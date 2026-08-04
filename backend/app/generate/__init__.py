"""LLM 生成模块 — 把检索结果 + 用户问题发给 LLM 生成答案（非流式）。

实现位于 service.py，此处仅做导出。LLM 调用细节已下沉到公共层 app/llm/。
"""
from ..llm import get_llm_config
from .service import generate_answer

# 向后兼容别名：既有代码（如 test_generate）通过此私有名引用
_get_llm_config = get_llm_config

__all__ = ["generate_answer", "get_llm_config", "_get_llm_config"]
