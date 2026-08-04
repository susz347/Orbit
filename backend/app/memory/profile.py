"""用户画像：save / get"""

import json
from typing import Optional

from .db import _get_db, init_memory_db


def save_user_profile(user_id: int, role: str = None, preferences: dict = None,
                      common_skills: list = None, output_style: str = None):
    """保存/更新用户画像"""
    init_memory_db()
    conn = _get_db()
    try:
        existing = conn.execute("SELECT user_id FROM user_profile WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE user_profile SET
                    role = COALESCE(?, role),
                    preferences = COALESCE(?, preferences),
                    common_skills = COALESCE(?, common_skills),
                    output_style = COALESCE(?, output_style),
                    updated_at = datetime('now')
                WHERE user_id = ?
            """, (
                role,
                json.dumps(preferences, ensure_ascii=False) if preferences else None,
                json.dumps(common_skills, ensure_ascii=False) if common_skills else None,
                output_style,
                user_id,
            ))
        else:
            conn.execute("""
                INSERT INTO user_profile (user_id, role, preferences, common_skills, output_style)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                role,
                json.dumps(preferences or {}, ensure_ascii=False),
                json.dumps(common_skills or [], ensure_ascii=False),
                output_style or "default",
            ))
        conn.commit()
    finally:
        conn.close()


def get_user_profile(user_id: int) -> Optional[dict]:
    """获取用户画像"""
    init_memory_db()
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "role": row["role"],
            "preferences": json.loads(row["preferences"]) if row["preferences"] else {},
            "common_skills": json.loads(row["common_skills"]) if row["common_skills"] else [],
            "output_style": row["output_style"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()
