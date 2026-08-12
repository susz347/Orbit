from typing import Literal, Optional

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
    user_id: Optional[int]
    status: ImportStatus
    file_count: int = Field(ge=0)
    total_size: int = Field(ge=0)
    manifest_hash: Optional[str] = None
    relative_path: Optional[str] = None
    error_category: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    files: tuple[ImportFileRecord, ...] = ()
