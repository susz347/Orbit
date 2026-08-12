"""P2-2: 可观测性模块 — Prometheus Metrics + Sentry Error Tracking。

特性：
- /metrics 端点暴露 Prometheus 格式指标（请求量、延迟、错误率）
- Sentry 自动捕获未处理异常并上报到 Sentry DSN
- LLM 调用计数器和直方图
- RAG 检索指标
"""

import os
import logging
from typing import Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# 懒加载 Prometheus 指标（可选依赖）
# ═══════════════════════════════════════════════

_prometheus_available = False
_llm_call_counter = None
_llm_call_latency = None
_llm_token_counter = None
_rag_search_counter = None
_rag_search_latency = None


def _ensure_prometheus():
    """惰性初始化 Prometheus 指标。"""
    global _prometheus_available, _llm_call_counter, _llm_call_latency, _llm_token_counter, _rag_search_counter, _rag_search_latency
    if _prometheus_available:
        return True
    try:
        from prometheus_client import Counter, Histogram

        global llm_call_counter, llm_call_latency, llm_token_counter, rag_search_counter, rag_search_latency

        _llm_call_counter = Counter(
            "orbit_llm_calls_total", "Total LLM API calls",
            ["model", "status"],
        )
        _llm_call_latency = Histogram(
            "orbit_llm_call_latency_seconds", "LLM API call latency",
            ["model"], buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
        )
        _llm_token_counter = Counter(
            "orbit_llm_tokens_total", "Total tokens consumed",
            ["model", "type"],
        )
        _rag_search_counter = Counter(
            "orbit_rag_searches_total", "Total RAG searches",
            ["tier"],
        )
        _rag_search_latency = Histogram(
            "orbit_rag_search_latency_seconds", "RAG search latency",
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0),
        )

        _prometheus_available = True
        return True
    except ImportError:
        _prometheus_available = False
        return False


# ═══════════════════════════════════════════════
# Prometheus 集成（可选依赖）
# ═══════════════════════════════════════════════

def setup_prometheus(app: FastAPI) -> None:
    """安装 Prometheus 指标仪表盘到 FastAPI 应用。

    暴露 GET /metrics 端点。若 prometheus_fastapi_instrumentator 
    未安装，静默跳过。
    """
    if not os.getenv("ENABLE_PROMETHEUS", "").lower() in ("1", "true", "yes"):
        logger.info("prometheus_disabled")
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator, metrics as inst_metrics

        instrumentator = Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_respect_env_var=False,
        )

        instrumentator.add(inst_metrics.request_size())
        instrumentator.add(inst_metrics.response_size())
        instrumentator.add(inst_metrics.latency())
        instrumentator.add(inst_metrics.requests())

        instrumentator.instrument(app).expose(
            app, endpoint="/metrics",
            include_in_schema=True, tags=["monitoring"],
        )

        logger.info("prometheus_metrics_enabled", endpoint="/metrics")
    except ImportError:
        logger.info("prometheus_skipped", reason="prometheus_fastapi_instrumentator not installed")


# ═══════════════════════════════════════════════
# Sentry 集成
# ═══════════════════════════════════════════════

def setup_sentry(dsn: Optional[str] = None) -> None:
    """初始化 Sentry 错误追踪。

    参数:
        dsn: Sentry DSN 地址。不传时从 SENTRY_DSN 环境变量读取。
             若均未设置，Sentry 不会被初始化（静默跳过）。
    """
    dsn = dsn or os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("sentry_disabled", reason="SENTRY_DSN not configured")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        env = os.getenv("ENV", "development")

        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            traces_sample_rate=0.3 if env == "production" else 1.0,
            integrations=[
                StarletteIntegration(transaction_style="url"),
                FastApiIntegration(transaction_style="url"),
                LoggingIntegration(
                    level=logging.WARNING,
                    event_level=logging.ERROR,
                ),
            ],
            send_default_pii=False,
            enable_tracing=True,
        )

        logger.info("sentry_initialized", environment=env)

    except ImportError:
        logger.warning("sentry_not_installed", hint="pip install sentry-sdk")
    except Exception as e:
        logger.warning("sentry_init_failed", error=str(e)[:200])


# ═══════════════════════════════════════════════
# 便捷记录函数
# ═══════════════════════════════════════════════

def record_llm_call(
    model: str,
    status: str,
    latency_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """记录一次 LLM 调用到 Prometheus 指标。

    若 prometheus_client 未安装，静默跳过。
    """
    if not _ensure_prometheus():
        return
    _llm_call_counter.labels(model=model, status=status).inc()
    _llm_call_latency.labels(model=model).observe(latency_seconds)
    if prompt_tokens:
        _llm_token_counter.labels(model=model, type="prompt").inc(prompt_tokens)
    if completion_tokens:
        _llm_token_counter.labels(model=model, type="completion").inc(completion_tokens)


def record_rag_search(tier: str, latency_seconds: float) -> None:
    """记录一次 RAG 搜索到 Prometheus 指标。

    若 prometheus_client 未安装，静默跳过。
    """
    if not _ensure_prometheus():
        return
    _rag_search_counter.labels(tier=tier).inc()
    _rag_search_latency.observe(latency_seconds)
