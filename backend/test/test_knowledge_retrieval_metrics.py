import math

import pytest

from app.knowledge_agent.retrieval_metrics import (
    CaseMetric,
    evaluate_gate,
    hit_at_k,
    ndcg_at_k,
    reciprocal_rank,
)


def test_ranked_metrics_reward_early_relevant_result():
    relevance = [False, True, False, False, False]

    assert hit_at_k(relevance, 5) is True
    assert reciprocal_rank(relevance) == 0.5
    assert ndcg_at_k(relevance, 5) == pytest.approx(1 / math.log2(3))


def test_gate_requires_every_critical_case():
    reports = (
        CaseMetric(
            case_id="critical",
            critical=True,
            source_hit_at_5=False,
            locator_hit_at_5=False,
            reciprocal_rank=0.0,
            ndcg_at_5=0.0,
        ),
    )

    decision = evaluate_gate(
        reports,
        empty_chunk_count=0,
        duplicate_chunk_count=0,
        counts_match=True,
    )

    assert decision.passed is False
    assert "critical_source_miss:critical" in decision.failures


def test_gate_passes_complete_high_quality_results():
    reports = tuple(
        CaseMetric(
            case_id=f"case-{index}",
            critical=True,
            source_hit_at_5=True,
            locator_hit_at_5=True,
            reciprocal_rank=1.0,
            ndcg_at_5=1.0,
        )
        for index in range(5)
    )

    decision = evaluate_gate(
        reports,
        empty_chunk_count=0,
        duplicate_chunk_count=0,
        counts_match=True,
    )

    assert decision.passed is True
    assert decision.failures == ()
