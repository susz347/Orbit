"""语义缓存存储：get / put / stats / clear 与缓存条目管理。

- 缓存 Key: query 的 embedding
- 命中条件: cosine similarity > CACHE_THRESHOLD (默认 0.95)
- 存储: 内存字典（MVP），生产可换 Redis
- TTL: 1 小时（文档未更新时有效）
"""

import time
from typing import Optional
from ..embed import encode
from .similarity import find_similar

# 缓存条目: {cache_key: {"answer": str, "sources": list, "timestamp": float, "query": str, "embedding": list}}
_cache: dict = {}

CACHE_THRESHOLD = 0.95      # cosine similarity 命中阈值
CACHE_TTL_SECONDS = 3600    # 1 小时
MAX_CACHE_SIZE = 500        # 最大缓存条目数


def _find_similar(query_embedding: list[float]) -> Optional[dict]:
    """在缓存中查找相似查询（单参数包装，兼容既有调用面）"""
    return find_similar(query_embedding, _cache, CACHE_TTL_SECONDS, CACHE_THRESHOLD)


def get(query: str) -> Optional[dict]:
    """
    查询缓存。
    如果命中，返回 {"answer": ..., "sources": ..., "cache_hit": True, "cache_hit_score": ...}
    如果未命中，返回 None
    """
    # 生成 query embedding
    embeddings = encode([query])
    if not embeddings:
        return None

    query_embedding = embeddings[0]
    hit = _find_similar(query_embedding)

    if hit:
        return {
            "answer": hit["answer"],
            "sources": hit["sources"],
            "model": "cache",
            "cache_hit": True,
            "cache_hit_score": hit.get("cache_hit_score", 0),
        }

    return None


def put(query: str, answer: str, sources: list, model: str):
    """存入缓存"""
    # LRU: 超过最大大小时删除最早的
    if len(_cache) >= MAX_CACHE_SIZE:
        oldest_key = min(_cache, key=lambda k: _cache[k]["timestamp"])
        del _cache[oldest_key]

    embeddings = encode([query])
    if not embeddings:
        return

    cache_key = f"q_{hash(query)}"
    _cache[cache_key] = {
        "query": query,
        "answer": answer,
        "sources": sources,
        "model": model,
        "embedding": embeddings[0],
        "timestamp": time.time(),
    }


def stats() -> dict:
    """缓存统计"""
    now = time.time()
    active = sum(1 for v in _cache.values() if now - v["timestamp"] <= CACHE_TTL_SECONDS)
    return {
        "total_entries": len(_cache),
        "active_entries": active,
        "max_size": MAX_CACHE_SIZE,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "threshold": CACHE_THRESHOLD,
    }


def clear():
    """清空缓存"""
    _cache.clear()
