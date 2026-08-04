"""ChromaDB 存储模块（支持多租户 Collection 隔离）

实现拆分为：client（客户端/Collection 管理）、documents（文档增删/统计），此处仅做导出。
"""
from .client import _client, _client_lock, get_client, get_collection
from .documents import add_documents, delete_by_source, get_stats

__all__ = [
    "_client",
    "_client_lock",
    "get_client",
    "get_collection",
    "add_documents",
    "delete_by_source",
    "get_stats",
]
