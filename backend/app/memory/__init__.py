"""
长期记忆模块 — 跨会话上下文恢复

用户打开聊天时，自动加载上次的项目状态和上下文。
- L1: 当前对话上下文（会话内完整保留）
- L2: 近期对话摘要（压缩存储）
- L3: 持久化长期记忆（关键决策、偏好、项目信息）

实现拆分为：db（连接/建表）、profile（用户画像）、project（项目上下文）、
summary（对话摘要）、restore（上下文恢复），此处仅做导出。
"""
from .db import DB_PATH, _get_db, init_memory_db
from .profile import save_user_profile, get_user_profile
from .project import save_project_context, get_latest_project
from .summary import save_conversation_summary, get_recent_summaries
from .restore import restore_context

__all__ = [
    "DB_PATH",
    "_get_db",
    "init_memory_db",
    "save_user_profile",
    "get_user_profile",
    "save_project_context",
    "get_latest_project",
    "save_conversation_summary",
    "get_recent_summaries",
    "restore_context",
]
