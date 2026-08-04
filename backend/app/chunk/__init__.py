"""文本切割模块

实现位于 chunking.py，此处仅做导出。
"""
from .chunking import chunk_text, _split_long_text

__all__ = ["chunk_text", "_split_long_text"]
