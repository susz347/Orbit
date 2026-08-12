from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelevantLocator(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)
    sheet: Optional[str] = None
    row_number: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_locator_field(self):
        if not any((self.heading, self.page, self.sheet, self.row_number)):
            raise ValueError("locator must contain at least one field")
        return self


class RetrievalEvaluationCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["rag-retrieval.v1"]
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    relevant_sources: tuple[str, ...] = Field(min_length=1)
    relevant_locators: tuple[RelevantLocator, ...] = Field(min_length=1)
    critical: bool = True
    tags: tuple[str, ...] = ()


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    distance: float
    chunk_id: str = Field(min_length=1)
    text: str
    source_path: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    page: Optional[int] = Field(default=None, ge=1)
    sheet: Optional[str] = None
    row_number: Optional[int] = Field(default=None, ge=1)
    chunk_index: int = Field(ge=0)


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    critical: bool
    source_hit_at_5: bool
    locator_hit_at_5: bool
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    ndcg_at_5: float = Field(ge=0.0, le=1.0)
    matched_chunk_id: Optional[str] = None
    matched_source_path: Optional[str] = None
    matched_rank: Optional[int] = Field(default=None, ge=1)
    duration_ms: int = Field(ge=0)


class EvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempt_id: str
    run_id: str
    status: Literal["passed", "rejected", "failed"]
    dataset_version: str
    source_hit_rate_at_5: float = Field(ge=0.0, le=1.0)
    locator_hit_rate_at_5: float = Field(ge=0.0, le=1.0)
    mean_reciprocal_rank: float = Field(ge=0.0, le=1.0)
    mean_ndcg_at_5: float = Field(ge=0.0, le=1.0)
    failures: tuple[str, ...] = ()
    expected_vector_count: int = Field(ge=0)
    actual_vector_count: int = Field(ge=0)
    empty_chunk_count: int = Field(default=0, ge=0)
    duplicate_chunk_count: int = Field(default=0, ge=0)
    error_category: Optional[str] = None
    duration_ms: int = Field(ge=0)
    cases: tuple[EvaluationCaseResult, ...] = ()
