"""新手引导读取接口：模板 / 角色配置 / 角色列表"""

from typing import Optional

from .templates import ROLE_TEMPLATES


def get_onboarding_template() -> dict:
    """获取新手引导模板（首次使用时展示）"""
    return {
        "title": "欢迎使用 AI Agent 系统",
        "subtitle": "选择你的角色，我们会为你推荐最合适的工具组合",
        "roles": [
            {
                "key": k,
                "label": v["label"],
                "icon": v["icon"],
                "desc": v["desc"],
                "quick_actions_count": len(v["quick_actions"]),
            }
            for k, v in ROLE_TEMPLATES.items()
        ],
    }


def get_role_config(role: str) -> Optional[dict]:
    """获取指定角色的完整配置"""
    return ROLE_TEMPLATES.get(role)


def get_all_roles() -> dict:
    """获取所有角色"""
    return {k: {"label": v["label"], "icon": v["icon"], "desc": v["desc"]} for k, v in ROLE_TEMPLATES.items()}
