"""
多用户/企业隔离模块

每个用户/租户拥有独立的知识库 collection，数据互不可见。
- 认证：JWT Token + bcrypt 密码哈希
- 隔离：ChromaDB collection 按用户隔离（user_{user_id}）
- 权限：read / write / admin 三级

实现拆分为：db（连接/建表）、password（密码哈希）、users（用户管理）、
sessions（会话管理），此处仅做导出。
"""
from .db import DB_PATH, _get_db, init_db
from .password import _hash_password, _verify_password
from .users import register_user, login_user, get_user_by_id, get_user_collection
from .sessions import save_session, get_session, get_latest_session

__all__ = [
    "DB_PATH",
    "_get_db",
    "init_db",
    "_hash_password",
    "_verify_password",
    "register_user",
    "login_user",
    "get_user_by_id",
    "get_user_collection",
    "save_session",
    "get_session",
    "get_latest_session",
]
