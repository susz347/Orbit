"""
混合存储路由模块

根据文档类型自动选择最佳存储策略：
- 原样存储：合同、发票、合规文件（需原文溯源）
- RAG 向量化：手册、FAQ、文档（需语义检索）
- 结构化提取：表格、表单、数据（需字段查询）
- 知识图谱：关系型数据（人员、项目依赖）

Knowledge Agent 参照 rag-optimization-guide.md 做最终决策。

实现拆分为：policies（策略/规则数据）、routing（内容识别与决策）、
executors（策略执行），此处仅做导出。
"""
from .policies import (
    STORAGE_STRATEGIES,
    FILE_TYPE_ROUTING,
    CONTRACT_KEYWORDS,
    TABLE_INDICATORS,
    RELATIONSHIP_INDICATORS,
)
from .routing import detect_content_type, route_storage, get_strategy_info, _rule_confidence, _llm_verify_strategy
from .executors import (
    execute_strategy,
    _execute_original,
    _execute_structured,
    _execute_rag,
    _execute_multimodal,
    _execute_graph,
    _safe_table_name,
)

__all__ = [
    "STORAGE_STRATEGIES",
    "FILE_TYPE_ROUTING",
    "CONTRACT_KEYWORDS",
    "TABLE_INDICATORS",
    "RELATIONSHIP_INDICATORS",
    "detect_content_type",
    "route_storage",
    "get_strategy_info",
    "_rule_confidence",
    "_llm_verify_strategy",
    "execute_strategy",
    "_execute_original",
    "_execute_structured",
    "_execute_rag",
    "_execute_multimodal",
    "_execute_graph",
    "_safe_table_name",
]
