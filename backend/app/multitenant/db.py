"""多租户数据库：连接、路径解析、建表（通过 Alembic 迁移管理）。

数据迁移文件位于 alembic/versions/，使用 `alembic upgrade head` 管理 schema 变更。
"""

import os
import sqlite3
from alembic.config import Config as AlembicConfig
from alembic import command

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
    """通过 Alembic 迁移初始化多租户数据库。

    替代了之前的原始 CREATE TABLE 语句，统一由 Alembic 管理 schema 版本。
    首次运行时自动 `alembic upgrade head`；若数据库已是最新版本则无操作。
    """
    # 确保数据目录存在
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    # 如果数据库文件尚不存在，创建一个空文件让 Alembic 可以连接
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        conn.close()

    # 读取 Alembic 配置并执行迁移
    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
    alembic_cfg = AlembicConfig(alembic_ini)

    # 如果有 DATABASE_URL 环境变量，覆盖配置文件中的值
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # P0-4: 自动执行所有未应用的迁移
    command.upgrade(alembic_cfg, "head")
