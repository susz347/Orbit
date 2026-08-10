"""Post-Run Critique：每次 loop 结束自动生成反思记录。

记录：false positives、重复问题、调整建议，写入 project_state.critiques，
下次 loop 读取作为约束。
"""

import json
import logging
from typing import Optional

from .budget import LoopBudget
from .state import ProjectState

logger = logging.getLogger(__name__)

CRITIQUE_SYSTEM_PROMPT = """你是一名严谨的系统审计员。请根据下面一次 agent loop 的运行记录生成 Post-Run Critique。

请返回 JSON（不要 markdown 代码块），schema：
{
  "false_positives": ["string", ...],     // Reviewer/Builder 误判或过度敏感的地方
  "duplicate_issues": ["string", ...],    // 与历史 loop 重复、无需再处理的问题
  "adjustment_suggestions": ["string", ...], // 下次 loop 应如何调整（提示词、流程、约束）
  "summary": "string"                     // 一句话总结
}

要求：
- 只基于事实，不要编造。
- 如果某项没有，返回空数组/空字符串。
- adjustment_suggestions 中可包含新的 "约束"，例如 "不要修改 config.py"。
"""


def build_critique_prompt(
    task_desc: str,
    plan: dict,
    build: dict,
    review: dict,
    ux: Optional[dict],
    state: ProjectState,
    budget_summary: dict,
) -> str:
    return (
        f"## 任务\n{task_desc}\n\n"
        f"## 计划\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"## Builder 输出\n{json.dumps(build, ensure_ascii=False, indent=2)}\n\n"
        f"## Reviewer 结论\n{json.dumps(review, ensure_ascii=False, indent=2)}\n\n"
        f"## UX 审查\n{json.dumps(ux or {}, ensure_ascii=False, indent=2)}\n\n"
        f"## 项目 STATE 摘要\n{state.summary_text()}\n\n"
        f"## Token 消耗\n{json.dumps(budget_summary, ensure_ascii=False, indent=2)}"
    )


def generate_critique(
    task_desc: str,
    plan: dict,
    build: dict,
    review: dict,
    ux: Optional[dict],
    state: ProjectState,
    budget: LoopBudget,
) -> dict:
    """生成 critique 记录（同步函数，由编排器在线程池调用）。"""
    prompt = build_critique_prompt(task_desc, plan, build, review, ux, state, budget.summary())
    # 导入避免循环依赖
    from .orchestrator import _call_llm_sync
    try:
        raw, _ = _call_llm_sync(CRITIQUE_SYSTEM_PROMPT, prompt, "", "")
        data = json.loads(raw.strip())
        if not isinstance(data, dict):
            return {"summary": "critique 输出不是对象", "false_positives": [], "duplicate_issues": [],
                    "adjustment_suggestions": []}
        return {
            "false_positives": list(data.get("false_positives") or []),
            "duplicate_issues": list(data.get("duplicate_issues") or []),
            "adjustment_suggestions": list(data.get("adjustment_suggestions") or []),
            "summary": str(data.get("summary") or ""),
        }
    except Exception as e:
        logger.warning("生成 critique 失败: %s", e)
        return {"summary": f"critique 生成失败: {e}", "false_positives": [], "duplicate_issues": [],
                "adjustment_suggestions": []}
