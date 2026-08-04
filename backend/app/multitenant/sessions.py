"""会话管理（长期记忆用）"""

import secrets
from typing import Optional

from .db import _get_db, init_db


def save_session(user_id: int, context: str) -> str:
    """保存会话上下文（长期记忆）"""
    init_db()
    conn = _get_db()
    session_id = secrets.token_hex(8)
    try:
        conn.execute(
            "INSERT INTO sessions (id, user_id, context) VALUES (?, ?, ?)",
            (session_id, user_id, context),
        )
        conn.commit()
        return session_id
    finally:
        conn.close()


def get_session(session_id: str) -> Optional[dict]:
    """获取会话上下文"""
    init_db()
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def get_latest_session(user_id: int) -> Optional[dict]:
    """获取用户最近的会话（跨会话恢复）"""
    init_db()
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()
