"""Agent Loop 模块 — 多智能体协作运行时（对话内嵌，落地文档 docs/AGENT-LOOP-INTEGRATION.md）。

导出入口供 api 层使用。核心逻辑在 orchestrator.py（状态机）与 schemas.py（结构化传递）。
"""
from .db import init_loop_db, create_loop_group, add_loop_event, get_loop_group, get_loop_events
from .db import create_run_log, update_run_log, get_run_logs, get_run_log_metrics, get_daily_metrics
from .db import acquire_branch_lock, release_branch_lock
from .orchestrator import run_loop, get_runtime
from .schemas import Plan, BuildOutput, ReviewResult, Verdict, MetricsSummary, GraduationStatus
from .gate import LoopGate, load_gate, check_build_against_gate

__all__ = [
    "init_loop_db",
    "create_loop_group",
    "add_loop_event",
    "get_loop_group",
    "get_loop_events",
    "create_run_log",
    "update_run_log",
    "get_run_logs",
    "get_run_log_metrics",
    "get_daily_metrics",
    "acquire_branch_lock",
    "release_branch_lock",
    "run_loop",
    "get_runtime",
    "Plan",
    "BuildOutput",
    "ReviewResult",
    "Verdict",
    "MetricsSummary",
    "GraduationStatus",
    "LoopGate",
    "load_gate",
    "check_build_against_gate",
]
