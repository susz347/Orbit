"""上下文恢复：跨会话组装完整上下文快照"""

from datetime import datetime

from .profile import get_user_profile
from .project import get_latest_project
from .summary import get_recent_summaries


def restore_context(user_id: int) -> dict:
    """
    跨会话上下文恢复：用户打开聊天时调用。
    返回完整的上下文快照。
    """
    profile = get_user_profile(user_id)
    project = get_latest_project(user_id)
    summaries = get_recent_summaries(user_id, limit=3)

    return {
        "user_profile": profile,
        "current_project": project,
        "recent_summaries": summaries,
        "restored_at": datetime.now().isoformat(),
        "has_context": bool(profile or project or summaries),
    }
