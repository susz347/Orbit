"""Embedding 入口：后端选择（线程安全懒加载）、预热、encode"""

import logging
import threading
from typing import Optional

from ..config import settings
from .backends import EmbeddingBackend, OllamaBackend, SentenceTransformerBackend

logger = logging.getLogger(__name__)

_backend: Optional[EmbeddingBackend] = None
_backend_lock = threading.Lock()


def get_backend() -> EmbeddingBackend:
    """获取 Embedding 后端（线程安全懒加载）"""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                if settings.EMBED_BACKEND == "ollama":
                    _backend = OllamaBackend().load()
                else:
                    _backend = SentenceTransformerBackend().load()
    return _backend


def preload_model():
    """
    预热：在 FastAPI on_startup 事件中调用。
    确保第一个请求不需要等待模型加载（节省数秒延迟）。
    """
    logger.info("Preloading embedding model...")
    get_backend()
    logger.info("Embedding model ready.")


def encode(texts: list[str]) -> list[list[float]]:
    return get_backend().encode(texts)
