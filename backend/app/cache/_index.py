"""缓存向量索引（C3）：Faiss 可选后端，不可用时自动回退暴力搜索。

参考 GPTCache 的模块化设计：向量索引作为缓存存储的可选加速器。
- 写入: add(key, embedding)  保持与 _cache 字典同步
- 搜索: search(q, top_k)     返回 [(cache_key, score)]，cosine（归一化内积）
- 删除: remove(key)          惰性标记 + 定期重建，避免 Faiss 不支持删除的限制
- 回退: faiss 未安装/初始化失败时 search 返回空列表，调用方走暴力搜索
"""

import logging

logger = logging.getLogger(__name__)

try:
    import faiss
    import numpy as np
    _HAS_FAISS = True
except ImportError:  # pragma: no cover - faiss 为可选依赖
    faiss = None
    np = None
    _HAS_FAISS = False


class CacheIndex:
    """Faiss 内存索引包装。"""

    def __init__(self, default_dim: int = 768):
        self.default_dim = default_dim
        self.dim = default_dim
        self._index = None
        self._id_map: list[str] = []      # Faiss 行号 → cache_key
        self._dead: set[int] = set()      # 惰性删除标记（Faiss 不支持删行）
        self._ready = False
        self._init_index()

    def _init_index(self):
        if not _HAS_FAISS:
            logger.debug("Faiss 未安装，缓存索引回退暴力搜索")
            return
        try:
            self._index = faiss.IndexFlatIP(self.dim)
            self._ready = True
        except Exception as e:
            logger.warning("Faiss 索引初始化失败，回退暴力搜索: %s", e)
            self._ready = False

    @property
    def enabled(self) -> bool:
        return self._ready and self._index is not None

    @property
    def ntotal(self) -> int:
        return self._index.ntotal if self.enabled else 0

    def _rebuild(self):
        """从零重建（惰性删除积累过多时调用）。"""
        if not self.enabled:
            return
        try:
            self._index.reset()
            self._id_map = []
            self._dead = set()
        except Exception:
            self._ready = False

    def _dead_ratio(self) -> float:
        if self.ntotal == 0:
            return 0.0
        return len(self._dead) / self.ntotal

    def add(self, cache_key: str, embedding: list[float]):
        """写入一个向量。维度与索引不符时跳过（首条写入时对齐维度）。"""
        if not self.enabled or not embedding:
            return
        if len(embedding) != self.dim:
            if self.ntotal == 0:
                # 首条写入：用实际维度重建索引
                try:
                    self.dim = len(embedding)
                    self._index = faiss.IndexFlatIP(self.dim)
                except Exception as e:
                    logger.warning("Faiss 维度重建失败: %s", e)
                    self._ready = False
                    return
            else:
                return
        try:
            vec = np.array([embedding], dtype=np.float32)
            faiss.normalize_L2(vec)          # L2 归一化 → 内积等价 cosine
            self._index.add(vec)
            self._id_map.append(cache_key)
        except Exception as e:
            logger.warning("Faiss add 失败（回退暴力搜索）: %s", e)
            self._ready = False

    def remove(self, cache_key: str):
        """惰性删除：标记该 key 对应行，定期重建回收。"""
        if not self.enabled:
            return
        for pos, key in enumerate(self._id_map):
            if key == cache_key:
                self._dead.add(pos)
        # 死行过多时自动重建
        if self._dead_ratio() > 0.3:
            self._rebuild()

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[str, float]]:
        """搜索 top_k 相似条目，返回 [(cache_key, cosine_score)]。

        不可用/空索引/维度不符时返回空列表（调用方回退暴力搜索）。
        """
        if not self.enabled or self.ntotal == 0 or len(query_embedding) != self.dim:
            return []
        try:
            q = np.array([query_embedding], dtype=np.float32)
            faiss.normalize_L2(q)
            k = min(top_k, self.ntotal)
            scores, indices = self._index.search(q, k)
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < 0 or int(idx) in self._dead:
                    continue
                results.append((self._id_map[int(idx)], float(scores[0][i])))
            return results
        except Exception as e:
            logger.warning("Faiss search 失败（回退暴力搜索）: %s", e)
            self._ready = False
            return []

    def reset(self):
        """清空索引。"""
        self._rebuild()
        self.dim = self.default_dim
