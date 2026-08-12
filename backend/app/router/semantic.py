"""Layer 2：语义路由 — Embedding 匹配意图描述，处理规则无法覆盖的变体表达"""

import logging
from typing import Optional

from .rules import INTENT_TAXONOMY

logger = logging.getLogger(__name__)

_intent_descriptions = None
_intent_embeddings = None


def _build_intent_embeddings():
    """惰性构建意图描述的 embedding（首次调用时）"""
    global _intent_descriptions, _intent_embeddings

    if _intent_embeddings is not None:
        return

    from ..embed import encode

    _intent_descriptions = []
    for domain_name, domain_info in INTENT_TAXONOMY.items():
        for intent_name, intent_desc in domain_info["intents"].items():
            full_desc = f"{domain_info['domain']} - {intent_name}: {intent_desc}"
            _intent_descriptions.append({
                "domain": domain_name,
                "intent": intent_name,
                "tier": domain_info["default_tier"],
                "desc": full_desc,
            })

    if _intent_descriptions:
        desc_texts = [d["desc"] for d in _intent_descriptions]
        _intent_embeddings = encode(desc_texts)


def _semantic_classify(query: str) -> tuple[Optional[str], float, str]:
    """
    语义路由：用 Embedding 匹配用户查询与意图描述。
    返回: (tier, confidence, intent_name) 或 (None, 0, "") 表示语义也不确定
    """
    try:
        _build_intent_embeddings()
    except Exception:
        logger.debug("Intent embed build skipped (fallback to regex only)")
        return None, 0.0, ""

    if not _intent_embeddings:
        return None, 0.0, ""

    from ..embed import encode

    query_embedding = encode([query])
    if not query_embedding:
        return None, 0.0, ""

    query_emb = query_embedding[0]

    # cosine similarity
    best_match = None
    best_score = 0.0
    norm_q = sum(x * x for x in query_emb) ** 0.5

    for i, intent_emb in enumerate(_intent_embeddings):
        if len(intent_emb) != len(query_emb):
            continue
        dot = sum(a * b for a, b in zip(query_emb, intent_emb))
        norm_i = sum(x * x for x in intent_emb) ** 0.5
        if norm_q == 0 or norm_i == 0:
            continue
        score = dot / (norm_q * norm_i)
        if score > best_score:
            best_score = score
            best_match = _intent_descriptions[i]

    # 阈值判断
    SEMANTIC_HIGH_THRESHOLD = 0.45   # 高于此值认为匹配
    SEMANTIC_LOW_THRESHOLD = 0.25    # 低于此值认为 unknown

    if best_match and best_score >= SEMANTIC_HIGH_THRESHOLD:
        return best_match["tier"], best_score, best_match["intent"]
    elif best_score >= SEMANTIC_LOW_THRESHOLD:
        # 模糊匹配 → LLM 分类兜底
        return None, best_score, ""
    else:
        return "unknown", best_score, "unknown"


def _intent_similarity(query: str, intent_name: str) -> Optional[float]:
    """R2: 计算 query 与指定意图描述的 Embedding 相似度。

    用于 Hybrid Route——规则命中后验证语义一致性：
    "什么是 Docker" 命中 definition → 语义也像 definition → hybrid 分高 → 直接采用
    "帮我写 Dockerfile" 命中 definition → 语义更像 code_gen → hybrid 分低 → 走 LLM 兜底

    返回 cosine 相似度（0-1），失败返回 None。
    """
    try:
        _build_intent_embeddings()
    except Exception:
        logger.debug("Intent embed build skipped")
        return None

    if not _intent_embeddings:
        return None

    # 定位目标意图的 embedding
    target_index = None
    for i, d in enumerate(_intent_descriptions):
        if d["intent"] == intent_name:
            target_index = i
            break
    if target_index is None:
        return None

    from ..embed import encode

    query_embedding = encode([query])
    if not query_embedding:
        return None
    query_emb = query_embedding[0]
    intent_emb = _intent_embeddings[target_index]

    if len(intent_emb) != len(query_emb):
        return None

    dot = sum(a * b for a, b in zip(query_emb, intent_emb))
    norm_q = sum(x * x for x in query_emb) ** 0.5
    norm_i = sum(x * x for x in intent_emb) ** 0.5
    if norm_q == 0 or norm_i == 0:
        return None
    return dot / (norm_q * norm_i)
