"""相似度计算：无状态纯函数，供缓存命中判断使用。"""

import time
from typing import Optional


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的 cosine 相似度。维度不一致或零向量返回 0。"""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_similar(
    query_embedding: list[float], cache: dict, ttl_seconds: int, threshold: float,
    namespace: Optional[str] = None,
) -> Optional[dict]:
    """在缓存字典中查找相似查询，返回命中的缓存条目（附 cache_hit_score）。

    同时清理过期条目（TTL）。
    namespace: 多租户缓存隔离——只匹配相同 namespace 的条目；None 匹配无 namespace 条目。
    """
    now = time.time()

    # 清理过期条目
    expired_keys = [k for k, v in cache.items() if now - v["timestamp"] > ttl_seconds]
    for k in expired_keys:
        del cache[k]

    # 暴力搜索（MVP，条目少时够用）
    best_score = 0.0
    best_entry = None

    for entry in cache.values():
        if now - entry["timestamp"] > ttl_seconds:
            continue
        if entry.get("namespace") != namespace:
            continue
        score = cosine_similarity(query_embedding, entry["embedding"])
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_score >= threshold and best_entry:
        best_entry["cache_hit_score"] = round(best_score, 4)
        return best_entry

    return None
