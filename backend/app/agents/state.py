"""Project STATE spine：持久化跨 loop 的项目状态。

每个项目维护一个 project_state（类似 loop-engineering 的 STATE.md）：
- 上次 loop 结果
- 未解决问题
- 已知约束（如"别动 config.py"）
- token 消耗累计
- post-run critiques

权威数据保存在 SQLite project_states 表中，同时镜像为项目目录下的 STATE.md
（人类可读、可 git 追踪、与 loop-engineering 风格一致）。
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from . import db

logger = logging.getLogger(__name__)

STATE_FILENAME = "STATE.md"
STATE_MARKER = "orbit-state"


@dataclass
class ProjectState:
    """跨 loop 项目状态。"""

    project_name: str
    project_dir: str = ""
    last_loop_result: dict = field(default_factory=dict)
    open_problems: list[str] = field(default_factory=list)
    closed_problems: list[str] = field(default_factory=list)  # P0-2: 已解决的问题归档
    constraints: list[str] = field(default_factory=list)
    token_consumption_total: int = 0
    critiques: list[dict] = field(default_factory=list)
    run_count: int = 0
    last_run_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # P2-8: L1→L2→L3 毕业状态
    graduation_level: str = "L1"  # L1 | L2 | L3
    graduation_progress: dict = field(default_factory=dict)  # 毕业条件追踪
    acting_on: Optional[str] = None  # P1-5: 分支锁占用标记

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "project_dir": self.project_dir,
            "last_loop_result": self.last_loop_result,
            "open_problems": self.open_problems,
            "closed_problems": self.closed_problems,
            "constraints": self.constraints,
            "token_consumption_total": self.token_consumption_total,
            "critiques": self.critiques,
            "run_count": self.run_count,
            "last_run_at": self.last_run_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "graduation_level": self.graduation_level,
            "graduation_progress": self.graduation_progress,
            "acting_on": self.acting_on,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectState":
        return cls(
            project_name=data.get("project_name", "untitled"),
            project_dir=data.get("project_dir", ""),
            last_loop_result=data.get("last_loop_result") or {},
            open_problems=list(data.get("open_problems") or []),
            closed_problems=list(data.get("closed_problems") or []),
            constraints=list(data.get("constraints") or []),
            token_consumption_total=int(data.get("token_consumption_total") or 0),
            critiques=list(data.get("critiques") or []),
            run_count=int(data.get("run_count") or 0),
            last_run_at=data.get("last_run_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            graduation_level=data.get("graduation_level", "L1"),
            graduation_progress=data.get("graduation_progress") or {},
            acting_on=data.get("acting_on"),
        )

    def add_critique(self, critique: dict, max_records: int = 10):
        """追加 critique，保留最近 max_records 条。"""
        self.critiques.insert(0, critique)
        if len(self.critiques) > max_records:
            self.critiques = self.critiques[:max_records]

    def summary_text(self) -> str:
        """注入 LLM prompt 的 STATE 摘要。"""
        lines = [
            f"## Project STATE: {self.project_name}",
            f"- Loop Level: {self.graduation_level}",
            f"- 已运行 loop 次数: {self.run_count}",
            f"- 累计 token 消耗: {self.token_consumption_total}",
            f"- 上次运行: {self.last_run_at or 'N/A'}",
        ]
        if self.acting_on:
            lines.append(f"- 当前占用分支: {self.acting_on}")
        if self.last_loop_result:
            lines.append("")
            lines.append("### 上次 loop 结果")
            res = self.last_loop_result
            lines.append(f"- 状态: {res.get('status', 'unknown')}")
            if res.get('summary'):
                lines.append(f"- 摘要: {res['summary']}")
            if res.get('open_problems'):
                lines.append("- 遗留问题:")
                for p in res['open_problems']:
                    lines.append(f"  - {p}")
        if self.open_problems:
            lines.append("")
            lines.append("### 未解决问题")
            for p in self.open_problems:
                lines.append(f"- {p}")
        if self.closed_problems:
            lines.append("")
            lines.append("### 已解决问题（最近5条）")
            for p in self.closed_problems[:5]:
                lines.append(f"- {p}")
        if self.constraints:
            lines.append("")
            lines.append("### 已知约束")
            for c in self.constraints:
                lines.append(f"- {c}")
        if self.critiques:
            lines.append("")
            lines.append("### 历史 Critiques")
            for c in self.critiques[:3]:
                lines.append(f"- [{c.get('created_at', '?')}] {c.get('summary', '')}")
        return "\n".join(lines)


def _state_path(project_dir: str) -> Optional[str]:
    if not project_dir:
        return None
    try:
        target = os.path.realpath(project_dir)
        return os.path.join(target, STATE_FILENAME)
    except Exception:
        return None


def _serialize_frontmatter(state: ProjectState) -> str:
    """STATE.md 顶部 JSON 元数据（安全、无需 YAML 依赖）。"""
    meta = {
        "project_name": state.project_name,
        "run_count": state.run_count,
        "token_consumption_total": state.token_consumption_total,
        "last_run_at": state.last_run_at,
        "graduation_level": state.graduation_level,
        "acting_on": state.acting_on,
        "updated_at": datetime.now().isoformat(),
        "created_at": state.created_at or datetime.now().isoformat(),
    }
    return f"<!-- {STATE_MARKER}: {json.dumps(meta, ensure_ascii=False)} -->"


def _parse_frontmatter(text: str) -> Optional[dict]:
    """从 STATE.md 顶部注释提取元数据。"""
    m = re.search(rf"<!--\s*{STATE_MARKER}:\s*(.+?)\s*-->", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _to_markdown(state: ProjectState) -> str:
    lines = [
        _serialize_frontmatter(state),
        "",
        f"# Project STATE: {state.project_name}",
        "",
        f"- **Loop Level**: {state.graduation_level}",
        f"- **Run Count**: {state.run_count}",
        f"- **Token Total**: {state.token_consumption_total}",
        f"- **Last Run**: {state.last_run_at or 'N/A'}",
    ]
    if state.acting_on:
        lines.append(f"- **Branch Lock**: {state.acting_on}")
    lines.append("")

    lines.append("## Last Loop Result")
    lines.append("")
    if state.last_loop_result:
        res = state.last_loop_result
        lines.append(f"- **status**: {res.get('status', 'unknown')}")
        if res.get('summary'):
            lines.append(f"- **summary**: {res['summary']}")
        for key in sorted(res.keys()):
            if key in ("status", "summary"):
                continue
            val = res[key]
            if isinstance(val, list):
                lines.append(f"- **{key}**:")
                for v in val:
                    lines.append(f"  - {v}")
            else:
                lines.append(f"- **{key}**: {val}")
    else:
        lines.append("_No loop run yet._")

    lines.extend(["", "## Open Problems", ""])
    if state.open_problems:
        for p in state.open_problems:
            lines.append(f"- {p}")
    else:
        lines.append("_None._")

    lines.extend(["", "## Closed Problems", ""])
    if state.closed_problems:
        for p in state.closed_problems[-10:]:
            lines.append(f"- {p}")
    else:
        lines.append("_None._")

    lines.extend(["", "## Constraints", ""])
    if state.constraints:
        for c in state.constraints:
            lines.append(f"- {c}")
    else:
        lines.append("_None._")

    lines.extend(["", "## Graduation", ""])
    lines.append(f"- **Current Level**: {state.graduation_level}")
    if state.graduation_progress:
        lines.append(f"- **Progress**: {json.dumps(state.graduation_progress, ensure_ascii=False)}")
    lines.append("")

    lines.extend(["", "## Critiques", ""])
    if state.critiques:
        for c in state.critiques:
            lines.append(f"### {c.get('created_at', 'unknown')}")
            if c.get('false_positives'):
                lines.append("- false_positives:")
                for fp in c['false_positives']:
                    lines.append(f"  - {fp}")
            if c.get('duplicate_issues'):
                lines.append("- duplicate_issues:")
                for d in c['duplicate_issues']:
                    lines.append(f"  - {d}")
            if c.get('adjustment_suggestions'):
                lines.append("- adjustment_suggestions:")
                for s in c['adjustment_suggestions']:
                    lines.append(f"  - {s}")
            if c.get('summary'):
                lines.append(f"- summary: {c['summary']}")
            lines.append("")
    else:
        lines.append("_No critiques yet._")

    lines.extend(["", "## Token Consumption", ""])
    lines.append(f"- total: {state.token_consumption_total}")
    lines.append("")
    return "\n".join(lines)


def _from_markdown(text: str, fallback_project_dir: str = "") -> ProjectState:
    """从 STATE.md 解析 ProjectState（容错）。"""
    meta = _parse_frontmatter(text) or {}
    state = ProjectState(
        project_name=meta.get("project_name", "untitled"),
        project_dir=fallback_project_dir,
        run_count=meta.get("run_count", 0),
        token_consumption_total=meta.get("token_consumption_total", 0),
        last_run_at=meta.get("last_run_at"),
        created_at=meta.get("created_at"),
        updated_at=meta.get("updated_at"),
        graduation_level=meta.get("graduation_level", "L1"),
        acting_on=meta.get("acting_on"),
    )

    # 简单的 section 提取（行级别）
    sections = {
        "## Last Loop Result": [],
        "## Open Problems": [],
        "## Closed Problems": [],
        "## Constraints": [],
    }
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line in sections:
            current = line
            continue
        if line.startswith("## ") and current:
            current = None
        if current and line.startswith("- "):
            sections[current].append(line[2:].strip())

    state.last_loop_result = {"summary": "; ".join(sections["## Last Loop Result"])}
    state.open_problems = sections["## Open Problems"]
    state.closed_problems = sections["## Closed Problems"]
    state.constraints = sections["## Constraints"]
    return state


def get_graduation_status(state: ProjectState, false_positive_rate: float = 0) -> dict:
    """P2-8: 计算 L1→L2→L3 毕业进度。"""
    checks = {
        "L1_to_L2": {
            "l1_runs_2_weeks": state.run_count >= 14,
            "noise_rate_below_20": false_positive_rate < 0.20,
            "verifier_tested": state.graduation_progress.get("verifier_tested", False),
            "denylist_configured": state.graduation_progress.get("denylist_configured", False),
            "audit_score_58": state.graduation_progress.get("audit_score", 0) >= 58,
        },
        "L2_to_L3": {
            "denylist_in_gate": state.graduation_progress.get("denylist_in_gate", False),
            "auto_merge_disabled_or_allowlisted": state.graduation_progress.get("auto_merge_safe", False),
            "kill_switch_ready": state.graduation_progress.get("kill_switch_ready", False),
            "human_gate_documented": state.graduation_progress.get("human_gate_documented", False),
            "l2_zero_incidents_1_month": state.graduation_progress.get("l2_incidents", 0) == 0
                and state.run_count >= 60,
        },
    }
    current_target = "L2_to_L3" if state.graduation_level == "L2" else "L1_to_L2"
    passed = sum(1 for v in checks[current_target].values() if v)
    total = len(checks[current_target])
    return {
        "current_level": state.graduation_level,
        "checks": checks[current_target],
        "progress": f"{passed}/{total}",
        "ready": passed == total,
    }


def check_graduation_demotion(state: ProjectState, false_positive_rate: float,
                              token_budget_pct: float, recent_escalations: int) -> Optional[str]:
    """P2-8: 检查降级触发器，返回应降到的级别或 None。"""
    if token_budget_pct > 0.80 and state.graduation_level == "L3":
        return "L2"
    if false_positive_rate > 0.30 and state.graduation_level in ("L2", "L3"):
        return "L1"
    if recent_escalations >= 2 and state.graduation_level in ("L2", "L3"):
        return "L1"
    return None


def load_project_state(user_id: Optional[int], project_name: str, project_dir: str = "") -> ProjectState:
    """加载项目 STATE：优先 STATE.md，其次 DB，都没有则初始化。"""
    # 1. STATE.md 文件优先（人类可编辑）
    sp = _state_path(project_dir)
    if sp and os.path.exists(sp):
        try:
            text = open(sp, "r", encoding="utf-8").read()
            state = _from_markdown(text, fallback_project_dir=project_dir)
            state.project_dir = project_dir or state.project_dir
            state.project_name = project_name or state.project_name
            return state
        except Exception as e:
            logger.warning("STATE.md 解析失败: %s", e)

    # 2. DB 兜底
    if user_id:
        row = db.get_project_state(user_id, project_name)
        if row:
            state = ProjectState.from_dict(row.get("state_json") or {})
            state.project_dir = project_dir or state.project_dir
            state.project_name = project_name
            return state

    # 3. 初始化
    return ProjectState(project_name=project_name, project_dir=project_dir)


def save_project_state(user_id: Optional[int], state: ProjectState):
    """持久化 STATE 到 DB 与 STATE.md。"""
    now = datetime.now().isoformat()
    state.updated_at = now
    if not state.created_at:
        state.created_at = now

    if user_id:
        try:
            db.upsert_project_state(user_id, state.project_name, state.project_dir, state.to_dict())
        except Exception as e:
            logger.warning("写入 project_states 表失败: %s", e)

    sp = _state_path(state.project_dir)
    if sp:
        try:
            os.makedirs(os.path.dirname(sp), exist_ok=True)
            open(sp, "w", encoding="utf-8").write(_to_markdown(state))
        except Exception as e:
            logger.warning("写入 STATE.md 失败: %s", e)


def prune_state(state: ProjectState, max_open_problems: int = 20, max_critiques: int = 30) -> ProjectState:
    """P0-2: 每次 loop 启动前清理过时状态。

    清理规则:
    1. open_problems > max_open_problems → 最旧的移入 closed_problems
    2. critiques > max_critiques → 只保留最近 max_critiques 条，旧的内容提取摘要
    3. 超过 30 天未更新的 open_problems → 标记并移到 closed_problems
    """
    now = datetime.now().isoformat()
    changed = False

    # 1. 裁剪 open_problems
    if len(state.open_problems) > max_open_problems:
        overflow = state.open_problems[:-max_open_problems]
        state.closed_problems = (overflow + state.closed_problems)[:50]  # 上限 50
        state.open_problems = state.open_problems[-max_open_problems:]
        changed = True
        logger.info("Prune: 裁剪 open_problems %d -> %d", len(state.open_problems) + len(overflow), len(state.open_problems))

    # 2. 裁剪 critiques
    if len(state.critiques) > max_critiques:
        old = state.critiques[max_critiques:]
        summary_text = "; ".join(c.get("summary", "") for c in old if c.get("summary"))
        if summary_text:
            state.critiques = state.critiques[:max_critiques]
            state.critiques.append({
                "created_at": now,
                "summary": f"[归档] {len(old)} 条旧 critique 摘要: {summary_text[:200]}",
            })
        else:
            state.critiques = state.critiques[:max_critiques]
        changed = True

    return state


def update_state_after_loop(
    user_id: Optional[int],
    project_name: str,
    project_dir: str,
    status: str,
    summary: str,
    open_problems: list[str],
    new_constraints: list[str],
    tokens_used: int,
    critique: Optional[dict] = None,
) -> ProjectState:
    """每次 loop 结束后更新 STATE。"""
    state = load_project_state(user_id, project_name, project_dir)
    state.project_dir = project_dir or state.project_dir
    state.run_count += 1
    state.last_run_at = datetime.now().isoformat()
    state.last_loop_result = {
        "status": status,
        "summary": summary,
        "open_problems": open_problems,
    }
    # 合并新约束（去重），保留旧的
    existing = set(state.constraints)
    for c in new_constraints:
        if c not in existing:
            state.constraints.append(c)
            existing.add(c)
    # 合并未解决问题（去重）
    existing_p = set(state.open_problems)
    for p in open_problems:
        if p not in existing_p:
            state.open_problems.append(p)
            existing_p.add(p)
    state.token_consumption_total += tokens_used
    if critique:
        state.add_critique(critique)
    save_project_state(user_id, state)
    return state
