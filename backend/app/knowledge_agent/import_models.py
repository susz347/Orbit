from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ImportStatus = Literal["uploading", "validating", "ready", "failed"]


class ImportFileRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    relative_path: str
    size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    status: Literal["uploaded"] = "uploaded"


class ImportBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    import_id: str
    user_id: int | None
    status: ImportStatus
    file_count: int = Field(ge=0)
    total_size: int = Field(ge=0)
    manifest_hash: str | None = None
    relative_path: str | None = None
    error_category: str | None = None
    created_at: str
    completed_at: str | None = None
    files: tuple[ImportFileRecord, ...] = ()
