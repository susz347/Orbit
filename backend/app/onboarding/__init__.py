"""
新手引导模块

首次使用时引导用户选择角色，自动加载预设 Skill 模板。
实现拆分为：templates（角色模板数据）、service（读取接口），此处仅做导出。
"""
from .templates import ROLE_TEMPLATES
from .service import get_onboarding_template, get_role_config, get_all_roles

__all__ = ["ROLE_TEMPLATES", "get_onboarding_template", "get_role_config", "get_all_roles"]
