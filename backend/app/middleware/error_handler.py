"""
全局异常处理中间件。

所有未捕获异常在此统一处理，返回结构化的 JSON 错误响应：
- 隐藏内部堆栈（生产环境），保留 request_id 供排查
- 区分已知业务异常（如 HTTPException、RateLimitExceeded）和未知异常
- 记录完整的异常信息到结构化日志
"""

import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .request_id import get_request_id

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """统一异常处理。

    返回格式：
        {
            "error": "错误描述",
            "detail": "详细信息（仅开发环境）",
            "request_id": "abc-123"
        }
    """
    request_id = get_request_id(request)

    # ── 已知异常：HTTPException ──
    if isinstance(exc, StarletteHTTPException):
        logger.warning(
            "http_exception",
            status_code=exc.status_code,
            detail=str(exc.detail),
            request_id=request_id,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": str(exc.detail),
                "request_id": request_id,
            },
        )

    # ── 未知异常：记录完整堆栈 → 返回通用 500 ──
    logger.error(
        "unhandled_exception",
        exc_info=True,
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc) if _is_dev() else "An unexpected error occurred",
            "request_id": request_id,
        },
    )


def _is_dev() -> bool:
    """判断是否为开发环境。"""
    import os
    return os.getenv("ENV", "development").lower() in ("dev", "development", "local")
