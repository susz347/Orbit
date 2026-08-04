"""用户管理：注册 / 登录 / 查询 / Collection 隔离"""

from typing import Optional

from .db import _get_db, init_db
from .password import _hash_password, _verify_password


def register_user(username: str, password: str, tenant_id: str = None) -> dict:
    """注册用户"""
    init_db()
    conn = _get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return {"error": "用户名已存在"}

        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, tenant_id) VALUES (?, ?, ?)",
            (username, _hash_password(password), tenant_id),
        )
        user_id = cursor.lastrowid
        conn.commit()

        return {
            "user_id": user_id,
            "username": username,
            "tenant_id": tenant_id,
            "collection_name": f"user_{user_id}",
        }
    finally:
        conn.close()


def login_user(username: str, password: str) -> Optional[dict]:
    """登录验证"""
    init_db()
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            return None

        return {
            "user_id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "tenant_id": row["tenant_id"],
            "collection_name": f"user_{row['id']}",
        }
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """根据 ID 获取用户"""
    init_db()
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def get_user_collection(user_id: int) -> str:
    """获取用户的专属 collection 名称"""
    return f"user_{user_id}"
