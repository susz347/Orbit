"""
结构化日志配置（基于 structlog）。

特性：
- JSON 格式输出（生产环境），彩色 console 输出（开发环境）
- 自动注入 request_id（从请求上下文提取）
- 桥接标准 logging，让第三方库（chromadb、uvicorn 等）的日志也结构化
- 按模块名自动设置不同库的日志级别

Usage:
    from .logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("llm_call_completed", model="deepseek-v4", tokens=1523, latency_ms=320)
"""

import logging
import os
import sys
from typing import Any, Optional

import structlog


def setup_logging() -> None:
    """初始化结构化日志系统。

    应在 FastAPI 应用启动前调用（lifespan 最开始）。
    """
    # 判断是否为开发环境
    is_dev = os.getenv("ENV", "development").lower() in ("dev", "development", "local")

    # ── 1. 配置标准 logging ──
    _config_stdlib_logging(is_dev)

    # ── 2. 配置 structlog ──
    _config_structlog(is_dev)


def _config_stdlib_logging(is_dev: bool) -> None:
    """配置 Python 标准 logging，让日志输出到 stdout 并统一格式。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(message)s" if is_dev else '{"logger": "%(name)s", "level": "%(levelname)s", "event": %(message)s}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # 降低第三方库的日志噪音
    _silence_noisy_libraries()

    # 本应用模块设为 DEBUG（开发环境）
    if is_dev:
        logging.getLogger("app").setLevel(logging.DEBUG)


def _silence_noisy_libraries() -> None:
    """降低第三方库的日志噪音。"""
    noisy = {
        "chromadb": logging.WARNING,
        "chromadb.telemetry": logging.ERROR,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "urllib3": logging.WARNING,
        "sentence_transformers": logging.WARNING,
        "asyncio": logging.WARNING,
        "uvicorn.access": logging.WARNING,
    }
    for name, level in noisy.items():
        logging.getLogger(name).setLevel(level)


def _config_structlog(is_dev: bool) -> None:
    """配置 structlog 处理器链。"""
    # 共享的预处理器
    shared_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if is_dev:
        # 开发环境：彩色 console
        structlog.configure(
            processors=shared_processors
            + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # 生产环境：JSON 输出
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: Optional[str] = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """获取结构化日志实例。

    用法：
        logger = get_logger(__name__)
        logger.info("user_login", username="ace", ip="1.2.3.4")

    绑定上下文（在整个请求生命周期内有效）：
        logger = get_logger(__name__).bind(request_id="abc-123")
        logger.info("processing")  # 自动带上 request_id
    """
    logger = structlog.get_logger(name or __name__)
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
