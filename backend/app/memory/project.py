"""项目上下文：save / 取最近项目"""

import json
from typing import Optional

from .db import _get_db, init_memory_db


def save_project_context(user_id: int, project_name: str, tech_stack: str = None,
                         current_progress: str = None, key_decisions: list = None):
    """保存项目上下文"""
    init_memory_db()
    conn = _get_db()
    try:
        conn.execute("""
            INSERT INTO project_context (user_id, project_name, tech_stack, current_progress, key_decisions)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id, project_name, tech_stack, current_progress,
            json.dumps(key_decisions or [], ensure_ascii=False),
        ))
        conn.commit()
    finally:
        conn.close()


def get_latest_project(user_id: int) -> Optional[dict]:
    """获取用户最近的项目上下文"""
    init_memory_db()
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM project_context WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "project_name": row["project_name"],
            "tech_stack": row["tech_stack"],
            "current_progress": row["current_progress"],
            "key_decisions": json.loads(row["key_decisions"]) if row["key_decisions"] else [],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()
