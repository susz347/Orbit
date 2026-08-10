from pathlib import Path

import pytest

from app.knowledge_agent.evaluation_dataset import (
    EvaluationDatasetError,
    load_evaluation_cases,
)


QUESTIONS = Path(__file__).resolve().parents[2] / "knowledge" / "evals" / "questions.jsonl"
VALID_LINE = (
    '{"schema_version":"rag-retrieval.v1","id":"case-1",'
    '"question":"Question?","expected_answer":"Answer",'
    '"relevant_sources":["doc.md"],'
    '"relevant_locators":[{"heading":"Section"}],"critical":true}'
)


def test_loads_versioned_unique_retrieval_cases():
    cases = load_evaluation_cases(QUESTIONS)

    assert len(cases) >= 5
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.schema_version == "rag-retrieval.v1" for case in cases)
    assert all(case.relevant_sources for case in cases)


def test_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(VALID_LINE + "\n" + VALID_LINE, encoding="utf-8")

    with pytest.raises(EvaluationDatasetError, match="duplicate_case_id"):
        load_evaluation_cases(path)
