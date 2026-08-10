import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class EvaluationPolicy:
    top_k: int = 5
    minimum_source_hit_rate: float = 1.0
    minimum_locator_hit_rate: float = 0.9
    minimum_mrr: float = 0.8
    minimum_ndcg: float = 0.9


@dataclass(frozen=True)
class CaseMetric:
    case_id: str
    critical: bool
    source_hit_at_5: bool
    locator_hit_at_5: bool
    reciprocal_rank: float
    ndcg_at_5: float


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    failures: tuple[str, ...]
    source_hit_rate_at_5: float
    locator_hit_rate_at_5: float
    mean_reciprocal_rank: float
    mean_ndcg_at_5: float


def hit_at_k(relevance: Sequence[bool], k: int) -> bool:
    return any(relevance[:k])


def reciprocal_rank(relevance: Sequence[bool]) -> float:
    for rank, relevant in enumerate(relevance, start=1):
        if relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(relevance: Sequence[bool], k: int) -> float:
    limited = relevance[:k]
    relevant_count = sum(limited)
    if relevant_count == 0:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, relevant in enumerate(limited, start=1)
        if relevant
    )
    ideal = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(1, relevant_count + 1)
    )
    return dcg / ideal


def evaluate_gate(
    reports: Sequence[CaseMetric],
    *,
    empty_chunk_count: int,
    duplicate_chunk_count: int,
    counts_match: bool,
    policy: EvaluationPolicy = EvaluationPolicy(),
) -> GateDecision:
    if not reports:
        return GateDecision(False, ("no_cases",), 0.0, 0.0, 0.0, 0.0)

    size = len(reports)
    source_rate = sum(item.source_hit_at_5 for item in reports) / size
    locator_rate = sum(item.locator_hit_at_5 for item in reports) / size
    mean_mrr = sum(item.reciprocal_rank for item in reports) / size
    mean_ndcg = sum(item.ndcg_at_5 for item in reports) / size
    failures: list[str] = []

    for item in reports:
        if item.critical and not item.source_hit_at_5:
            failures.append(f"critical_source_miss:{item.case_id}")
        if item.critical and not item.locator_hit_at_5:
            failures.append(f"critical_locator_miss:{item.case_id}")
    if source_rate < policy.minimum_source_hit_rate:
        failures.append("source_hit_rate_below_threshold")
    if locator_rate < policy.minimum_locator_hit_rate:
        failures.append("locator_hit_rate_below_threshold")
    if mean_mrr < policy.minimum_mrr:
        failures.append("mrr_below_threshold")
    if mean_ndcg < policy.minimum_ndcg:
        failures.append("ndcg_below_threshold")
    if empty_chunk_count:
        failures.append("empty_chunks")
    if duplicate_chunk_count:
        failures.append("duplicate_chunks")
    if not counts_match:
        failures.append("vector_count_mismatch")

    return GateDecision(
        passed=not failures,
        failures=tuple(failures),
        source_hit_rate_at_5=source_rate,
        locator_hit_rate_at_5=locator_rate,
        mean_reciprocal_rank=mean_mrr,
        mean_ndcg_at_5=mean_ndcg,
    )
