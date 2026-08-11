from __future__ import annotations

import sqlite3
from pathlib import Path

from .import_models import ImportBatch, ImportFileRecord


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_imports (
            import_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 0, total_size INTEGER NOT NULL DEFAULT 0,
            manifest_hash TEXT, relative_path TEXT, error_category TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS knowledge_import_files (
            import_id TEXT NOT NULL, relative_path TEXT NOT NULL, size INTEGER NOT NULL,
            sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'uploaded',
            PRIMARY KEY (import_id, relative_path),
            FOREIGN KEY (import_id) REFERENCES knowledge_imports(import_id) ON DELETE CASCADE
        );
        """
    )


def create_batch(import_id: str, *, database_path: Path, user_id: int | None) -> ImportBatch:
    with _connect(database_path) as connection:
        _ensure_schema(connection)
        connection.execute(
            "INSERT INTO knowledge_imports (import_id, user_id, status) VALUES (?, ?, 'uploading')",
            (import_id, user_id),
        )
    return get_batch(import_id, database_path=database_path, user_id=user_id)  # type: ignore[return-value]


def get_batch(import_id: str, *, database_path: Path, user_id: int | None) -> ImportBatch | None:
    with _connect(database_path) as connection:
        _ensure_schema(connection)
        row = connection.execute(
            """SELECT import_id, user_id, status, file_count, total_size,
                      manifest_hash, relative_path, error_category, created_at, completed_at
               FROM knowledge_imports WHERE import_id = ? AND user_id IS ?""",
            (import_id, user_id),
        ).fetchone()
        if row is None:
            return None
        files = connection.execute(
            """SELECT relative_path, size, sha256, status FROM knowledge_import_files
               WHERE import_id = ? ORDER BY relative_path""",
            (import_id,),
        ).fetchall()
    return ImportBatch(
        import_id=row[0], user_id=row[1], status=row[2], file_count=row[3],
        total_size=row[4], manifest_hash=row[5], relative_path=row[6],
        error_category=row[7], created_at=row[8], completed_at=row[9],
        files=tuple(ImportFileRecord(relative_path=f[0], size=f[1], sha256=f[2], status=f[3]) for f in files),
    )


def add_file(import_id: str, record: ImportFileRecord, *, database_path: Path, user_id: int | None) -> bool:
    with _connect(database_path) as connection:
        _ensure_schema(connection)
        row = connection.execute(
            "SELECT status FROM knowledge_imports WHERE import_id = ? AND user_id IS ?",
            (import_id, user_id),
        ).fetchone()
        if row is None or row[0] != "uploading":
            return False
        try:
            connection.execute(
                "INSERT INTO knowledge_import_files (import_id, relative_path, size, sha256) VALUES (?, ?, ?, ?)",
                (import_id, record.relative_path, record.size, record.sha256),
            )
        except sqlite3.IntegrityError:
            return False
        connection.execute(
            "UPDATE knowledge_imports SET file_count = file_count + 1, total_size = total_size + ? WHERE import_id = ?",
            (record.size, import_id),
        )
    return True


def mark_ready(import_id: str, *, database_path: Path, user_id: int | None, manifest_hash: str, relative_path: str) -> bool:
    with _connect(database_path) as connection:
        _ensure_schema(connection)
        cursor = connection.execute(
            """UPDATE knowledge_imports SET status='ready', manifest_hash=?, relative_path=?,
                      completed_at=CURRENT_TIMESTAMP
               WHERE import_id=? AND user_id IS ? AND status='uploading' AND file_count > 0""",
            (manifest_hash, relative_path, import_id, user_id),
        )
    return cursor.rowcount == 1


def delete_batch(import_id: str, *, database_path: Path, user_id: int | None) -> bool:
    with _connect(database_path) as connection:
        _ensure_schema(connection)
        cursor = connection.execute(
            "DELETE FROM knowledge_imports WHERE import_id=? AND user_id IS ? AND status != 'ready'",
            (import_id, user_id),
        )
    return cursor.rowcount == 1
