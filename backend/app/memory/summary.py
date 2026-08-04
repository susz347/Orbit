"""对话摘要：save / get 最近摘要"""

import json

from .db import _get_db, init_memory_db


def save_conversation_summary(user_id: int, summary: str, key_points: list = None):
    """保存对话摘要"""
    init_memory_db()
    conn = _get_db()
    try:
        conn.execute("""
            INSERT INTO conversation_summary (user_id, summary, key_points)
            VALUES (?, ?, ?)
        """, (user_id, summary, json.dumps(key_points or [], ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()


def get_recent_summaries(user_id: int, limit: int = 5) -> list:
    """获取最近的对话摘要"""
    init_memory_db()
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM conversation_summary WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [{
            "summary": r["summary"],
            "key_points": json.loads(r["key_points"]) if r["key_points"] else [],
            "created_at": r["created_at"],
        } for r in rows]
    finally:
        conn.close()
