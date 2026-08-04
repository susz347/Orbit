"""统一入口：混合路由 — 规则引擎 → 语义路由 → LLM 分类 → 检索置信度降级"""

from .models import RouteDecision
from .rules import _regex_classify, MODEL_PRESETS, INTENT_TAXONOMY
from .semantic import _semantic_classify
from .llm import _llm_classify

CLARIFY_THRESHOLD = 0.45    # 低于此置信度时追问用户
CONFIDENCE_DOWNGRADE = 0.7  # 检索高置信度自动降级到 fast


def route_model(query: str, retrieval_scores: list[float] = None) -> RouteDecision:
    """
    混合路由：规则引擎 → 语义路由 → LLM 分类 → 检索置信度降级

    返回 RouteDecision（结构化路由决策）
    """
    tier = "balanced"
    confidence = 0.5
    intent = "balanced"
    reason = ""

    # ── Layer 1: 规则引擎 ──
    rule_tier, rule_conf, rule_intent = _regex_classify(query)

    if rule_tier and rule_conf >= 0.7:
        # 规则高置信度 → 直接采用
        tier, confidence, intent = rule_tier, rule_conf, rule_intent
        reason = f"规则匹配（{intent}, conf={confidence:.0%}）"
    elif rule_tier:
        # 规则低置信度 → 保留候选，继续语义路由
        tier, confidence, intent = rule_tier, rule_conf, rule_intent
        reason = f"规则匹配（{intent}, conf={confidence:.0%}）→ 语义确认中"

        # 同时尝试语义路由
        sem_tier, sem_conf, sem_intent = _semantic_classify(query)
        if sem_tier and sem_conf > rule_conf:
            tier, confidence, intent = sem_tier, sem_conf, sem_intent
            reason = f"语义路由覆盖（{intent}, conf={sem_conf:.0%}，超越规则 {rule_conf:.0%}）"
    elif rule_tier is None:
        # 规则完全未匹配 → 语义路由
        sem_tier, sem_conf, sem_intent = _semantic_classify(query)
        if sem_tier and sem_conf >= 0.45:
            tier, confidence, intent = sem_tier, sem_conf, sem_intent
            reason = f"语义路由命中（{intent}, conf={sem_conf:.0%}）"
        elif sem_conf >= 0.25:
            # 语义模糊 → LLM 分类
            llm_tier, llm_conf, llm_intent = _llm_classify(query)
            tier, confidence, intent = llm_tier, llm_conf, llm_intent
            reason = f"LLM 分类（{intent}, conf={llm_conf:.0%}）"
        else:
            # 完全不确定 → unknown
            tier, confidence, intent = "unknown", 0.0, "unknown"
            reason = "规则+语义均无法识别，标记为 unknown"

    # ── 检索置信度降级 ──
    if retrieval_scores and len(retrieval_scores) > 0:
        top_score = retrieval_scores[0]
        if top_score > CONFIDENCE_DOWNGRADE and tier not in ("strong", "unknown", "out_of_scope"):
            tier = "fast"
            reason += f" + 检索高置信度({top_score:.0%})→降级至 fast"

    # ── 置信度门控 ──
    needs_clarification = False
    clarification_question = ""

    if tier == "unknown":
        needs_clarification = True
        clarification_question = "抱歉，我不太确定你想做什么。能再描述一下吗？"
    elif confidence < CLARIFY_THRESHOLD and tier != "out_of_scope":
        needs_clarification = True
        clarification_question = f"你的意思是「{INTENT_TAXONOMY.get(intent, {}).get('intents', {}).get(intent, '查询')}」吗？请确认一下。"

    if tier == "out_of_scope":
        needs_clarification = True
        clarification_question = "抱歉，我只能回答知识库相关的问题。请尝试问我关于文档内容的问题。"

    # ── 构建决策 ──
    preset = MODEL_PRESETS.get(tier, MODEL_PRESETS["balanced"])
    return RouteDecision(
        tier=tier,
        model=preset["model"],
        max_tokens=preset["max_tokens"],
        temperature=preset["temperature"],
        confidence=round(confidence, 4),
        reason=reason,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question if needs_clarification else "",
        intent=intent,
    )


def detect_intent(query: str) -> str:
    """意图识别（兼容旧接口），返回 'simple' | 'complex' | 'balanced' | 'unknown'"""
    decision = route_model(query)
    mapping = {
        "fast": "simple",
        "balanced": "balanced",
        "strong": "complex",
        "unknown": "unknown",
        "out_of_scope": "unknown",
    }
    return mapping.get(decision.tier, "balanced")
