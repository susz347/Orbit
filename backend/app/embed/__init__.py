"""Embedding 模块：支持 sentence-transformers（轻量本地）和 Ollama（BGE-M3）

实现拆分为：backends（后端实现类）、core（后端选择/预热/入口），此处仅做导出。
"""
from .backends import EmbeddingBackend, SentenceTransformerBackend, OllamaBackend
from .core import _backend, get_backend, preload_model, encode

__all__ = [
    "EmbeddingBackend",
    "SentenceTransformerBackend",
    "OllamaBackend",
    "_backend",
    "get_backend",
    "preload_model",
    "encode",
]
