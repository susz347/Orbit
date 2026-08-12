"""存储策略与规则定义（纯数据，无逻辑）"""

# ── 存储策略定义 ──────────────────────────────────

STORAGE_STRATEGIES = {
    "rag": {
        "desc": "RAG 向量化存储",
        "suitable": ["产品手册", "FAQ", "技术文档", "会议纪要", "Markdown", "教程"],
        "not_suitable": ["合同", "发票", "表格数据"],
    },
    "original": {
        "desc": "原样存储 + 全文索引",
        "suitable": ["合同", "发票", "合规文件", "法律文书", "证书", "报告"],
        "not_suitable": ["FAQ", "短文本"],
    },
    "structured": {
        "desc": "结构化提取到 SQLite",
        "suitable": ["Excel", "CSV", "表格", "表单", "数据库导出", "价格表"],
        "not_suitable": ["长文本", "合同"],
    },
    "graph": {
        "desc": "知识图谱（Neo4j/JSON Graph）",
        "suitable": ["组织架构", "项目依赖", "供应商关系", "人员关系"],
        "not_suitable": ["纯文本", "表格"],
    },
}


# ── 文件类型 → 存储策略映射 ──────────────────────

FILE_TYPE_ROUTING = {
    # 文档类 → RAG
    ".md": "rag",
    ".markdown": "rag",
    ".txt": "rag",
    ".pdf": "rag",  # PDF 默认 RAG，但如果是合同/发票则 original

    # 表格类 → 结构化
    ".xlsx": "structured",
    ".xls": "structured",
    ".csv": "structured",
    ".tsv": "structured",

    # 图片类 → 多模态（OCR + RAG）
    ".jpg": "multimodal",
    ".jpeg": "multimodal",
    ".png": "multimodal",
    ".gif": "multimodal",
    ".webp": "multimodal",

    # 代码类 → RAG
    ".py": "rag",
    ".js": "rag",
    ".ts": "rag",
    ".java": "rag",
    ".go": "rag",

    # 数据类 → 结构化
    ".json": "structured",
    ".xml": "structured",
}


# ── 内容特征 → 策略调整 ──────────────────────────

CONTRACT_KEYWORDS = [
    "合同", "协议", "甲方", "乙方", "合同编号", "签署", "盖章",
    "invoice", "发票", "收据", "保密", "非公开", "法律", "合规",
    "仲裁", "诉讼", "违约", "保密期限",
]
TABLE_INDICATORS = ["sheet", "table", "row", "column", "单元格", "行", "列"]
RELATIONSHIP_INDICATORS = [
    "上级", "下级", "依赖", "关联", "负责人", "汇报", "汇报给", "报告给",
    "parent", "child", "depends", "depends_on", "reports to", "manager",
    "组织架构", "架构", "层级", "节点", "nodes", "edges", "source", "target",
    "CEO", "CTO", "CFO", "director",
]
