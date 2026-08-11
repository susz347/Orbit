import io

import pytest

from app.knowledge_agent.imports import (
    ImportConflict,
    ImportValidationError,
    complete_import,
    create_import,
    delete_import,
    get_import,
    upload_import_file,
)


def test_import_is_tenant_scoped_and_freezes_an_immutable_manifest(tmp_path):
    database = tmp_path / "audit.sqlite3"
    root = tmp_path / "knowledge"
    batch = create_import(database_path=database, knowledge_root=root, user_id=7)
    upload_import_file(
        batch.import_id,
        relative_path="handbook/policy.md",
        stream=io.BytesIO(b"# Policy"),
        database_path=database,
        knowledge_root=root,
        user_id=7,
    )

    ready = complete_import(
        batch.import_id,
        database_path=database,
        knowledge_root=root,
        user_id=7,
    )

    assert ready.status == "ready"
    assert ready.relative_path.startswith("imports/ready/")
    assert ready.manifest_hash
    assert (root / ready.relative_path / "handbook" / "policy.md").read_bytes() == b"# Policy"
    assert get_import(batch.import_id, database_path=database, user_id=8) is None
    with pytest.raises(ImportConflict, match="import_not_uploading"):
        upload_import_file(
            batch.import_id,
            relative_path="new.md",
            stream=io.BytesIO(b"new"),
            database_path=database,
            knowledge_root=root,
            user_id=7,
        )


@pytest.mark.parametrize(
    "path,error",
    [
        ("../secret.md", "invalid_relative_path"),
        ("/absolute.md", "invalid_relative_path"),
        ("C:/drive.md", "invalid_relative_path"),
        ("folder\\escape.md", "invalid_relative_path"),
        ("notes.txt", "unsupported_file_type"),
    ],
)
def test_import_rejects_unsafe_or_unsupported_paths(tmp_path, path, error):
    database = tmp_path / "audit.sqlite3"
    root = tmp_path / "knowledge"
    batch = create_import(database_path=database, knowledge_root=root, user_id=7)

    with pytest.raises(ImportValidationError, match=error):
        upload_import_file(
            batch.import_id,
            relative_path=path,
            stream=io.BytesIO(b"data"),
            database_path=database,
            knowledge_root=root,
            user_id=7,
        )


def test_import_never_overwrites_and_empty_batch_cannot_complete(tmp_path):
    database = tmp_path / "audit.sqlite3"
    root = tmp_path / "knowledge"
    batch = create_import(database_path=database, knowledge_root=root, user_id=7)
    with pytest.raises(ImportValidationError, match="empty_import"):
        complete_import(
            batch.import_id, database_path=database, knowledge_root=root, user_id=7
        )

    upload_import_file(
        batch.import_id,
        relative_path="same.pdf",
        stream=io.BytesIO(b"first"),
        database_path=database,
        knowledge_root=root,
        user_id=7,
    )
    with pytest.raises(ImportConflict, match="duplicate_relative_path"):
        upload_import_file(
            batch.import_id,
            relative_path="same.pdf",
            stream=io.BytesIO(b"second"),
            database_path=database,
            knowledge_root=root,
            user_id=7,
        )


def test_unfrozen_import_can_be_deleted_but_ready_import_cannot(tmp_path):
    database = tmp_path / "audit.sqlite3"
    root = tmp_path / "knowledge"
    disposable = create_import(database_path=database, knowledge_root=root, user_id=7)
    delete_import(
        disposable.import_id,
        database_path=database,
        knowledge_root=root,
        user_id=7,
    )
    assert get_import(disposable.import_id, database_path=database, user_id=7) is None

    frozen = create_import(database_path=database, knowledge_root=root, user_id=7)
    upload_import_file(
        frozen.import_id,
        relative_path="one.xlsx",
        stream=io.BytesIO(b"xlsx"),
        database_path=database,
        knowledge_root=root,
        user_id=7,
    )
    complete_import(
        frozen.import_id,
        database_path=database,
        knowledge_root=root,
        user_id=7,
    )
    with pytest.raises(ImportConflict, match="ready_import_is_immutable"):
        delete_import(
            frozen.import_id,
            database_path=database,
            knowledge_root=root,
            user_id=7,
        )
