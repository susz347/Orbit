"""流式问答编排：缓存 → 检索 → 路由 → LLM 流式生成，按 SSE 事件序列输出。"""

import json
import time
import urllib.request

from ..config import settings
from ..logging_config import get_logger
from ..search import search
from ..router import route_model
from ..cache import get as cache_get, put as cache_put
from ..llm import (
    get_llm_config,
    resolve_api_key,
    build_chat_request,
    LENIENT_RAG_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    build_context_text,
    build_sources,
    build_rag_user_message,
    call_llm_with_retry,
    LLMCallFailedError,
)
from .sse import _sse

# 相关度阈值：cosine 相似度低于此值的检索结果视为与问题无关（如闲聊匹配到文档）
MIN_RELEVANCE_SCORE = 0.3

logger = get_logger(__name__)


def stream_ask(question: str, top_k: int = None, user_id: int = None, api_key: str = None, model: str = None):
    """
    流式 RAG 问答生成器。
    yield SSE 格式的数据。

    参数:
        user_id: 可选，已登录用户的 ID，用于租户隔离检索。
        api_key: 前端传入的 LLM API Key，优先于环境变量。
        model: 前端传入的模型名，优先于路由器默认模型。
    """
    if top_k is None:
        top_k = settings.rag.retrieval.top_k

    # ── Event 1: 开始 ──
    yield _sse("status", {"stage": "start", "question": question})

    # ── Event 2: 检查缓存 ──
    cached = cache_get(question)
    if cached:
        yield _sse("status", {
            "stage": "cache_hit",
            "score": cached.get("cache_hit_score", 0),
        })
        yield _sse("answer", {"text": cached["answer"], "sources": cached["sources"], "model": "cache"})
        yield _sse("done", {"model": "cache", "cached": True})
        return

    yield _sse("status", {"stage": "cache_miss"})

    # ── Event 3: 检索（含相关度过滤）──
    yield _sse("status", {"stage": "retrieving", "top_k": top_k})
    chunks = [c for c in search(question, top_k, user_id) if c["score"] >= MIN_RELEVANCE_SCORE]

    yield _sse("status", {
        "stage": "retrieved",
        "count": len(chunks),
        "top_score": round(chunks[0]["score"], 4) if chunks else 0,
    })

    # ── Event 4: 模型路由 ──
    scores = [c["score"] for c in chunks]
    route = route_model(question, scores)
    yield _sse("status", {
        "stage": "routing",
        "tier": route.tier,
        "model": route.model,
        "reason": route.reason,
        "confidence": route.confidence,
        "needs_clarification": route.needs_clarification,
    })

    # ── Event 5: 生成（流式）──
    api_key = resolve_api_key(api_key)
    # 模型优先级：前端指定 > 路由器选择 > 环境变量默认
    _, base_url, model_name = get_llm_config(model or route.model)

    sources = build_sources(chunks, default_source="?")

    if not api_key:
        logger.warning("no_api_key_configured", model=model_name)
        # Fallback: 无 LLM 时返回检索结果
        if chunks:
            fallback_text = f"（未配置 LLM_API_KEY）\n\n最相关内容来自：{sources[0]['source']}\n\n{chunks[0]['text']}"
        else:
            fallback_text = "（未配置 LLM_API_KEY，且问题与知识库无关。请在设置中配置模型的 API Key。）"
        yield _sse("answer", {"text": fallback_text, "sources": sources, "model": "fallback"})
        yield _sse("done", {"model": "fallback", "retrieval_count": len(chunks)})
        return

    # 构建 LLM 请求：有相关检索结果走 RAG 模式，否则走纯对话模式
    if chunks:
        system_prompt = LENIENT_RAG_SYSTEM_PROMPT
        user_message = build_rag_user_message(question, build_context_text(chunks))
    else:
        system_prompt = CHAT_SYSTEM_PROMPT
        user_message = question

    req = build_chat_request(base_url, api_key, {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": route.temperature,
        "max_tokens": route.max_tokens,
        "stream": True,  # 启用流式
    })

    full_answer = ""
    final_model = model_name

    # P0-3: 流式 LLM 调用（带重试和熔断保护）
    # 流式模式：retry 包装 HTTP 连接建立，连接成功后内部逐行读取 chunk
    start_time = time.monotonic()
    try:
        result = call_llm_with_retry(
            call_fn=lambda: urllib.request.urlopen(req, timeout=60),
            model_name=model_name,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        final_model = result["model_used"]

        with result["data"] as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk_data = json.loads(data)
                    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        full_answer += token
                        yield _sse("token", {"text": token})
                except json.JSONDecodeError:
                    continue

        # 存入缓存
        cache_put(question, full_answer, sources, final_model)

        logger.info(
            "stream_generate_success",
            model=final_model,
            latency_ms=elapsed_ms,
            answer_length=len(full_answer),
            retrieval_count=len(chunks),
        )

        yield _sse("sources", {"sources": sources})
        yield _sse("done", {
            "model": final_model,
            "retrieval_count": len(chunks),
            "cached": False,
            "answer_length": len(full_answer),
        })

    except LLMCallFailedError as e:
        logger.error(
            "stream_generate_failed",
            error=str(e)[:200],
            model=model_name,
            retrieval_count=len(chunks),
        )
        yield _sse("error", {"message": str(e)})
        yield _sse("done", {"model": model_name, "error": True})
    except Exception as e:
        logger.error(
            "stream_unexpected_error",
            error=str(e)[:200],
            model=model_name,
        )
        yield _sse("error", {"message": str(e)})
        yield _sse("done", {"model": model_name, "error": True})
