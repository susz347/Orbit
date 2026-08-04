"""LLM API 配置解析与 HTTP 请求构造（OpenAI 兼容协议）。"""

import json
import os
import urllib.request


def get_llm_config(model: str = None):
    """从环境变量读取 LLM 配置，根据模型名自动选择 API 地址。

    返回: (api_key, base_url, model)
    """
    api_key = os.getenv("LLM_API_KEY", "")
    model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

    # 根据模型名自动匹配 API 地址
    if "deepseek" in model.lower():
        default_url = "https://api.deepseek.com/v1/chat/completions"
    elif "claude" in model.lower():
        default_url = "https://api.anthropic.com/v1/messages"
    else:
        default_url = "https://api.openai.com/v1/chat/completions"

    base_url = os.getenv("LLM_BASE_URL", default_url)
    return api_key, base_url, model


def resolve_api_key(api_key: str = None) -> str:
    """优先使用传入的 api_key，为空（None 或空字符串）时回退到环境变量 LLM_API_KEY。"""
    return api_key or os.getenv("LLM_API_KEY", "")


def build_chat_request(base_url: str, api_key: str, payload: dict) -> urllib.request.Request:
    """构造 OpenAI 兼容的 chat/completions POST 请求。"""
    return urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
