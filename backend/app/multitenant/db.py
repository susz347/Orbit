"""多租户数据库：连接、路径解析、建表"""

import sqlite3

from ..config import settings


def _resolve_db_path() -> str:
    """从 DATABASE_URL 解析 SQLite 文件路径（预留 PostgreSQL 升级路径）"""
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///"):]
    # 未来: if db_url.startswith("postgresql://") → asyncpg
    raise ValueError(f"不支持的数据库 URL scheme: {db_url}")


DB_PATH = _resolve_db_path()


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化多租户数据库"""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            tenant_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            max_collections INTEGER DEFAULT 5,
            max_storage_mb INTEGER DEFAULT 500,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            context TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()
