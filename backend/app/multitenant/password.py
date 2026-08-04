"""密码哈希（bcrypt）"""

import bcrypt


def _hash_password(password: str) -> str:
    """bcrypt 哈希（自动加随机盐，work_factor=12）"""
    # 截断到 72 字节（bcrypt 固有限制）
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, stored: str) -> bool:
    """bcrypt 验证"""
    return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
