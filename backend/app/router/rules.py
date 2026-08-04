"""Layer 1：规则引擎 — 快速过滤（微秒级），处理 80% 常见查询"""

import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── 模型预设 ──────────────────────────────────────

MODEL_PRESETS = {
    "fast": {
        "model": os.getenv("LLM_MODEL_FAST", "gpt-4o-mini"),
        "max_tokens": 500,
        "temperature": 0.3,
        "desc": "快模型：简单问答、定义查询、FAQ",
    },
    "balanced": {
        "model": os.getenv("LLM_MODEL_BALANCED", "gpt-4o"),
        "max_tokens": 1000,
        "temperature": 0.3,
        "desc": "中等模型：通用问答、文档总结",
    },
    "strong": {
        "model": os.getenv("LLM_MODEL_STRONG", "gpt-4o"),
        "max_tokens": 2000,
        "temperature": 0.2,
        "desc": "强模型：代码生成、多步推理、架构设计",
    },
    "unknown": {
        "model": os.getenv("LLM_MODEL_FAST", "gpt-4o-mini"),
        "max_tokens": 300,
        "temperature": 0.2,
        "desc": "未知意图：尝试从知识库检索回答",
    },
    "out_of_scope": {
        "model": os.getenv("LLM_MODEL_FAST", "gpt-4o-mini"),
        "max_tokens": 200,
        "temperature": 0.1,
        "desc": "领域外：礼貌拒绝 + 引导回知识库范围",
    },
}


# ── 意图体系（三层：domain → intent → task）──

INTENT_TAXONOMY = {
    "knowledge": {
        "domain": "知识库查询",
        "intents": {
            "definition": "定义/概念查询（什么是、意思是）",
            "list": "列表查询（有哪些、列出）",
            "howto": "用法查询（怎么用、如何）",
            "where": "位置查询（在哪里、路径）",
            "count": "数量查询（多少、几个）",
        },
        "default_tier": "fast",
    },
    "generation": {
        "domain": "内容生成",
        "intents": {
            "code_gen": "代码生成（写一个、创建、实现）",
            "document": "文档生成（写一份报告、生成文档）",
        },
        "default_tier": "strong",
    },
    "analysis": {
        "domain": "分析与推理",
        "intents": {
            "analyze": "分析推理（分析、对比、评估）",
            "causal": "因果推理（为什么、原因）",
            "security": "安全分析（漏洞、风险）",
        },
        "default_tier": "strong",
    },
    "troubleshooting": {
        "domain": "排错与修复",
        "intents": {
            "debug": "调试（bug、错误、异常）",
            "fix": "修复（怎么修复、解决方案）",
        },
        "default_tier": "strong",
    },
    "design": {
        "domain": "架构设计",
        "intents": {
            "architecture": "架构设计（设计、重构、优化）",
            "workflow": "流程设计（步骤、流程、怎么做到）",
        },
        "default_tier": "strong",
    },
}


# ── 规则映射 ────────────────────────────────────

SIMPLE_PATTERNS = [
    (r'什么是|是什么|意思是', 'definition', 0.85),
    (r'有哪些|列表|清单', 'list', 0.85),
    (r'怎么用|如何使用|用法', 'howto', 0.80),
    (r'在哪|哪里|路径', 'where', 0.85),
    (r'多少|几个|数量', 'count', 0.85),
    (r'^.{1,15}$', 'short_query', 0.60),  # 短查询，置信度低
]

COMPLEX_PATTERNS = [
    (r'写一个|生成|创建|实现', 'code_gen', 0.80),
    (r'分析|对比|比较|评估', 'analyze', 0.85),
    (r'为什么|原因|根本', 'causal', 0.80),
    (r'重构|优化|改进|设计', 'architecture', 0.85),
    (r'步骤|流程|怎么做到', 'workflow', 0.80),
    (r'bug|错误|报错|异常|修复', 'debug', 0.90),
    (r'安全|漏洞|风险', 'security', 0.85),
    (r'报告|文档|总结', 'document', 0.75),
]

# 领域外关键词
OUT_OF_SCOPE_INDICATORS = [
    r'外卖|点餐|订餐|快递|打车|天气|股票|新闻|热搜|八卦',
    r'你是谁|你叫什么|你有什么功能',
    r'聊天|闲聊|讲故事|冷笑话|笑话|唱歌|诗',
]

# 安全预检
SAFETY_PATTERNS = [
    (r'(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)', "prompt_injection"),
    (r'(?i)system\s*prompt', "prompt_leak"),
    (r'(?i)forget\s+everything', "prompt_injection"),
]


def _regex_classify(query: str) -> tuple[Optional[str], float, str]:
    """
    规则引擎分类。
    返回: (tier, confidence, intent_name) 或 (None, 0, "") 表示规则无法匹配
    """
    query_lower = query.lower().strip()

    # 安全预检
    for pattern, threat_type in SAFETY_PATTERNS:
        if re.search(pattern, query_lower):
            return "out_of_scope", 1.0, threat_type

    # 领域外检测
    for pattern in OUT_OF_SCOPE_INDICATORS:
        if re.search(pattern, query_lower):
            return "out_of_scope", 0.8, "out_of_scope"

    # 先复杂后简单（避免短查询误判）
    best_complex = None
    for pattern, intent, conf in COMPLEX_PATTERNS:
        if re.search(pattern, query_lower):
            if best_complex is None or conf > best_complex[1]:
                best_complex = ("strong", conf, intent)

    if best_complex:
        return best_complex

    best_simple = None
    for pattern, intent, conf in SIMPLE_PATTERNS:
        if re.search(pattern, query_lower):
            if best_simple is None or conf > best_simple[1]:
                best_simple = ("fast", conf, intent)

    if best_simple:
        return best_simple

    # 规则无法匹配 → 升级到语义路由
    return None, 0.0, ""
