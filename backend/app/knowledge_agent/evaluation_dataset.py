import json
from pathlib import Path

from pydantic import ValidationError

from .evaluation_models import RetrievalEvaluationCase


class EvaluationDatasetError(ValueError):
    """Sanitized invalid evaluation dataset category."""


def load_evaluation_cases(path: Path) -> tuple[RetrievalEvaluationCase, ...]:
    cases: list[RetrievalEvaluationCase] = []
    seen_ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvaluationDatasetError("dataset_unavailable") from exc

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationDatasetError("invalid_jsonl") from exc
        try:
            case = RetrievalEvaluationCase.model_validate(payload)
        except ValidationError as exc:
            raise EvaluationDatasetError("invalid_case") from exc
        if case.id in seen_ids:
            raise EvaluationDatasetError("duplicate_case_id")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise EvaluationDatasetError("empty_dataset")
    return tuple(cases)
