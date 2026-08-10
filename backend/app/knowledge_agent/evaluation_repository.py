import json
from pathlib import Path

from .evaluation_models import EvaluationCaseResult, EvaluationReport
from .repository import _connect, _ensure_schema


def _ensure_evaluation_schema(connection) -> None:
    _ensure_schema(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_evaluation_runs (
            attempt_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            status TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            source_hit_rate_at_5 REAL NOT NULL,
            locator_hit_rate_at_5 REAL NOT NULL,
            mean_reciprocal_rank REAL NOT NULL,
            mean_ndcg_at_5 REAL NOT NULL,
            failures_json TEXT NOT NULL,
            expected_vector_count INTEGER NOT NULL,
            actual_vector_count INTEGER NOT NULL,
            empty_chunk_count INTEGER NOT NULL,
            duplicate_chunk_count INTEGER NOT NULL,
            error_category TEXT,
            duration_ms INTEGER NOT NULL,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (run_id) REFERENCES knowledge_agent_runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS knowledge_evaluation_cases (
            attempt_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            critical INTEGER NOT NULL,
            source_hit_at_5 INTEGER NOT NULL,
            locator_hit_at_5 INTEGER NOT NULL,
            reciprocal_rank REAL NOT NULL,
            ndcg_at_5 REAL NOT NULL,
            matched_chunk_id TEXT,
            matched_source_path TEXT,
            matched_rank INTEGER,
            duration_ms INTEGER NOT NULL,
            PRIMARY KEY (attempt_id, case_id),
            FOREIGN KEY (attempt_id) REFERENCES knowledge_evaluation_runs(attempt_id)
        );
        """
    )


def save_evaluation_report(
    report: EvaluationReport, *, database_path: Path, user_id: int | None
) -> None:
    with _connect(database_path) as connection:
        _ensure_evaluation_schema(connection)
        connection.execute(
            """
            INSERT INTO knowledge_evaluation_runs
                (attempt_id, run_id, user_id, status, dataset_version,
                 source_hit_rate_at_5, locator_hit_rate_at_5,
                 mean_reciprocal_rank, mean_ndcg_at_5, failures_json,
                 expected_vector_count, actual_vector_count,
                 empty_chunk_count, duplicate_chunk_count,
                 error_category, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.attempt_id, report.run_id, user_id, report.status,
                report.dataset_version, report.source_hit_rate_at_5,
                report.locator_hit_rate_at_5, report.mean_reciprocal_rank,
                report.mean_ndcg_at_5, json.dumps(report.failures),
                report.expected_vector_count, report.actual_vector_count,
                report.empty_chunk_count, report.duplicate_chunk_count,
                report.error_category, report.duration_ms,
            ),
        )
        connection.executemany(
            """
            INSERT INTO knowledge_evaluation_cases
                (attempt_id, case_id, critical, source_hit_at_5,
                 locator_hit_at_5, reciprocal_rank, ndcg_at_5,
                 matched_chunk_id, matched_source_path, matched_rank, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    report.attempt_id, item.case_id, int(item.critical),
                    int(item.source_hit_at_5), int(item.locator_hit_at_5),
                    item.reciprocal_rank, item.ndcg_at_5,
                    item.matched_chunk_id, item.matched_source_path,
                    item.matched_rank, item.duration_ms,
                )
                for item in report.cases
            ],
        )


def get_evaluation_report(
    run_id: str, *, database_path: Path, user_id: int | None
) -> EvaluationReport | None:
    with _connect(database_path) as connection:
        _ensure_evaluation_schema(connection)
        row = connection.execute(
            """
            SELECT attempt_id, run_id, status, dataset_version,
                   source_hit_rate_at_5, locator_hit_rate_at_5,
                   mean_reciprocal_rank, mean_ndcg_at_5, failures_json,
                   expected_vector_count, actual_vector_count,
                   empty_chunk_count, duplicate_chunk_count,
                   error_category, duration_ms
            FROM knowledge_evaluation_runs
            WHERE run_id = ? AND user_id IS ?
            """,
            (run_id, user_id),
        ).fetchone()
        if row is None:
            return None
        case_rows = connection.execute(
            """
            SELECT case_id, critical, source_hit_at_5, locator_hit_at_5,
                   reciprocal_rank, ndcg_at_5, matched_chunk_id,
                   matched_source_path, matched_rank, duration_ms
            FROM knowledge_evaluation_cases
            WHERE attempt_id = ? ORDER BY case_id
            """,
            (row[0],),
        ).fetchall()
    cases = tuple(
        EvaluationCaseResult(
            case_id=item[0], critical=bool(item[1]),
            source_hit_at_5=bool(item[2]), locator_hit_at_5=bool(item[3]),
            reciprocal_rank=item[4], ndcg_at_5=item[5],
            matched_chunk_id=item[6], matched_source_path=item[7],
            matched_rank=item[8], duration_ms=item[9],
        )
        for item in case_rows
    )
    return EvaluationReport(
        attempt_id=row[0], run_id=row[1], status=row[2], dataset_version=row[3],
        source_hit_rate_at_5=row[4], locator_hit_rate_at_5=row[5],
        mean_reciprocal_rank=row[6], mean_ndcg_at_5=row[7],
        failures=tuple(json.loads(row[8])), expected_vector_count=row[9],
        actual_vector_count=row[10], empty_chunk_count=row[11],
        duplicate_chunk_count=row[12], error_category=row[13],
        duration_ms=row[14], cases=cases,
    )
