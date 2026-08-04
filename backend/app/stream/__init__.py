"""
流式输出模块

SSE (Server-Sent Events) 流式返回 RAG 问答结果。
用户看到的是逐步生成的答案，而非等待完整结果。

实现位于 service.py（问答编排）与 sse.py（事件格式化），此处仅做导出。
LLM 调用细节已下沉到公共层 app/llm/。
"""
from .service import stream_ask, MIN_RELEVANCE_SCORE
from .sse import _sse

__all__ = ["stream_ask", "MIN_RELEVANCE_SCORE", "_sse"]
