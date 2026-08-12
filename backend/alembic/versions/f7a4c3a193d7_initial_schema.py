"""Initial schema — 从原始 CREATE TABLE 语句迁移到 Alembic 版本管理

Revision ID: f7a4c3a193d7
Revises:
Create Date: 2026-08-11 18:49:26.052030

管理范围：核心多租户表（users, tenants, sessions）
Agent Loop 表、Memory 表由各自模块独立管理（不同 SQLite 文件或独立 init）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a4c3a193d7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建多租户核心表（原 multitenant/db.py）。"""

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            tenant_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            max_collections INTEGER DEFAULT 5,
            max_storage_mb INTEGER DEFAULT 500,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            context TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


def downgrade() -> None:
    """回滚：删除核心表。"""
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TABLE IF EXISTS users")
