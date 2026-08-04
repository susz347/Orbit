"""内容识别与存储策略决策：detect_content_type → route_storage"""

import os

from .policies import (
    STORAGE_STRATEGIES,
    FILE_TYPE_ROUTING,
    CONTRACT_KEYWORDS,
    TABLE_INDICATORS,
    RELATIONSHIP_INDICATORS,
)


def detect_content_type(text: str, filename: str = "") -> str:
    """
    分析内容特征，判断文档类型。
    返回: "contract" | "table" | "relationship" | "document" | "code" | "image"
    """
    if not text:
        text = ""

    text_lower = text.lower()

    # 合同/法律文件
    contract_score = sum(1 for kw in CONTRACT_KEYWORDS if kw in text_lower)
    if contract_score >= 2:
        return "contract"

    # 关系型数据
    relation_score = sum(1 for kw in RELATIONSHIP_INDICATORS if kw in text_lower)
    if relation_score >= 3:
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


def route_storage(filename: str, text: str = "", file_size: int = 0) -> dict:
    """
    混合存储路由：根据文件类型 + 内容特征选择最佳存储策略。

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

    return {
        "strategy": strategy,
        "reason": reason,
        "content_type": content_type,
        "actions": actions,
        "file_extension": ext,
        "file_size": file_size,
    }


def get_strategy_info() -> dict:
    """获取所有存储策略信息"""
    return {
        "strategies": STORAGE_STRATEGIES,
        "file_routing": FILE_TYPE_ROUTING,
        "total_strategies": len(STORAGE_STRATEGIES) + 1,  # +1 for multimodal
    }
