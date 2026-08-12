
import hashlib
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Optional

from .import_models import ImportBatch, ImportFileRecord
from .import_repository import add_file, create_batch, delete_batch, get_batch, mark_ready


ALLOWED_EXTENSIONS = {".md", ".docx", ".xlsx", ".pdf"}
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_BATCH_SIZE = 250 * 1024 * 1024
MAX_FILE_COUNT = 500
CHUNK_SIZE = 1024 * 1024


class ImportErrorBase(RuntimeError):
    pass


class ImportNotFound(ImportErrorBase):
    pass


class ImportConflict(ImportErrorBase):
    pass


class ImportValidationError(ImportErrorBase):
    pass


def _tenant_key(user_id: Optional[int]) -> str:
    return hashlib.sha256(f"tenant:{user_id}".encode()).hexdigest()[:16]


def _staging_dir(root: Path, user_id: Optional[int], import_id: str) -> Path:
    return root / "imports" / ".staging" / _tenant_key(user_id) / import_id


def _ready_dir(root: Path, user_id: Optional[int], import_id: str) -> Path:
    return root / "imports" / "ready" / _tenant_key(user_id) / import_id


def _normalize_relative_path(value: str) -> str:
    if not value or "\x00" in value or "\\" in value or ":" in value:
        raise ImportValidationError("invalid_relative_path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ImportValidationError("invalid_relative_path")
    normalized = path.as_posix()
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImportValidationError("unsupported_file_type")
    return normalized


def create_import(*, database_path: Path, knowledge_root: Path, user_id: Optional[int]) -> ImportBatch:
    import_id = uuid.uuid4().hex
    batch = create_batch(import_id, database_path=database_path, user_id=user_id)
    _staging_dir(knowledge_root, user_id, import_id).mkdir(parents=True, exist_ok=False)
    return batch


def get_import(import_id: str, *, database_path: Path, user_id: Optional[int]) -> Optional[ImportBatch]:
    return get_batch(import_id, database_path=database_path, user_id=user_id)


def upload_import_file(import_id: str, *, relative_path: str, stream: BinaryIO, database_path: Path, knowledge_root: Path, user_id: Optional[int]) -> ImportBatch:
    normalized = _normalize_relative_path(relative_path)
    batch = get_batch(import_id, database_path=database_path, user_id=user_id)
    if batch is None:
        raise ImportNotFound("import_not_found")
    if batch.status != "uploading":
        raise ImportConflict("import_not_uploading")
    if batch.file_count >= MAX_FILE_COUNT:
        raise ImportValidationError("file_count_limit")
    target = _staging_dir(knowledge_root, user_id, import_id) / Path(*PurePosixPath(normalized).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := stream.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise ImportValidationError("file_size_limit")
                if batch.total_size + size > MAX_BATCH_SIZE:
                    raise ImportValidationError("batch_size_limit")
                digest.update(chunk)
                output.write(chunk)
    except FileExistsError as exc:
        raise ImportConflict("duplicate_relative_path") from exc
    except Exception:
        target.unlink(missing_ok=True)
        raise
    record = ImportFileRecord(relative_path=normalized, size=size, sha256=digest.hexdigest())
    if not add_file(import_id, record, database_path=database_path, user_id=user_id):
        target.unlink(missing_ok=True)
        latest = get_batch(import_id, database_path=database_path, user_id=user_id)
        if latest is None:
            raise ImportNotFound("import_not_found")
        if latest.status != "uploading":
            raise ImportConflict("import_not_uploading")
        raise ImportConflict("duplicate_relative_path")
    return get_batch(import_id, database_path=database_path, user_id=user_id)  # type: ignore[return-value]


def complete_import(import_id: str, *, database_path: Path, knowledge_root: Path, user_id: Optional[int]) -> ImportBatch:
    batch = get_batch(import_id, database_path=database_path, user_id=user_id)
    if batch is None:
        raise ImportNotFound("import_not_found")
    if batch.status != "uploading":
        raise ImportConflict("import_not_uploading")
    if not batch.files:
        raise ImportValidationError("empty_import")
    manifest = "\n".join(f"{item.relative_path}\0{item.size}\0{item.sha256}" for item in batch.files)
    manifest_hash = hashlib.sha256(manifest.encode()).hexdigest()
    source = _staging_dir(knowledge_root, user_id, import_id)
    destination = _ready_dir(knowledge_root, user_id, import_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)
    relative_path = destination.relative_to(knowledge_root).as_posix()
    if not mark_ready(import_id, database_path=database_path, user_id=user_id, manifest_hash=manifest_hash, relative_path=relative_path):
        destination.replace(source)
        raise ImportConflict("import_not_uploading")
    return get_batch(import_id, database_path=database_path, user_id=user_id)  # type: ignore[return-value]


def delete_import(import_id: str, *, database_path: Path, knowledge_root: Path, user_id: Optional[int]) -> None:
    batch = get_batch(import_id, database_path=database_path, user_id=user_id)
    if batch is None:
        raise ImportNotFound("import_not_found")
    if batch.status == "ready":
        raise ImportConflict("ready_import_is_immutable")
    if not delete_batch(import_id, database_path=database_path, user_id=user_id):
        raise ImportConflict("import_delete_conflict")
    shutil.rmtree(_staging_dir(knowledge_root, user_id, import_id), ignore_errors=True)
