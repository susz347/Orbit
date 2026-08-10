from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelevantLocator(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str | None = None
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    row_number: int | None = Field(default=None, ge=1)

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
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    row_number: int | None = Field(default=None, ge=1)
    chunk_index: int = Field(ge=0)
