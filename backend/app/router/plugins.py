"""内置路由器插件（R3）：包装既有三层实现为可插拔策略。

- RegexRouter:   Layer 1 规则引擎（微秒级）
- SemanticRouter: Layer 2 语义路由（Embedding 意图匹配）
- LLMRouter:      Layer 3 LLM 分类（边缘案例兜底）

每个插件 conf 达到自身 confidence_threshold 才被 pipeline 采用。
"""

from typing import Optional

from .base import BaseRouter
from .rules import _regex_classify
from .semantic import _semantic_classify
from .llm import _llm_classify


class RegexRouter(BaseRouter):
    """规则引擎插件。"""

    name = "regex"
    confidence_threshold = 0.7  # 与 service.route_model 的硬编码一致

    def classify(self, query: str) -> tuple[Optional[str], float, str]:
        tier, conf, intent = _regex_classify(query)
        return tier, conf or 0.0, intent or ""


class SemanticRouter(BaseRouter):
    """语义路由插件。"""

    name = "semantic"
    confidence_threshold = 0.45  # 与 service.route_model 的语义高置信阈值一致

    def classify(self, query: str) -> tuple[Optional[str], float, str]:
        tier, conf, intent = _semantic_classify(query)
        return tier, conf or 0.0, intent or ""


class LLMRouter(BaseRouter):
    """LLM 分类插件（兜底，总是执行）。"""

    name = "llm"
    confidence_threshold = 0.0  # LLM 兜底：只要被调用就采纳其结果

    def classify(self, query: str) -> tuple[Optional[str], float, str]:
        tier, conf, intent = _llm_classify(query)
        return tier, conf or 0.0, intent or ""
