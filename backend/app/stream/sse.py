"""SSE (Server-Sent Events) 事件格式化。"""

import json


def _sse(event: str, data: dict) -> str:
    """格式化为 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
