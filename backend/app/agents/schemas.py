"""Agent Loop 结构化 Schema — Agent 间传递的唯一事实来源（替代 markdown 文件接力）。

落地文档: docs/AGENT-LOOP-INTEGRATION.md §5
关键点:
- verdict 用枚举（ALL_PASS/PARTIAL_FAIL/...），杜绝 run-loop.sh 那种 grep markdown 解析。
- Plan/BuildOutput/ReviewResult 三个产物都有强类型结构，LLM 输出经 Pydantic 校验。
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    ALL_PASS = "ALL_PASS"
    PARTIAL_FAIL = "PARTIAL_FAIL"
    CRITICAL_FAIL = "CRITICAL_FAIL"
    DIMENSION_UNCOVERED = "DIMENSION_UNCOVERED"
    UX_ESCALATE = "UX_ESCALATE"


class TestLevel(str, Enum):
    full = "full"
    smoke = "smoke"
    skip = "skip"


class PlanStep(BaseModel):
    index: int = Field(..., description="步骤序号，从 1 开始")
    desc: str = Field(..., description="做什么（具体到文件/位置）")
    verify: str = Field(..., description="可执行的成功标准")
    test_level: TestLevel = TestLevel.skip
    files: list[str] = Field(default_factory=list, description="涉及的文件路径")


class Gate(BaseModel):
    gate_id: str = Field(..., description="如 G1, G2")
    check: str = Field(..., description="可执行命令/检查")
    pass_criteria: str = Field(..., description="什么算 PASS")


class Plan(BaseModel):
    task_name: str = Field(..., description="任务名称")
    steps: list[PlanStep] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    impact_analysis: str = Field(default="", description="影响面分析（planner.md 核心要求）")
    assumptions: list[str] = Field(default_factory=list)


class BuildOutput(BaseModel):
    summary: str = Field(default="", description="本次改动摘要")
    changed_files: list[dict] = Field(
        default_factory=list,
        description='[{path, action("create"|"modify"|"delete"), content}] — content 为完整文件内容',
    )
    snapshot_hash: str = Field(default="clean", description="git stash create 的 hash，或 'clean'")
    plan_deviations: list[str] = Field(default_factory=list, description="Plan 偏离记录")
    verification_commands: list[str] = Field(
        default_factory=list,
        description="P4: 验证自己产出的可执行命令（如 ['python3 hello.py']），供 orchestrator 执行并取输出作为 Reviewer 证据",
    )


class StageEvidence(BaseModel):
    stage: str = Field(..., description='审查阶段: "0.5" | "1" | "2"')
    item: str = Field(..., description="检查项名称")
    result: str = Field(..., description="PASS | FAIL")
    evidence: str = Field(..., description="真实证据（命令输出/文件内容/数字）")


class ReviewResult(BaseModel):
    verdict: Verdict
    stage_results: list[StageEvidence] = Field(default_factory=list)
    fail_reason: str = Field(default="", description="FAIL 时必填：精确描述")
    fix_direction: str = Field(default="", description="FAIL 时必填：修复方向（给 Builder 退回用）")


class UxCheckpoint(BaseModel):
    checkpoint: str = Field(..., description="检查项（来自 user.md 双视角清单）")
    result: Literal["PASS", "FAIL"] = "PASS"
    issue: str = Field(default="", description="FAIL 时必填：问题描述")
    severity: Literal["critical", "high", "medium", "low"] = "low"
    code_locations: list[dict] = Field(
        default_factory=list,
        description='FAIL 时必填：[{file, line_range, reason}] 定位导致 UX 问题的代码',
    )


class UxReviewResult(BaseModel):
    overall: Literal["PASS", "FAIL", "UX_SKIPPED"] = "UX_SKIPPED"
    user_perspective: list[UxCheckpoint] = Field(default_factory=list)
    designer_perspective: list[UxCheckpoint] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list, description="截图路径（playwright 可用时）")
    summary: str = Field(default="", description="UX 审查总结")


class LoopScheduleIn(BaseModel):
    project_name: str
    task_prompt: str
    cron_expr: str = Field(..., description="简化 cron：m h dom mon dow")
    mode: Literal["L1", "L2"] = "L1"
    enabled: bool = True


class LoopScheduleOut(BaseModel):
    id: int
    project_name: str
    task_prompt: str
    cron_expr: str
    mode: str
    enabled: bool
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    created_at: Optional[str] = None


class GlobalSwitchOut(BaseModel):
    key: str
    value: bool


class BudgetSummary(BaseModel):
    budget: int
    used: dict
    remaining: int
    by_agent: dict


# ── P1-4: Run log schemas ─────────────────────────────────

class RunLogOut(BaseModel):
    id: int
    loop_id: int
    project_name: str
    pattern: str = "manual"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_s: Optional[float] = None
    items_found: int = 0
    files_changed: int = 0
    iterations: int = 0
    outcome: Optional[str] = None
    human_decision: Optional[str] = None
    total_tokens: int = 0
    denylist_hits: int = 0
    escalations: int = 0


class MetricsSummary(BaseModel):
    total_runs: int = 0
    success_rate: float = 0.0
    false_positive_rate: float = 0.0
    avg_duration_s: float = 0.0
    total_tokens: int = 0
    total_denylist_hits: int = 0
    total_escalations: int = 0
    avg_items_found: float = 0.0
    avg_files_changed: float = 0.0
    avg_iterations: float = 0.0
    days: int = 7


class GraduationStatus(BaseModel):
    current_level: str = "L1"
    checks: dict = {}
    progress: str = "0/5"
    ready: bool = False


class GateHitInfo(BaseModel):
    message: str
    hits: list[dict] = []
    abort: bool = False
