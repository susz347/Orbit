"""
X-Request-ID 中间件 — 全链路请求追踪

每个 HTTP 请求都获得唯一标识符，便于日志关联和问题排查。
- 优先使用客户端传入的 X-Request-ID 头
- 无头时自动生成 UUID4
- 响应中回传 X-Request-ID 头
- 注入到 structlog context，所有后续日志自动携带 request_id
"""

import uuid
import logging

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """注入 X-Request-ID 到请求上下文和响应头，并绑定到 structlog"""

    async def dispatch(self, request: Request, call_next):
        # 优先使用客户端传入的 request-id
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # P0-1: 绑定到 structlog context，后续所有日志自动携带 request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response: Response = await call_next(request)

            # 回传 request-id
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # 请求结束后清理 context，防止污染下一个请求
            structlog.contextvars.clear_contextvars()


def get_request_id(request: Request) -> str:
    """获取当前请求的 request_id，供下游模块使用"""
    return getattr(request.state, "request_id", "unknown")
