"""Loop 级别 token 预算与全局 kill switch。

- 每个 loop 有 token 预算上限，默认从环境变量 LOOP_TOKEN_BUDGET 读取，
  可被 API 调用参数覆盖。
- 每次 LLM 调用后累加 prompt + completion tokens。
- 超限时抛出 BudgetExhausted，编排器据此暂停 loop 并通知用户。
- 全局 pause-all 开关写入 global_switches 表，任何 agent 步骤前检查。
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from . import db

logger = logging.getLogger(__name__)

DEFAULT_LOOP_TOKEN_BUDGET = int(os.getenv("LOOP_TOKEN_BUDGET", "100000"))
PAUSE_ALL_KEY = "loop-pause-all"


class BudgetExhausted(Exception):
    """Loop token 预算耗尽。"""

    def __init__(self, used: int, budget: int):
        super().__init__(f"Loop token budget exhausted: {used}/{budget}")
        self.used = used
        self.budget = budget


class LoopPaused(Exception):
    """全局 pause-all 开关被触发。"""

    def __init__(self):
        super().__init__("Loop paused by global kill switch (loop-pause-all)")


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def estimate_tokens(text: str) -> int:
    """近似 token 估算（API 未返回 usage 时兜底）。

    简单启发式：英文约 4 字符/token，中文约 1.5 字符/token；
    混合文本按 3 字符/token 近似。足够用于预算熔断。
    """
    if not text:
        return 0
    return max(1, int(len(text) / 3))


def extract_usage(response: dict, prompt_text: str) -> Usage:
    """从 OpenAI 兼容响应提取 usage；缺失时按 prompt_text 估算。"""
    usage = response.get("usage") or {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    if prompt is not None and completion is not None:
        return Usage(prompt_tokens=int(prompt), completion_tokens=int(completion),
                     total_tokens=int(total) if total is not None else int(prompt) + int(completion))
    if total is not None:
        # 只知道总量，把 completion 视为一半（保守）
        t = int(total)
        return Usage(prompt_tokens=t // 2, completion_tokens=t - t // 2, total_tokens=t)
    # 兜底估算
    est = estimate_tokens(prompt_text)
    return Usage(prompt_tokens=est, completion_tokens=est // 4, total_tokens=est + est // 4)


@dataclass
class LoopBudget:
    """单个 loop 的预算追踪器。"""

    loop_id: int
    budget: int = DEFAULT_LOOP_TOKEN_BUDGET
    used: Usage = field(default_factory=Usage)
    agent_usages: dict[str, Usage] = field(default_factory=dict)

    def check_pause(self):
        """检查全局 pause-all 开关。"""
        try:
            paused = db.get_global_switch(PAUSE_ALL_KEY, False)
        except Exception as e:
            logger.warning("读取 pause-all 开关失败: %s", e)
            paused = False
        if paused:
            raise LoopPaused()

    def record(self, agent: str, usage: Usage):
        """记录一次 LLM 调用，写入 DB 并检查预算。"""
        self.used.prompt_tokens += usage.prompt_tokens
        self.used.completion_tokens += usage.completion_tokens
        self.used.total_tokens += usage.total_tokens

        self.agent_usages.setdefault(agent, Usage())
        self.agent_usages[agent].prompt_tokens += usage.prompt_tokens
        self.agent_usages[agent].completion_tokens += usage.completion_tokens
        self.agent_usages[agent].total_tokens += usage.total_tokens

        try:
            db.record_token_usage(self.loop_id, agent, usage.prompt_tokens, usage.completion_tokens)
        except Exception as e:
            logger.warning("记录 token usage 失败: %s", e)

        if self.used.total_tokens > self.budget:
            raise BudgetExhausted(self.used.total_tokens, self.budget)

    def summary(self) -> dict:
        return {
            "budget": self.budget,
            "used": self.used.to_dict(),
            "remaining": max(0, self.budget - self.used.total_tokens),
            "by_agent": {k: v.to_dict() for k, v in self.agent_usages.items()},
        }


def get_pause_all() -> bool:
    return bool(db.get_global_switch(PAUSE_ALL_KEY, False))


def set_pause_all(paused: bool):
    db.set_global_switch(PAUSE_ALL_KEY, paused)


def set_loop_budget(loop_id: int, budget: int):
    """把预算写入临时 global_switches 项（loop 级）。"""
    db.set_global_switch(f"loop-budget-{loop_id}", budget)


def get_loop_budget(loop_id: int) -> int:
    return int(db.get_global_switch(f"loop-budget-{loop_id}", DEFAULT_LOOP_TOKEN_BUDGET))
