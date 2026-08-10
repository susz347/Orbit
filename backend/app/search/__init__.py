"""搜索模块：向量检索 + 结果后处理（支持多租户 + Active Index 版本机制）

实现拆分为：core（检索核心 + count 缓存 + active index 解析）、
format（结果格式化），此处仅做导出。
"""
from .core import (
    _count_cache,
    _count_lock,
    _get_cached_count,
    _invalidate_count_cache,
    resolve_active_collection,
    resolve_active_version,
    search,
)
from .format import search_formatted

__all__ = [
    "_count_cache",
    "_count_lock",
    "_get_cached_count",
    "_invalidate_count_cache",
    "resolve_active_collection",
    "resolve_active_version",
    "search",
    "search_formatted",
]
