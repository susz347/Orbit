import time
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from .approval import RunNotFound, RunStateConflict
from .evaluation_models import (
    EvaluationCaseResult,
    EvaluationReport,
    RelevantLocator,
    RetrievalEvaluationCase,
    RetrievedChunk,
)
from .evaluation_repository import get_evaluation_report, save_evaluation_report
from .repository import get_run, transition_run
from .retrieval_metrics import (
    CaseMetric,
    evaluate_gate,
    ndcg_at_k,
    reciprocal_rank,
)
from .run_state import InvalidRunTransition
from .staging_store import EmbeddingFailed, StagingStore, StorageFailed


def _locator_matches(locator: RelevantLocator, chunk: RetrievedChunk) -> bool:
    return all(
        (
            locator.heading is None or locator.heading in chunk.heading_path,
            locator.page is None or locator.page == chunk.page,
            locator.sheet is None or locator.sheet == chunk.sheet,
            locator.row_number is None or locator.row_number == chunk.row_number,
        )
    )


def _failed_report(
    run_id: str, expected: int, actual: int, category: str, duration_ms: int
) -> EvaluationReport:
    return EvaluationReport(
        attempt_id=uuid4().hex, run_id=run_id, status="failed",
        dataset_version="rag-retrieval.v1", source_hit_rate_at_5=0.0,
        locator_hit_rate_at_5=0.0, mean_reciprocal_rank=0.0,
        mean_ndcg_at_5=0.0, failures=(category,),
        expected_vector_count=expected, actual_vector_count=actual,
        error_category=category, duration_ms=duration_ms,
    )


def evaluate_run(
    run_id: str,
    *,
    database_path: Path,
    user_id: int | None,
    cases: Sequence[RetrievalEvaluationCase],
    staging_store: StagingStore,
) -> EvaluationReport:
    existing = get_evaluation_report(
        run_id, database_path=database_path, user_id=user_id
    )
    if existing is not None:
        return existing
    run = get_run(run_id, database_path=database_path, user_id=user_id)
    if run is None:
        raise RunNotFound(run_id)
    if run.status != "evaluating":
        raise InvalidRunTransition(f"只有 evaluating Run 可以评测，当前为 {run.status}")

    started = time.perf_counter()
    try:
        exists = staging_store.exists(run_id=run_id, user_id=user_id)
        actual_count = (
            staging_store.count(run_id=run_id, user_id=user_id) if exists else 0
        )
    except EmbeddingFailed:
        exists, actual_count = True, 0
        category = "embedding_error"
    except StorageFailed:
        exists, actual_count = True, 0
        category = "storage_error"
    else:
        category = None
    if category or not exists or actual_count != run.chunk_count:
        report = _failed_report(
            run_id, run.chunk_count, actual_count,
            category or "evaluation_input_error",
            int((time.perf_counter() - started) * 1000),
        )
        save_evaluation_report(report, database_path=database_path, user_id=user_id)
        if not transition_run(
            run_id, target="failed", expected="evaluating",
            database_path=database_path, user_id=user_id,
        ):
            raise RunStateConflict(run_id)
        return report

    case_results: list[EvaluationCaseResult] = []
    metrics: list[CaseMetric] = []
    try:
        for case in cases:
            case_started = time.perf_counter()
            chunks = staging_store.query(
                run_id=run_id, user_id=user_id,
                question=case.question, top_k=5,
            )
            source_flags = [
                chunk.source_path in case.relevant_sources for chunk in chunks
            ]
            relevance = [
                source_match and any(
                    _locator_matches(locator, chunk)
                    for locator in case.relevant_locators
                )
                for source_match, chunk in zip(source_flags, chunks)
            ]
            matched = next(
                (chunk for chunk, relevant in zip(chunks, relevance) if relevant),
                None,
            )
            metric = CaseMetric(
                case_id=case.id, critical=case.critical,
                source_hit_at_5=any(source_flags),
                locator_hit_at_5=any(relevance),
                reciprocal_rank=reciprocal_rank(relevance),
                ndcg_at_5=ndcg_at_k(relevance, 5),
            )
            metrics.append(metric)
            case_results.append(
                EvaluationCaseResult(
                    **metric.__dict__,
                    matched_chunk_id=matched.chunk_id if matched else None,
                    matched_source_path=matched.source_path if matched else None,
                    matched_rank=matched.rank if matched else None,
                    duration_ms=int((time.perf_counter() - case_started) * 1000),
                )
            )
    except EmbeddingFailed:
        category = "embedding_error"
    except StorageFailed:
        category = "storage_error"
    except Exception:
        category = "internal_error"
    if category:
        report = _failed_report(
            run_id, run.chunk_count, actual_count, category,
            int((time.perf_counter() - started) * 1000),
        )
        save_evaluation_report(report, database_path=database_path, user_id=user_id)
        if not transition_run(
            run_id, target="failed", expected="evaluating",
            database_path=database_path, user_id=user_id,
        ):
            raise RunStateConflict(run_id)
        return report

    gate = evaluate_gate(
        metrics, empty_chunk_count=0, duplicate_chunk_count=0,
        counts_match=actual_count == run.chunk_count,
    )
    status = "passed" if gate.passed else "rejected"
    report = EvaluationReport(
        attempt_id=uuid4().hex, run_id=run_id, status=status,
        dataset_version="rag-retrieval.v1",
        source_hit_rate_at_5=gate.source_hit_rate_at_5,
        locator_hit_rate_at_5=gate.locator_hit_rate_at_5,
        mean_reciprocal_rank=gate.mean_reciprocal_rank,
        mean_ndcg_at_5=gate.mean_ndcg_at_5,
        failures=gate.failures, expected_vector_count=run.chunk_count,
        actual_vector_count=actual_count,
        duration_ms=int((time.perf_counter() - started) * 1000),
        cases=tuple(case_results),
    )
    save_evaluation_report(report, database_path=database_path, user_id=user_id)
    if status == "rejected" and not transition_run(
        run_id, target="rejected", expected="evaluating",
        database_path=database_path, user_id=user_id,
    ):
        raise RunStateConflict(run_id)
    return report
