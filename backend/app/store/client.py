"""ChromaDB 客户端与 Collection 管理（线程安全单例、多租户隔离）"""

import threading
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from ..config import settings


_client = None
_client_lock = threading.Lock()


def get_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端（线程安全单例）"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(
                    path=settings.CHROMA_PERSIST_DIR,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
    return _client


def get_collection(user_id: Optional[int] = None) -> chromadb.Collection:
    """
    获取 Collection。

    - user_id=None: 全局默认 Collection（向后兼容）
    - user_id=1:   Collection "user_1"（多租户隔离）
    """
    client = get_client()
    collection_name = f"user_{user_id}" if user_id else settings.CHROMA_COLLECTION
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def get_collection_by_name(collection_name: str) -> chromadb.Collection:
    """按名称打开 Collection（服务端解析后的名称）。

    注意：绝不将此函数直接暴露给 HTTP 输入——collection 名称必须
    由服务端代码解析（如 active index 版本机制），防止任意 Collection 访问。
    """
    return get_client().get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
