"""RAG 生成服务：检索结果 + 用户问题 → LLM → 带引用的答案（非流式）。"""

import json
import urllib.request

from ..llm import (
    get_llm_config,
    build_chat_request,
    STRICT_RAG_SYSTEM_PROMPT,
    build_context_text,
    build_sources,
    build_strict_rag_user_message,
)


def generate_answer(question: str, context_chunks: list[dict], history: list[dict] = None, model: str = None, api_key: str = None) -> dict:
    """
    RAG 生成：检索结果 + 用户问题 → LLM → 带引用的答案

    参数:
        model: 指定 LLM 模型名。不传时使用 LLM_MODEL 环境变量默认值。
        api_key: API Key。优先使用此参数，不传（None）时回退到环境变量 LLM_API_KEY。

    返回: { "answer", "sources", "model", "context_count" }
    """
    env_key, base_url, model = get_llm_config(model=model)
    if api_key is None:
        api_key = env_key

    # 构建上下文与来源
    context_text = build_context_text(context_chunks, with_score=True) or "（无检索结果）"
    sources = build_sources(context_chunks)
    user_message = build_strict_rag_user_message(question, context_text)

    # 构建 messages
    messages = [{"role": "system", "content": STRICT_RAG_SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-4:])  # 最近 2 轮对话
    messages.append({"role": "user", "content": user_message})

    # 如果没有 API key，返回检索结果作为 fallback
    if not api_key:
        return {
            "answer": f"（未配置 LLM_API_KEY，以下为检索结果摘要）\n\n根据知识库检索，最相关的内容来自：{', '.join(s['source'] for s in sources)}\n\n{context_chunks[0]['text'] if context_chunks else '无结果'}",
            "sources": sources,
            "model": "fallback (no LLM)",
            "context_count": len(context_chunks),
        }

    # 调用 LLM
    req = build_chat_request(base_url, api_key, {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1000,
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            answer = result["choices"][0]["message"]["content"]
            return {
                "answer": answer,
                "sources": sources,
                "model": model,
                "context_count": len(context_chunks),
            }
    except Exception as e:
        return {
            "answer": f"LLM 调用失败: {str(e)}\n\n以下为检索结果：\n{context_chunks[0]['text'] if context_chunks else '无结果'}",
            "sources": sources,
            "model": f"error: {model}",
            "context_count": len(context_chunks),
        }
