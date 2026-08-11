import pytest

from app.knowledge_agent.repository import (
    InvalidRunCursor,
    _connect,
    _ensure_schema,
    list_runs,
)


def _insert_run(database, run_id, user_id, created_at):
    with _connect(database) as connection:
        _ensure_schema(connection)
        connection.execute(
            """INSERT INTO knowledge_agent_runs
               (run_id, user_id, folder_path, status, dry_run,
                vector_store_writes, document_count, created_at)
               VALUES (?, ?, 'fixtures', 'planned', 1, 0, 1, ?)""",
            (run_id, user_id, created_at),
        )


def test_list_runs_is_tenant_scoped_sorted_and_cursor_paginated(tmp_path):
    database = tmp_path / "audit.sqlite3"
    _insert_run(database, "run-old", 7, "2026-08-11 08:00:00")
    _insert_run(database, "run-middle", 7, "2026-08-11 09:00:00")
    _insert_run(database, "run-new", 7, "2026-08-11 10:00:00")
    _insert_run(database, "other-tenant", 8, "2026-08-11 11:00:00")

    first = list_runs(database_path=database, user_id=7, limit=2)
    second = list_runs(
        database_path=database,
        user_id=7,
        limit=2,
        cursor=first.next_cursor,
    )

    assert [item.run_id for item in first.items] == ["run-new", "run-middle"]
    assert [item.run_id for item in second.items] == ["run-old"]
    assert second.next_cursor is None
    assert all(item.user_id == 7 for item in (*first.items, *second.items))


def test_list_runs_uses_run_id_as_stable_timestamp_tiebreaker(tmp_path):
    database = tmp_path / "audit.sqlite3"
    _insert_run(database, "run-a", 7, "2026-08-11 10:00:00")
    _insert_run(database, "run-b", 7, "2026-08-11 10:00:00")

    page = list_runs(database_path=database, user_id=7, limit=1)
    next_page = list_runs(
        database_path=database,
        user_id=7,
        limit=1,
        cursor=page.next_cursor,
    )

    assert [item.run_id for item in page.items] == ["run-b"]
    assert [item.run_id for item in next_page.items] == ["run-a"]


def test_list_runs_rejects_invalid_cursor(tmp_path):
    with pytest.raises(InvalidRunCursor, match="invalid_run_cursor"):
        list_runs(
            database_path=tmp_path / "audit.sqlite3",
            user_id=7,
            limit=20,
            cursor="not-a-cursor",
        )
