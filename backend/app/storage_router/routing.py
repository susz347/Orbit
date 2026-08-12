"""内容识别与存储策略决策：detect_content_type → route_storage"""

import json
import logging
import os

from .policies import (
    STORAGE_STRATEGIES,
    FILE_TYPE_ROUTING,
    CONTRACT_KEYWORDS,
    TABLE_INDICATORS,
    RELATIONSHIP_INDICATORS,
)

logger = logging.getLogger(__name__)

# SR1: LLM 兜底验证的置信度阈值——规则命中低于此值时触发 LLM 确认
RULE_LOW_CONFIDENCE = 0.6

_VERIFY_PROMPT = """你是文档分类器。根据文件名和内容预览，判断该文档最适合哪种存储策略：
- rag: 普通文档（产品手册、FAQ、技术文档、教程、会议纪要）
- original: 合同/法律/合规/审计文件（需要原文溯源、不切割）
- structured: 表格数据（Excel/CSV、字段化查询）
- graph: 关系型数据（组织架构、依赖关系、人员汇报链）
- multimodal: 图片（OCR 后走 RAG）

文件名: {filename}
内容预览（前 500 字）:
{text}

只输出严格 JSON（不要代码块、不要解释）: {{"strategy": "rag" | "original" | "structured" | "graph" | "multimodal"}}"""


def detect_content_type(text: str, filename: str = "") -> str:
    """
    分析内容特征，判断文档类型。
    返回: "contract" | "table" | "relationship" | "document" | "code" | "image"
    """
    if not text:
        text = ""

    text_lower = text.lower()

    # 合同/法律文件——内容 + 文件名联合判断（SR2: 修复"采购合同.xlsx"被表格抢占）
    contract_score = sum(1 for kw in CONTRACT_KEYWORDS if kw in text_lower)
    filename_lower = filename.lower()
    contract_filename_score = sum(1 for kw in CONTRACT_KEYWORDS if kw in filename_lower)
    if contract_score + contract_filename_score >= 2:
        return "contract"

    # 关系型数据——内容关键词 + 结构化格式强信号（SR2: 修复 JSON/YAML 图数据）
    relation_score = sum(1 for kw in RELATIONSHIP_INDICATORS if kw in text_lower)
    ext = os.path.splitext(filename)[1].lower()
    if relation_score >= 3:
        return "relationship"
    # JSON/YAML 中的图结构强信号（nodes/edges 或 depends_on）
    if (ext == ".json" and "nodes" in text_lower and "edges" in text_lower) or \
       (ext in (".yaml", ".yml") and "depends_on" in text_lower):
        return "relationship"

    # 表格数据
    table_score = sum(1 for kw in TABLE_INDICATORS if kw in text_lower)
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".xlsx", ".xls", ".csv", ".tsv") or table_score >= 2:
        return "table"

    # 代码
    code_extensions = {".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c"}
    if ext in code_extensions:
        return "code"

    # 图片
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if ext in image_extensions:
        return "image"

    # 默认：普通文档
    return "document"


def _rule_confidence(content_type: str, text: str, filename: str = "") -> float:
    """SR1: 规则判决的置信度——关键词命中越多越可信（0-1）。"""
    text = text or ""
    text_lower = text.lower()
    ext = os.path.splitext(filename)[1].lower()

    if content_type == "contract":
        hits = sum(1 for kw in CONTRACT_KEYWORDS if kw in text_lower)
        return min(hits / 3, 1.0)  # 命中 ≥3 个合同关键词 → 100%
    if content_type == "table":
        table_exts = {".xlsx", ".xls", ".csv", ".tsv"}
        if ext in table_exts:
            return 1.0  # 表格扩展名 + 无内容 → 扩展名即确定
        hits = sum(1 for kw in TABLE_INDICATORS if kw in text_lower)
        return min(hits / 2, 1.0)
    if content_type == "relationship":
        hits = sum(1 for kw in RELATIONSHIP_INDICATORS if kw in text_lower)
        return min(hits / 3, 1.0)
    if content_type == "image":
        return 1.0  # 图片由扩展名决定，无歧义
    if content_type == "code":
        return 1.0  # 代码由扩展名决定，无歧义
    # document 默认——内容无明显特征，置信度中等
    return 0.5


def _llm_verify_strategy(filename: str, text: str = "", api_key: str = None, model: str = None) -> str:
    """SR1: LLM 兜底验证存储策略（参考 LangGraph Agentic RAG 的 Router 节点）。

    仅对规则低置信度的边缘 case 调用。失败/不可用时返回 ""（调用方回退规则结果）。
    """
    if not api_key:
        return ""
    try:
        from ..llm import get_llm_config, resolve_api_key, build_chat_request

        _, base_url, model_name = get_llm_config(model)
        api_key = resolve_api_key(api_key)
        prompt = _VERIFY_PROMPT.format(filename=filename or "(unknown)", text=(text or "")[:500])
        req = build_chat_request(base_url, api_key, {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 50,
        })
        import urllib.request
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        # 容错解析：提取 {strategy: ...}
        m = json.loads(content) if content.strip().startswith("{") else None
        if not m:
            import re
            m = re.search(r'\{\s*"strategy"\s*:\s*"(\w+)"', content)
            strategy = m.group(1) if m else ""
        else:
            strategy = m.get("strategy", "")
        valid = {"rag", "original", "structured", "graph", "multimodal"}
        return strategy if strategy in valid else ""
    except Exception as e:
        logger.warning("LLM 存储策略验证失败（回退规则）: %s", e)
        return ""


def route_storage(filename: str, text: str = "", file_size: int = 0,
                  use_llm_verify: bool = False, api_key: str = None, model: str = None) -> dict:
    """
    混合存储路由：根据文件类型 + 内容特征选择最佳存储策略。

    SR1: use_llm_verify=True 时，对规则低置信度的 case 用 LLM 兜底确认，
    减少边缘 case（如 PDF 夹表格、会议纪要引用合同条款）的误判。

    返回:
    {
        "strategy": "rag" | "original" | "structured" | "graph" | "multimodal",
        "reason": str,
        "content_type": str,
        "actions": list[str],   # 需要执行的操作步骤
    }
    """
    content_type = detect_content_type(text, filename)
    ext = os.path.splitext(filename)[1].lower()

    # ── 策略决策 ──
    if content_type == "contract":
        strategy = "original"
        reason = "合同/法律文件，需原文溯源，原样存储 + 全文索引"
        actions = ["保存原始文件", "建立全文索引", "不做切割"]
    elif content_type == "table":
        strategy = "structured"
        reason = "表格数据，结构化提取到 SQLite，支持字段查询"
        actions = ["解析表格结构", "提取字段到 SQLite", "保留原始文件备份"]
    elif content_type == "relationship":
        strategy = "graph"
        reason = "关系型数据，适合知识图谱存储"
        actions = ["提取实体和关系", "构建图谱节点和边", "保留原文备份"]
    elif content_type == "image":
        strategy = "multimodal"
        reason = "图片文件，OCR 提取文字后走 RAG"
        actions = ["OCR 提取文字", "文字走 RAG 向量化", "保留原图"]
    elif content_type == "code":
        strategy = "rag"
        reason = "代码文件，按函数/类切割后 RAG"
        actions = ["按代码结构切割", "RAG 向量化", "保留源文件"]
    else:
        # 普通文档 → RAG
        strategy = "rag"
        reason = "普通文档，语义切割后 RAG 向量化"
        actions = ["语义切割", "RAG 向量化", "保留原文"]

    # SR1: LLM 兜底验证——仅规则低置信度时触发（参考 LangGraph Agentic RAG Router 节点）
    llm_overrode = False
    if use_llm_verify:
        rule_conf = _rule_confidence(content_type, text, filename)
        if rule_conf < RULE_LOW_CONFIDENCE:
            llm_strategy = _llm_verify_strategy(filename, text, api_key, model)
            if llm_strategy and llm_strategy != strategy:
                old_strategy = strategy
                strategy = llm_strategy
                reason += f" + LLM 验证覆盖（{old_strategy}→{llm_strategy}, 规则置信度{rule_conf:.0%}）"
                llm_overrode = True

    result = {
        "strategy": strategy,
        "reason": reason,
        "content_type": content_type,
        "actions": actions,
        "file_extension": ext,
        "file_size": file_size,
    }
    if llm_overrode:
        result["llm_verified"] = True
        result["rule_confidence"] = round(rule_conf, 4)
    return result


def get_strategy_info() -> dict:
    """获取所有存储策略信息"""
    return {
        "strategies": STORAGE_STRATEGIES,
        "file_routing": FILE_TYPE_ROUTING,
        "total_strategies": len(STORAGE_STRATEGIES) + 1,  # +1 for multimodal
    }
