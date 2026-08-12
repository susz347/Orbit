"""Router 插件化（R3）：BaseRouter 抽象基类 + RouterPipeline 组合。

参考 ulab-uiuc/LLMRouter 的 MetaRouter 插件体系：
- 每个路由策略是一个独立插件（RegexRouter / SemanticRouter / LLMRouter）
- 用户可自定义路由器（继承 BaseRouter）插入 pipeline，无需改框架
- pipeline 按顺序尝试，首个 conf >= 自身 threshold 的决策生效

用法:
    pipeline = RouterPipeline([RegexRouter(), SemanticRouter(), LLMRouter()])
    tier, conf, intent = pipeline.route("什么是 Docker")

    # 自定义插件（放 custom_routers/ 目录即可复用）
    class MyRouter(BaseRouter):
        name = "my_router"
        confidence_threshold = 0.5
        def classify(self, query):
            if "特殊标记" in query:
                return "fast", 0.9, "special"
            return None, 0.0, ""
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseRouter(ABC):
    """路由器基类。"""

    name: str = "base"
    confidence_threshold: float = 0.0

    @abstractmethod
    def classify(self, query: str) -> tuple[Optional[str], float, str]:
        """分类 query。

        返回 (tier, confidence, intent)：
        - tier: fast | balanced | strong | unknown | Optional[out_of_scope]（未命中）
        - confidence: 0.0 ~ 1.0
        - intent: 意图名（未命中时为空字符串）
        """
        raise NotImplementedError


class RouterPipeline:
    """可配置的路由流水线。"""

    def __init__(self, routers: Optional[list[BaseRouter]] = None):
        self.routers: list[BaseRouter] = list(routers or [])

    def add(self, router: BaseRouter) -> "RouterPipeline":
        """追加一个路由器。"""
        self.routers.append(router)
        return self

    def route(self, query: str) -> tuple[str, float, str]:
        """依次尝试每个路由器，首个 conf >= threshold 且 tier 非 None 的决策生效。

        全部未命中时返回 fallback（balanced, 0.3, "fallback"）。
        """
        for router in self.routers:
            try:
                tier, conf, intent = router.classify(query)
            except Exception:
                continue
            if tier and conf >= router.confidence_threshold:
                return tier, conf, intent
        return "balanced", 0.3, "fallback"


def build_default_pipeline() -> RouterPipeline:
    """构建默认三层流水线：规则 → 语义 → LLM。

    与 service.route_model 的默认行为一致，但可被用户替换任一层。
    """
    from .plugins import RegexRouter, SemanticRouter, LLMRouter
    return RouterPipeline([RegexRouter(), SemanticRouter(), LLMRouter()])
