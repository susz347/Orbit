# Agent Loop 集成落地文档

> 目标：把 `agent-loop/`（当前是框架文档 + bash runner）重写为 Orbit 产品内的运行时功能——用户在对话中触发多智能体协作，每个 Agent 用前端配置的 API Key 调用 LLM，过程实时显示在对话流中（workbuddy 式），无需独立观察台。
> 状态：**全部完成（P1-P4，2026-08-04）**

---

## 1. 已确认的决策记录

| # | 决策 | 结论 |
|---|------|------|
| D1 | Agent 间传递方式 | 结构化（Pydantic + SQLite 事件表），markdown 只做归档导出 |
| D2 | Agent 调用方式 | 复用 `app/llm/` 公共层，前端配置的 API Key（`orbit_llm_models_v2`）透传 |
| D3 | 观察台 | **方案 B：砍掉独立观察台**，Agent 状态以卡片形式集成进对话流 |
| D4 | Builder 落盘方式 | **直接落盘 + git 快照兜底**（沿用原设计 `git stash create` 回滚） |
| D5 | Session 模型 | 一个 session ↔ 一个 loop 组（1:1），互不干扰 |
| D6 | loop 触发 | 显式触发（`/loop <任务>` 或按钮），普通问答仍走现有 streamAsk |
| D7 | checkpoint 粒度 | 两处暂停：计划产出后确认 + 最终完成签字（见 §6.5） |

---

## 2. 现状诊断（基于当前代码）

### 2.1 agent-loop 是"框架文档"，不是产品功能

| 维度 | 现状 | 问题 |
|------|------|------|
| 执行方式 | `agent-loop/run-loop.sh`（bash+curl）或 CodeBuddy 加载 SKILL.md | 与 FastAPI 后端脱节，前端无法触发 |
| API Key | `run-loop.sh:26` 读环境变量 `LLM_API_KEY` | 前端用户配置的 key 用不上 |
| Agent 通信 | markdown 文件接力（`memory/loop-*.md`） | 全局单例，多 session 互相覆盖；`run-loop.sh:428` 靠 `grep "ALL_PASS"` 解析结论，脆弱 |
| 用户可见性 | 过程不可见 | 无对话集成 |
| 多用户 | 无 session 概念 | 多用户同时跑 loop 会污染 |

### 2.2 可复用的现有资产（重要：后端已重构，直接复用）

| 资产 | 位置 | 用途 |
|------|------|------|
| LLM 配置解析 + 请求构造 | `backend/app/llm/client.py`（`get_llm_config` / `resolve_api_key` / `build_chat_request`） | Agent LLM 调用的基础，无需新写 |
| RAG Prompt 资产 | `backend/app/llm/prompts.py` | 对话类 agent 可复用 |
| SSE 事件格式化 | `backend/app/stream/sse.py:6` `_sse()` | loop 进度推送 |
| 流式问答编排模式 | `backend/app/stream/service.py`（缓存→检索→路由→LLM 全链路） | orchestrator 的参照实现 |
| JWT 认证 | `backend/app/middleware/auth.py`（`get_optional_user` / `get_current_user`） | loop 接口用户隔离 |
| 多租户 DB | `backend/app/multitenant/db.py`（users/sessions 表） | loop 状态表挂靠，`sessions.user_id` 已存在 |
| 长期记忆 | `backend/app/memory/restore.py` `restore_context()` | loop 启动时注入用户上下文 |
| 对话总结写盘 | `backend/app/api/logos.py` | loop 收尾归档的参照 |
| Agent 前端 schema | `frontend/src/components/agent/agent-panel.tsx:13-24` `AgentStep` | 对话内 agent 卡片的类型定义（B 方案下迁移到 chat 消息） |
| SSE 前端解析 | `frontend/src/lib/api.ts:108-181` `streamAsk` | loop 事件流的解析参照 |

### 2.3 已砍掉/不再需要

- `agent-loop/run-loop.sh`（bash runner）→ 由 orchestrator.py 替代
- `agent-loop/memory/loop-*.md` 文件接力 → 由 loop_events 表替代
- `frontend/src/components/agent/agent-panel.tsx` + sidebar "Agent 观察" tab → 删除（D3）

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│ 前端 (localhost:3000)                                        │
│  ChatInterface                                               │
│   ├─ 普通消息: streamAsk → 现有 RAG 流                        │
│   └─ agent 消息: /loop 触发 → agent 卡片流（本方案新增）        │
│        └─ AgentLoopCard 组件（复用 AgentStep schema）         │
└──────────────────────┬──────────────────────────────────────┘
                       │ POST /api/agents/loop + SSE (X-API-Key, X-LLM-Model)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 后端 (localhost:8001)                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ agents/orchestrator.py  (asyncio 后台任务)            │  │
│  │  Loop 状态机:                                         │  │
│  │   Master(冷启动) → Planner → Builder → Reviewer →     │  │
│  │   checkpoint(用户签字) → 下一轮 / 完成                  │  │
│  └───────────┬───────────────────────────────────────────┘  │
│              │ 每个 agent = 一次 LLM 调用                    │
│              ▼                                              │
│  ┌──────────────────────────────────────┐                   │
│  │ app/llm/client.py（已存在，直接复用）  │                   │
│  │  resolve_api_key() → build_chat_request()               │
│  └──────────────────────────────────────┘                   │
│                                                             │
│  持久化: multitenant.db + 新增 2 表                         │
│   loop_groups / loop_events                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 数据模型（`backend/app/agents/db.py`）

挂靠现有 `multitenant.db`（复用 `multitenant/db.py` 的 `_get_db`），新增两表：

```sql
-- 一个 session 最多一个活跃 loop 组
CREATE TABLE IF NOT EXISTS loop_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,            -- 复用 users.id
    session_id TEXT UNIQUE NOT NULL,     -- 前端 session 标识，1:1
    status TEXT NOT NULL DEFAULT 'running',
        -- running | paused | awaiting_signoff | done | failed
    current_agent TEXT,                  -- master|planner|builder|reviewer
    iteration_count INTEGER DEFAULT 0,   -- 迭代熔断计数
    task_desc TEXT,                      -- 用户原始任务描述
    project_dir TEXT,                    -- D4: Builder 落盘目标目录
    plan_json TEXT,                      -- 结构化 Plan（评审用）
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Event Sourcing：整个 loop 过程的事件流，可回放、可审计
CREATE TABLE IF NOT EXISTS loop_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,                -- 顺序号
    agent TEXT NOT NULL,                 -- master|planner|builder|reviewer|system|user
    event_type TEXT NOT NULL,
        -- spawn | done | plan | step_progress | verdict |
        -- checkpoint | user_decision | error | done
    payload TEXT,                        -- JSON 字符串
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_loop_events_loop ON loop_events(loop_id, seq);
```

**为什么用事件表**（替代 markdown 文件）：
- 多 session 隔离：`loop_id` 天然隔离，互不覆盖
- 结论强类型：`verdict` 是 `ALL_PASS/PARTIAL_FAIL/CRITICAL_FAIL` 枚举，不再 grep markdown
- 可回放：前端对话刷新后可恢复整个 loop 历史（对接 D3 对话内展示）

---

## 5. 结构化 Schema（`backend/app/agents/schemas.py`）

```python
from enum import Enum
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
    index: int
    desc: str
    verify: str                      # 可执行的成功标准
    test_level: TestLevel = TestLevel.skip
    files: list[str] = []            # 涉及文件

class Gate(BaseModel):
    gate_id: str                     # G1, G2...
    check: str                       # 可执行命令/检查
    pass_criteria: str

class Plan(BaseModel):
    task_name: str
    steps: list[PlanStep]
    gates: list[Gate]
    forbidden_paths: list[str] = []
    impact_analysis: str = ""        # 影响面分析（原 planner.md 核心要求）
    assumptions: list[str] = []

class BuildOutput(BaseModel):
    summary: str
    changed_files: list[dict]        # [{path, change}]
    snapshot_hash: str               # D4: git stash create 的 hash，或 "clean"
    plan_deviations: list[str] = []  # Plan 偏离记录

class StageEvidence(BaseModel):
    stage: str                       # "0.5" | "1" | "2"
    item: str
    result: str
    evidence: str

class ReviewResult(BaseModel):
    verdict: Verdict                 # ← 枚举，杜绝字符串 grep
    stage_results: list[StageEvidence]
    fail_reason: str = ""
    fix_direction: str = ""
```

---

## 6. 后端设计（`backend/app/agents/`）

### 6.1 模块结构

```
backend/app/agents/
├── __init__.py          # 导出 orchestrator 入口
├── db.py                # §4 两张表 + CRUD
├── schemas.py           # §5 Pydantic 模型
├── prompts.py           # 迁移 agent-loop/agents/*.md 的 prompt 资产
│                        #  （或运行时读文件，二选一，见 §7 风险 R2）
├── orchestrator.py      # Loop 状态机（核心）
└── api.py               # FastAPI 路由
```

### 6.2 API 设计（`api.py`）

```python
router = APIRouter(prefix="/api/agents", tags=["agents"])

# 启动一个 loop（显式触发）
@router.post("/loop")
async def start_loop(
    body: dict,                         # {session_id, task, project_dir?}
    request: Request,
    current_user = Depends(get_optional_user),
):
    # 从 headers 读 X-API-Key / X-LLM-Model
    # 校验: 该 session 无 running/paused 的 loop → 409
    # 创建 loop_groups + 事件
    # asyncio.create_task(run_loop(loop_id))   # 后台跑，不阻塞
    # 返回 {loop_id}

# 查询 loop 历史（对话刷新后恢复）
@router.get("/loop/{loop_id}")
def get_loop(loop_id: int, current_user = Depends(get_optional_user)):
    # 返回 loop_groups + 全部 events（供前端重放）

# checkpoint 决策（用户点按钮）
@router.post("/loop/{loop_id}/decision")
def decision(
    loop_id: int, body: dict,           # {decision: "continue"|"adjust"|"rollback", note: str}
    current_user = Depends(get_optional_user),
):
    # 写 loop_events(agent="user", event_type="user_decision")
    # 状态机根据 decision 推进
```

### 6.3 LLM 调用（复用 `app/llm/client.py`）

每个 Agent 一次独立调用，**不共享上下文**（保留原设计"上下文重置"原则）：

```python
from ..llm import get_llm_config, resolve_api_key, build_chat_request

def call_agent_llm(
    agent_prompt: str,       # agents/prompts.py 里的 role prompt
    user_context: str,       # 本轮拼接的上下文（plan/output/state）
    api_key: str,            # 前端传的 X-API-Key（resolve_api_key 兜底 env）
    model: str,              # 前端传的 X-LLM-Model，或路由默认
    stream: bool = False,
) -> str:
    _, base_url, model_name = get_llm_config(model)
    api_key = resolve_api_key(api_key)
    req = build_chat_request(base_url, api_key, {
        "model": model_name,
        "messages": [
            {"role": "system", "content": agent_prompt},
            {"role": "user", "content": user_context},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
        "stream": stream,
    })
    # urllib 调用 + 解析（与 stream/service.py 同构）
```

> `llm/client.py:28-30` 的 `resolve_api_key()` 已实现"优先传入值、兜底环境变量"——这正好是之前修 401 bug 时沉淀的公共函数，agent loop 直接受益。

### 6.4 Orchestrator 状态机（`orchestrator.py`）

```
start_loop
  │
  ├─ 事件: spawn master（仅 project 未初始化时，见 §6.6）
  │
  ├─ [Phase 0] 上下文注入
  │    restore_context(user_id) → 注入用户画像/项目/摘要（复用 memory/restore.py）
  │
  ├─ spawn planner → call_agent_llm(planner_prompt, context)
  │    解析 LLM 输出为 Plan (pydantic) → 存 plan_json
  │    事件: plan {steps, gates}
  │    ── ⏸ CHECKPOINT 1：等待用户确认计划 ──
  │        用户 decision=continue → 继续；adjust → 携带 note 重跑 planner
  │
  ├─ spawn builder → call_agent_llm(builder_prompt, plan)
  │    输出 BuildOutput
  │    ★ D4: 直接落盘 + git 快照
  │      ① 读 project_dir → git stash create 记录 snapshot_hash（复用原 builder.md 设计）
  │      ② 将 LLM 产出的改动写入目标文件
  │      ③ 事件: step_progress {index, total, desc}
  │
  ├─ spawn reviewer → call_agent_llm(reviewer_prompt, plan + build_output)
  │    解析为 ReviewResult (verdict 枚举)
  │    事件: verdict {ALL_PASS | PARTIAL_FAIL | ...}
  │
  ├─ 决策:
  │    ALL_PASS → 事件: done → 生成 markdown 归档（§6.7）
  │    PARTIAL_FAIL → iteration_count+1
  │       ≤3 → 退回 builder（带 reviewer.fix_direction）
  │       >3 → CRITICAL_FAIL（迭代熔断）
  │    CRITICAL_FAIL → 事件: error，暂停等人
  │
  └─ ── ⏸ CHECKPOINT 2：最终签字（D7）──
        用户签字 → 状态 done；不签 → 标记 failed
```

### 6.5 Checkpoint 设计（D7）

| Checkpoint | 触发点 | 用户选项 | 前端呈现 |
|-----------|--------|---------|---------|
| CP1 计划确认 | Planner 产出计划后 | continue / adjust（带修改意见） | agent 卡片内嵌 [继续] [调整] 按钮 + 文本输入 |
| CP2 最终签字 | 所有 case 完成后 | 签字 / 不签 | 卡片显示全量摘要 + [标记完成] |

原设计"每 10 个 case 强制暂停"在 Web 对话场景改为**仅这两处暂停**，避免打断用户。

### 6.6 Master 冷启动（可选，P4）

- 触发：用户 `/loop` 但用户尚无 project 上下文（`get_latest_project(user_id)` 为空）
- 走一次对话式对齐（复用 onboarding 的角色模板 + master.md prompt）
- 收敛后写 project_context（`memory/project.py` 的 `save_project_context`）

### 6.7 Markdown 归档（保留原"可回溯"优点）

loop 完成后，从 `loop_events` 渲染一份 markdown 归档（参照 `logos.py:52-69` 写盘模式）：
`data/agent-loops/{loop_id}.md`，包含 plan / builder 改动清单 / reviewer 证据 / 用户决策。
**归档是产物不是载体**——运行时通信只走结构化事件。

---

## 7. 前端设计（D3：对话内嵌，砍观察台）

### 7.1 改动清单

| 文件 | 改动 |
|------|------|
| `frontend/src/components/agent/agent-panel.tsx` | **删除**（D3：不需要观察台） |
| `frontend/src/components/sidebar/sidebar.tsx:36` | 移除 "Agent 观察" nav item（`{ id: "agent", ... }`） |
| `frontend/src/app/page.tsx:14,70` | 移除 `agent` tab 及 `renderPanel` 分支 |
| `frontend/src/components/chat/agent-loop-card.tsx` | **新增**：对话内 agent 卡片（迁移 agent-panel 的 `AgentStep` schema + 时间线 UI，去掉独立面板外壳） |
| `frontend/src/components/chat/chat-interface.tsx` | 消息流支持 `role: "agent"` 类型消息，渲染 AgentLoopCard；识别 `/loop` 命令 |
| `frontend/src/lib/api.ts` | 新增 `agents.runLoop()` / `agents.getLoop()` / `agents.decision()` + loop SSE 解析 |

### 7.2 消息类型扩展

`message-item.tsx:10-16` 的 `Message` 接口扩展：

```typescript
export interface Message {
  id: string;
  role: "user" | "assistant" | "agent";   // ← 新增 agent
  content: string;
  sources?: { filename: string; chunk: string }[];
  timestamp: number;
  // agent loop 专属（role === "agent" 时）
  loopId?: number;
  agentSteps?: AgentStep[];               // 从 agent-panel.tsx 迁移
}
```

### 7.3 对话内 agent 卡片（workbuddy 式）

```
┌──────────────────────────────────────────────┐
│ [Planner ✓]  产出 5 步执行计划   12:05  [▾] │
│ [Builder ⏳] 正在执行 2/5 步骤    12:07  [▾] │
│ [Reviewer ⏸] 等待执行                     │
└──────────────────────────────────────────────┘
  （checkpoint 时）:
┌──────────────────────────────────────────────┐
│ ⏸ 计划已产出，是否开始执行？                  │
│   [✓ 继续]  [✎ 调整: ________]                │
└──────────────────────────────────────────────┘
```

### 7.4 触发方式（D6）

- 输入框识别 `/loop <任务描述>` → 调用 `agents.runLoop()`，走 SSE 推送
- 普通输入 → 保持现有 `streamAsk` 路径，零影响

---

## 8. 分期实施计划

| 期 | 内容 | 复用 | 验收 | 状态 |
|----|------|------|------|------|
| **P1** | 后端 `agents/` 模块：schemas + db + prompts + orchestrator + api，Planner→Builder→Reviewer 直线跑通 + SSE | `llm/client.py`、`_sse`、`get_optional_user` | curl 调 `/api/agents/loop` 能跑完一轮并产出 verdict | ✅ 完成（2026-08-04，11 测试全过 + 全量 241 回归无破坏） |
| **P2** | 前端对话内嵌：agent 卡片组件 + `/loop` 触发 + checkpoint 按钮；删除 agent-panel/sidebar tab | `AgentStep` schema、`streamAsk` 解析 | 对话中能看到完整 agent 流程 + 可点 checkpoint | ✅ 完成（2026-08-04，TS/ESLint/生产构建全过） |
| **P3** | 迭代熔断（PARTIAL_FAIL 退回 ≤3）+ loop_events 回放（刷新恢复）+ markdown 归档 | `logos.py` 写盘 | 失败自动重试、刷新后 loop 可恢复、归档文件自动生成 | ✅ 完成（2026-08-04，归档测试 + 真实 loop 验证 `data/agent-loops/7.md`） |
| **P4** | Master 冷启动对话 + per-role 模型（`X-LLM-Model-Planner` 等）+ User Agent UX 审查 + Builder 命令执行验证能力 | onboarding 角色模板 | 完整产品体验 | ✅ 完成（2026-08-04，4 个子项全部落地，全量 251 测试回归无破坏） |

### P4 交付清单（2026-08-04）

**P4-1 Builder 命令执行验证**（解决 P3 发现的"Reviewer 缺证据判 CRITICAL_FAIL"根因）
- `orchestrator.py` — `_run_verification()`：安全执行 Builder 的 `verification_commands`，产出 Reviewer 执行证据
  - 安全设计（RCE 防护）：命令白名单 + 黑名单双校验、禁 shell（`shlex.split` + `shell=False`）、仅项目根内执行、单命令 30s 超时、输出 4000 字符截断
- `schemas.py` — `BuildOutput.verification_commands` 字段
- `prompts.py` — BUILDER_PROMPT 要求产出验证命令（白名单约束）、REVIEWER_PROMPT 使用执行证据

**P4-2 per-role 模型**
- `api.py` — 解析 `X-LLM-Model-Planner/Builder/Reviewer` headers，传入 orchestrator
- `orchestrator.py` — `run_loop(role_models=...)`，每个 agent 独立模型，缺省回退全局
- 前端：`api.ts` `runLoop` 支持 role headers；`chat-interface.tsx` 读 `orbit_llm_roles_v1`；`settings-panel.tsx` 新增 "Agent 角色模型" 配置区

**P4-3 Master 冷启动**
- `prompts.py` — `MASTER_PROMPT` 需求对齐
- `orchestrator.py` — `_master_bootstrap()`：无项目上下文时先 LLM 对齐，存 `memory.project_context`，注入 Planner

**P4-4 User Agent UX 审查**
- `schemas.py` — `UxReviewResult` / `UxCheckpoint`
- `prompts.py` — `USER_AGENT_PROMPT` 双视角审查（用户 6 项 + 设计师 6 项）
- `orchestrator.py` — `_run_ux_review()`：Reviewer ALL_PASS 后触发；非前端任务 `UX_SKIPPED` 跳过；前端任务 LLM 双视角审查，FAIL 升级给人；`_playwright_available()` 可选截图（未装 playwright 时优雅降级）

测试：`test_agents_loop.py` 新增 9 个（命令验证 5 + Master 2 + User Agent 2）
全量回归：**251 passed**

### 真实浏览器模拟修复记录（2026-08-05/06，playwright 端到端）

通过真实浏览器自动化（playwright-cli）模拟用户完整操作流程（发 `/loop` → checkpoint 交互 → 失败/成功路径 → Settings 配置 → 登录 Master 冷启动），发现并修复 8 个真实 Bug：

| # | Bug | 根因 | 修复 |
|---|-----|------|------|
| #8 | loop 结束 UI 永远"进行中" | `orchestrator._finish` 失败路径不 emit done/error 终态事件 | `_finish` 统一按 status 补发终态事件 |
| #9 | Settings 显示"SQLite 异常/LLM 不可达" | 前端 health 类型期望 `{database,llm}`，后端返回 `{sqlite,llm_api}` | `api.ts` + `settings-panel.tsx` 字段对齐 |
| #10 | LLM 一直"不可达" | health 用 HEAD 打 chat/completions 端点必然失败 | 改为 key 存在性校验（不产生真实调用） |
| #11 | per-role 配置后 `/loop` 报 "Failed to fetch" | CORS `allow_headers` 缺 `X-LLM-Model-Planner/Builder/Reviewer/User` | `main.py` CORS 白名单补全 |
| #12 | 失败显示"已完成"+ 无原因 | 前端 finished 不区分 done/failed；CRITICAL_FAIL 无 failInfo | `loop_failed` 事件 + 前端 outcome/failInfo + 失败面板 |
| #13 | detail 显示"正在执行..."但状态 failed | `buildSteps` error 分支不改 detail；无 loop_failed 时 failInfo 为 null | error 分支更新 detail；`onError` 用 message 兜底 |
| #14 | 点"调整"立即继续，用户没机会填意见 | 前端所有按钮直接提交；后端 adjust 当 continue | 前端两段式（调整→填意见→提交/取消）；后端 adjust 带 note 退回 Planner 重新规划 |
| #15 | Master 完成仍显示"正在执行" | Master 完成 emit 通用 `done` 事件，前端无法识别 | 后端改 `master_done`；前端 `buildSteps` 加 case |

辅助增强：agent spawn 事件带 `model` 字段，前端卡片显示模型徽章（per-role 审计可见）。

验证：后端 252 passed（新增 Bug #14 adjust 循环专项测试）；TypeScript/ESLint/生产构建全过；浏览器端到端全部通过。

### P2 交付清单（2026-08-04）

新增前端文件：
- `frontend/src/components/chat/agent-loop-card.tsx` — 对话内 agent 卡片（时间线 + 可展开详情 + checkpoint 交互按钮），迁移 agent-panel 的 AgentStep schema

改动：
- `frontend/src/lib/api.ts` — 新增 `agents` API（runLoop/getLoop/decision/streamLoop SSE 解析）
- `frontend/src/components/chat/chat-interface.tsx` — `/loop` 命令触发、loop 状态管理、SSE 订阅、checkpoint 决策、事件累加器
- `frontend/src/components/sidebar/sidebar.tsx` — 移除 "Agent 观察" nav item
- `frontend/src/app/page.tsx` — 移除 agent tab

删除：
- `frontend/src/components/agent/agent-panel.tsx`（D3 砍观察台）

### P3 交付清单（2026-08-04）

- `orchestrator.py` — `_archive_loop()` 从 loop_events 渲染 markdown 归档到 `data/agent-loops/{loop_id}.md`，loop 结束时自动触发；修复 `_AGENTS_ROOT` 路径（4 层 → 3 层 `..`）
- `test/test_agents_loop.py` — 新增 TestLoopArchive 归档测试

### P3 端到端验证（真实 LLM，loop #7）

- Planner 产出真实计划 → Builder 生成 hello.py → Reviewer 因"缺少执行输出证据"判 CRITICAL_FAIL（正确行为：证据缺失拒绝放水）→ 归档 `7.md` 自动生成
- 全量回归：242 passed

### P1 交付清单（2026-08-04）

新增后端文件：
- `backend/app/agents/schemas.py` — Plan/BuildOutput/ReviewResult Pydantic 模型（verdict 枚举）
- `backend/app/agents/db.py` — `loop_groups` / `loop_events` 两表（挂 multitenant.db）
- `backend/app/agents/prompts.py` — 三个角色 JSON 输出版 prompt
- `backend/app/agents/orchestrator.py` — Loop 状态机（Planner→Builder→Reviewer、checkpoint 等待、迭代熔断、Builder 落盘 + git 快照）
- `backend/app/agents/api.py` — 4 个端点（POST /loop、GET /loop/{id}、GET /loop/{id}/events SSE、POST /loop/{id}/decision）

改动：
- `backend/app/main.py` — 注册 agents 路由 + lifespan 初始化 loop 表

新增测试：
- `backend/test/test_agents_loop.py` — 5 个状态机测试（happy path / 退回重试 / CRITICAL_FAIL / 熔断）
- `backend/test/test_agents_api.py` — 6 个 API 测试（校验 / 409 冲突 / AuthZ 403）

实现过程中的 3 个关键修复：
1. `orchestrator.py _wait_decision` — clear 事件必须在 emit 之前（否则决策信号会被清掉导致永久等待）
2. `orchestrator.py _call_agent_llm` — LLM 调用放 `asyncio.to_thread`，不阻塞事件循环
3. 测试闭包 `i += 1` 需用可变容器（`idx["n"]`）避免 `UnboundLocalError`

---

## 9. 风险与对策

| # | 风险 | 对策 |
|---|------|------|
| R1 | LLM 输出不是合法 JSON，Pydantic 解析失败 | 解析时做两次尝试：直接 `json.loads` → 失败则让 LLM 自修复（把报错回传重新生成）；仍失败 → CRITICAL_FAIL 升级给人 |
| R2 | `agents/*.md` prompt 资产迁移方式 | 优先**运行时读文件**（`agents/prompts.py` 读 `agent-loop/agents/*.md`），避免复制两份；若 agent-loop 目录被独立管理则复制进 backend |
| R3 | Builder 落盘覆盖用户未提交改动 | 落盘前 `git stash create`；检测工作区有非本次改动 → 暂停报告（沿用 `builder.md:29-37` 设计） |
| R4 | 长任务中断（浏览器刷新/SSE 断开） | loop 跑在 asyncio 后台任务，不依赖 SSE 连接；前端刷新后 `GET /loop/{id}` 重放事件恢复展示 |
| R5 | 多用户并发 | `loop_groups.session_id UNIQUE` + 启动时检查活跃 loop → 409；`loop_events` 按 `loop_id` 隔离 |
| R6 | API Key 安全问题 | Key 只存前端 localStorage、只经 header 透传（沿用现有模式），后端不落盘；SSE 事件不打印 key |

---

## 10. 明确不做

- 独立 Agent 观察台页面（D3 已砍）
- Redis/NATS/Temporal 分布式（单机 SQLite + asyncio 足够，`agent-loop/agents/PROTOCOL.md` 的扩展路径等有真实多机需求再说）
- 普通对话自动过 loop（D6 显式触发，控制成本与延迟）
- 每 N 个 case 强制暂停（D7 改为两处 checkpoint）
