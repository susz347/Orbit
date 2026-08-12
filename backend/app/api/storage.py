"""混合存储路由: /api/storage/*"""
from fastapi import APIRouter, Body, HTTPException, Request

from ..storage_router import route_storage, get_strategy_info, detect_content_type

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.get("/strategies")
def api_storage_strategies():
    return get_strategy_info()


@router.post("/analyze")
def api_storage_analyze(body: dict = Body(...), request: Request = None):
    filename = body.get("filename", "")
    text = body.get("text", "")
    file_size = body.get("file_size", 0)
    if not filename:
        raise HTTPException(400, "文件名不能为空")
    # SR1: LLM 兜底验证——前端传 key 时对低置信度 case 启用
    api_key = request.headers.get("X-API-Key") if request else None
    model = request.headers.get("X-LLM-Model") if request else None
    use_llm_verify = bool(body.get("use_llm_verify", False) and api_key)
    result = route_storage(filename, text, file_size,
                           use_llm_verify=use_llm_verify, api_key=api_key, model=model)
    return result
