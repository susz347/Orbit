# Agent Loop 完整介绍与 Bug 修复记录

> 本文档面向开发者：先讲清 Agent Loop 是什么、怎么工作、代码在哪，再逐条记录真实浏览器模拟中发现并修复的 Bug（现象 → 根因 → 修复 → 验证）。
> 配套文档：`AGENT-LOOP-INTEGRATION.md`（落地/实施设计稿）；本文件是"运行时现状 + 修复日志"。

---

## 第一部分：Agent Loop 是什么

### 1.1 一句话

Agent Loop 是 Orbit 的**多智能体协作执行引擎**：用户在对话中输入 `/loop <任务>`，系统自动派发一组智能体（Planner → Builder → Reviewer，必要时 Master/User Agent）接力完成任务，过程以**卡片形式实时显示在对话流中**（workbuddy 式），每个智能体使用**用户在前端配置的 API Key 和模型**（支持 per-role 独立模型）。

### 1.2 设计核心

| 原则 | 说明 |
|------|------|
| 生成-评估分离 | Builder 只干活不评价，Reviewer 只验证不修改，消除自我评估偏差 |
| 只读 Planner | 规划阶段不碰代码 |
| 结构化传递 | Agent 间用 Pydantic + SQLite 事件表通信，**不用 markdown 文件接力** |
| 上下文重置 | 每个 Agent 独立 LLM 调用，不带历史上下文（防污染） |
| checkpoint 签字 | 计划产出后、最终完成时强制用户确认 |
| 迭代熔断 | PARTIAL_FAIL 退回 Builder 最多 3 次，超限升级给人 |
| 证据驱动 | Reviewer 必须有真实执行证据才能 PASS，否则 CRITICAL_FAIL |
| 安全优先 | 命令执行白名单 + 禁 shell + 目录约束（RCE 防护）|

### 1.3 智能体角色

| Agent | 职责 | 触发 |
|-------|------|------|
| **Master** | 冷启动需求对齐（用户无项目上下文时） | 登录用户 + 无 project_context |
| **Planner** | 只读分析 → 产出结构化执行计划（steps + gates + 影响面） | 每个 loop 必跑 |
| **Builder** | 严格按计划改代码 → 落盘 + git 快照 + 产出验证命令 | Planner 计划确认后 |
| **Reviewer** | 两阶段验证（Spec + 质量），要求真实证据 | Builder 完成后 |
| **User Agent** | 前端 UX 审查（用户视角 + 设计师视角） | 前端任务 + Reviewer ALL_PASS 后 |

### 1.4 完整流程

```
用户输入 "/loop 写一个 hello.py 输出 Hello World"
  │
  ├─ Master（仅冷启动：新用户无项目上下文时）
  │    需求对齐 → 保存 project_context → 注入 Planner 上下文
  │
  ├─ Planner（per-role 模型）
  │    产出 Plan（steps/gates/影响面）→ 发 plan 事件
  │    ↓
  │    ⏸ CP1 计划确认（继续 / 调整 / 回退）
  │       ├─ 继续 → 进入 Builder
  │       ├─ 调整 → 带意见退回 Planner 重新规划（循环）
  │       └─ 回退 → 终止 loop
  │
  ├─ Builder（per-role 模型）
  │    按计划改代码 → 落盘 + git stash 快照 → 执行验证命令产出证据
  │
  ├─ Reviewer（per-role 模型）
  │    用执行证据两阶段审查
  │    ├─ ALL_PASS → 进入 User Agent
  │    ├─ PARTIAL_FAIL → 退回 Builder 修复（≤3 次）
  │    └─ CRITICAL_FAIL → 发 loop_failed 事件 → 终止
  │
  ├─ User Agent（前端任务）
  │    双视角 UX 审查（FAIL → 升级给人）
  │
  └─ ⏸ CP2 最终签字（标记完成 / 拒绝）
        → done / failed → markdown 归档 → 清理
```

### 1.5 事件流（SSE 推送前端）

```
spawn → plan → checkpoint(CP1) → user_decision → spawn(builder)
→ builder_done(+verification) → spawn(reviewer) → verdict
→ spawn(user) → ux_review → checkpoint(CP2) → user_decision
→ done / loop_failed / error
```

P5 新增事件：`budget`（阶段性 token 汇报）、`report`（L1 报告模式）、`worktree_created / worktree_merged`（worktree 生命周期）、`budget_exhausted` / `paused`（预算耗尽 / 全局暂停）。

前端 `buildSteps()` 把事件流转成 AgentStep 卡片列表，checkpoint 时渲染交互按钮。

---

## 第二部分：代码结构

### 2.1 后端 `backend/app/agents/`

| 文件 | 职责 |
|------|------|
| `schemas.py` | Plan / BuildOutput / ReviewResult / UxReviewResult Pydantic 模型（verdict 枚举）+ LoopScheduleIn/Out、GlobalSwitchOut、Usage |
| `db.py` | `loop_groups` / `loop_events` 两表（挂 multitenant.db）+ P5 新增 `project_states` / `loop_schedules` / `loop_budget_usage` / `global_switches` 表 |
| `prompts.py` | 各角色 JSON 输出版 prompt（MASTER/PLANNER/BUILDER/REVIEWER/USER_AGENT）|
| `orchestrator.py` | 状态机：Master→Planner(CP1 循环)→Builder→Reviewer(熔断)→User→CP2；`_finish` 终态 + 归档；P5：STATE 读写、L1/L2 模式、worktree、budget、critique |
| `state.py` | P5：ProjectState 读写 + STATE.md 镜像（L4 记忆脊柱）|
| `budget.py` | P5：LoopBudget token 追踪 + `loop-pause-all` 全局开关 |
| `worktree.py` | P5：独立 git worktree 隔离（create/commit/apply/discard）|
| `schedule.py` | P5：cron 解析 + 每分钟调度器 |
| `critique.py` | P5：Post-Run Critique 自动反思 |
| `api.py` | 9 组端点：POST /loop、GET /loop/{id}、GET /loop/{id}/events(SSE)、POST /loop/{id}/decision、GET /loops、GET/POST/PATCH/DELETE /schedules、GET/POST /loop/pause-all、GET /state/{project_name} |

### 2.2 前端

| 文件 | 职责 |
|------|------|
| `lib/api.ts` | `agents.runLoop/getLoop/decision/streamLoop/listLoops/getProjectState/listSchedules/createSchedule/updateSchedule/deleteSchedule/getPauseAll/setPauseAll` + SSE 解析 |
| `components/chat/agent-loop-card.tsx` | 对话内 agent 卡片（时间线 + 模型徽章 + checkpoint 交互 + 失败面板）|
| `components/chat/chat-interface.tsx` | `/loop` 触发、事件累积、`buildSteps` 状态机渲染、决策提交 |
| `components/chat/loop-settings-bar.tsx` | P5：loop 运行配置栏（项目名/目录/模式/预算，持久化 localStorage）|
| `components/chat/pause-all-switch.tsx` | P5：全局暂停开关按钮 |
| `components/settings/settings-panel.tsx` | per-role 模型配置区（orbit_llm_roles_v1）+ P5 Schedule 管理（创建/启用/删除）|

### 2.3 关键 API

| 端点 | 说明 |
|------|------|
| `POST /api/agents/loop` | 启动 loop（body: session_id/task/project_dir/**mode(L1/L2)/project_name/budget_limit**；header: X-API-Key/X-LLM-Model/X-LLM-Model-{Role}）|
| `GET /api/agents/loop/{id}` | 查询 loop + 全部事件（刷新恢复）|
| `GET /api/agents/loop/{id}/events` | SSE 事件流（回放 DB + 订阅实时）|
| `POST /api/agents/loop/{id}/decision` | checkpoint 决策（continue/adjust/rollback/approve/reject）|
| `GET /api/agents/loops` | 当前用户 loop 列表（Schedule 触发后可追踪）|
| `GET/POST/PATCH/DELETE /api/agents/schedules` | 定时触发器 CRUD（L1 报告 / L2 行动）|
| `GET/POST /api/agents/loop/pause-all` | 全局 kill switch（暂停所有新 loop）|
| `GET /api/agents/state/{project_name}` | 读取项目 STATE 摘要 |

---

## 第三部分：Bug 修复记录（真实浏览器模拟发现）

> 方法：playwright 真实浏览器自动点击、输入、提交，模拟真实用户操作，逐环节找非预期行为。
> 共修复 **10 个 Bug**（#8-#18），全部经过浏览器端到端复验。

---

### Bug #8：loop 结束后 UI 永远显示"进行中"

**严重度**：致命（核心流程不可用）

**现象**：完整跑完 Planner→Builder→Reviewer 后，卡片永远显示"进行中 · 完成 3"，不会变"已完成"。

**根因**：后端 `orchestrator._finish()` 在失败路径（CRITICAL_FAIL / 熔断 / 异常）直接调 `_finish(loop_id, "failed")` 收尾，**从不 emit `done`/`error` 终态事件**。SSE 连接只收到 `verdict` 后关闭，前端 `onDone/onError` 从未被触发 → `finished: true` 永不设置。

**修复**：
- 后端 `_finish()` 统一按 status 补发终态事件（done → emit `done`；否则 emit `error`）
- 前端 `api.ts streamLoop` 按 `currentEvent` 分发：`done` → `cb.onDone()`；`error` → `cb.onError(message)`（原来只调 `onEvent`）

**验证**：浏览器跑完 loop → UI 显示"已完成 · 完成 3"。

---

### Bug #9：Settings 显示"SQLite 异常 / LLM 不可达"（实际正常）

**严重度**：中（误导用户）

**现象**：设置页系统状态里 SQLite 显示"异常"、LLM 显示"不可达"，但后端实际正常。

**根因**：前端 `api.ts` health 类型期望 `{status, chromadb, database, llm}`，后端 `/health` 实际返回 `{status, chromadb, sqlite, llm_api}`——字段名不匹配，前端读 `database`/`llm` 得到 undefined。

**修复**：
- `api.ts` health 类型改为 `{status, chromadb, sqlite, llm_api}`
- `settings-panel.tsx` 渲染字段 `health?.sqlite` / `health?.llm_api === "ok"`

**验证**：设置页显示 SQLite 正常、LLM 可达。

---

### Bug #10：LLM 永远"不可达"（health 探测必然失败）

**严重度**：中（误报）

**现象**：即使配置了正确 key，LLM 可达性始终"不可达"。

**根因**：`main.py` health 探测用 **HEAD 请求打 `chat/completions` 端点**——该端点不支持 HEAD 必然 404/401；且默认 base_url 写死 OpenAI 而实际用 DeepSeek。

**修复**：health 只校验 `LLM_API_KEY` 是否存在（health 不该产生真实 API 调用开销；真实失败在请求时体现）。

**验证**：`/health` 返回 `llm_api: ok, status: ok`。

---

### Bug #11：per-role 配置后 `/loop` 报 "Failed to fetch"

**严重度**：致命（P4 per-role 功能浏览器全挂）

**现象**：在 Settings 配置 per-role 模型后发 `/loop`，前端报 `Agent Loop 启动失败: Failed to fetch`。

**根因**：`main.py` CORS `allow_headers` 白名单只有 `X-API-Key / X-LLM-Model / X-Request-ID`，**缺 P4-2 新增的 `X-LLM-Model-Planner/Builder/Reviewer/User`**。浏览器发自定义 header 前先 OPTIONS 预检 → 预检被拒（400）→ 请求直接失败。
（此前 P4 开发用 curl 验证绕过 CORS，浏览器从未实测 → 盲区。）

**修复**：`main.py` CORS 白名单补全 4 个 role headers。

**验证**：OPTIONS 预检返回 200 且 allow-headers 含新字段；浏览器发 `/loop` 正常。

---

### Bug #12：失败显示"已完成"且无失败原因

**严重度**：高（严重误导）

**现象**：Reviewer 判 CRITICAL_FAIL 后，UI 显示"**已完成** · 完成 3"（实际是失败），且只有 `CRITICAL_FAIL` 四个字，无失败原因、无后续操作。

**根因**：
1. 前端 `finished: true` 时无条件显示"已完成"，不区分 done/failed
2. CRITICAL_FAIL 路径只 emit 通用 `error` 事件（无 fail_reason），前端 failInfo 为 null

**修复**：
- 后端 CRITICAL_FAIL 分支新增 `loop_failed` 事件，带 `{verdict, fail_reason, fix_direction}`
- 前端 `LoopViewState` 加 `outcome: "done"|"failed"` + `failInfo`
- `AgentLoopCard` 头部区分"已完成/执行失败"，失败时渲染红色原因面板（含修复方向 + 重试提示）

**验证**：失败时显示"执行失败 · CRITICAL_FAIL · 已升级给人处理" + 完整原因 + "可重新发起 /loop 重试"。

---

### Bug #13：detail 显示"正在执行..."但状态是 failed（矛盾）

**严重度**：中（状态不一致）

**现象**：Planner 阶段失败（如 401）时，卡片显示 `planner | gpt-4o-mini | 正在执行...`，但整体状态是 failed。

**根因**：`buildSteps` 的 `error` 分支只把 `running → failed` 改 status，**不改 detail**；且无 `loop_failed` 事件时 failInfo 为 null → 失败面板不渲染。

**修复**：
- `buildSteps` error 分支同步更新 `detail = "执行失败"`
- 前端 `onError` 用 message 兜底填充 failInfo（无 loop_failed 时）

**验证**：失败时显示 `planner | 执行失败` + 失败面板（ERROR · HTTP Error 401）。

---

### Bug #14：点"调整"按钮立即继续，用户没机会填意见

**严重度**：高（关键交互损坏）

**现象**：CP1 点"调整"，loop **立即继续执行** Builder——用户根本没法填调整意见。输入框形同虚设。

**根因**：P1 遗留简化（代码注释"adjust 目前先直接继续"）：
1. 前端所有 checkpoint 按钮直接 `handleDecision(opt)`，点"调整"立即提交
2. 后端收到 adjust 后当 continue 处理

**修复**：
- 前端：两段式交互——点"调整"进入输入模式（显示意见输入框 + 提交/取消），填完点"提交调整"才提交 decision
- 后端：adjust 决策带 note 退回 Planner **重新规划**（while 循环 + `plan_adjusted` 事件），非前端任务直接继续

**验证**：点"调整"→ 输入框出现但 loop 不推进 → 填意见提交 → Planner 重新 spawn 产出新计划 → 再次 CP1 确认。新增专项测试 `TestAdjustLoop` 断言调整意见注入 Planner 上下文。

---

### Bug #15：Master 冷启动完成仍显示"正在执行"

**严重度**：中（状态不更新）

**现象**：新用户触发 Master 冷启动后，Master 完成但卡片停在"正在执行..."，且整体"已完成 · 执行中 1"矛盾。

**根因**：后端 Master 完成时 emit 通用 `done` 事件（agent="master"），前端 `buildSteps` 的 `case "done"` 是空操作（done 是 loop 结束标记）→ Master 步骤无法识别完成。

**修复**：
- 后端 Master 完成改用 `master_done` 事件类型（与 `builder_done` 命名一致）
- 前端 `buildSteps` 加 `case "master_done"` → `complete("master", "需求对齐完成")`
- 顺带补 master spawn 的 `model` 字段（模型徽章）

**验证**：全新用户发 `/loop` → `master | deepseek-chat | 需求对齐完成` → planner 产出计划 → CP1。已有上下文用户正确跳过 Master。

---

### Bug #16：搜索显示"NaN% 匹配"且无内容

**严重度**：高（搜索功能不可用）

**现象**：知识库搜索显示"找到 5 条结果"但每条都是 `NaN% 匹配`、无内容文本、无文件名。

**根因**：前端搜索面板 + api.ts 期望 `{content, similarity, metadata.filename}`，后端实际返回 `{text, score, metadata.source}`——**三处字段全不匹配**（`undefined * 100 = NaN`）。

**修复**：
- `api.ts` search 返回类型对齐 `{text, score}`
- `search-panel.tsx` `SearchResult` 接口 + 渲染逻辑（`text`/`score`/`metadata.source`，兼容旧字段）

**验证**：搜索显示内容文本 + `test_doc.md` + 匹配度 76%/74%/57%... 按相关度排序。

---

### Bug #17 + 17b：登录/注册 UI 从未接入产品

**严重度**：高（功能悬空）

**现象**：登录/注册页从未显示——`AuthForm` 组件是死代码，`page.tsx` 从不检查 `isAuthenticated`；即使往 localStorage 注入 token 也无任何 UI 变化。

**根因**：
- #17：`AuthForm` 定义后从未渲染，auth-context 的登录态无任何组件消费
- #17b：前端 `auth.login` 期望 `{token}`，后端实际返回 `{access_token}`

**修复**：
- `page.tsx` 接入：未登录且未跳过 → 显示 AuthForm（含"跳过，稍后登录"匿名入口）；登录成功关登录页，新用户走 onboarding
- `api.ts` + `auth-form.tsx` 兼容 `access_token`（`res.access_token ?? res.token`）

**验证**：未登录访问显示登录页；注册 ui_tester → 自动登录 → 主界面；无错误。

---

### Bug #18：登录后无登出入口

**严重度**：低-中（UX 缺失）

**现象**：登录成功后 sidebar 只有 `Orbit v1.0`，用户无法从 UI 登出（只能清 localStorage）。

**根因**：sidebar footer 无用户信息区。

**修复**：sidebar 底部加用户区（头像首字母 + 用户名 + 登出按钮，用 `useAuth().logout`），未登录不显示。

**验证**：登录后显示 `U · ui_tester` + 登出按钮；点击登出回登录页。

---

## 第四部分：实施过程中的架构级修复（P1-P4）

> 这些不是浏览器 bug，是开发期发现并修复的设计/实现问题。

| 位置 | 问题 | 修复 |
|------|------|------|
| `orchestrator._wait_decision` | `checkpoint_event.clear()` 在 `_emit` 之后，决策信号可能被清掉导致永久等待 | clear 提到 emit 之前 |
| `orchestrator._call_agent_llm` | 阻塞 urllib 直接跑事件循环会卡死所有请求 | 用 `asyncio.to_thread` 包装 |
| 测试闭包 | `_driver` 内 `i += 1` 无 `nonlocal` 抛 UnboundLocalError | 改用可变容器 `idx["n"]` |
| `_AGENTS_ROOT` 路径 | 从 backend/app/agents 到 Orbit 根用错 4 层 `..` | 改为 3 层 + `os.path.realpath` |
| `_run_verification` cwd | subprocess 的 cwd 目录不存在抛 FileNotFoundError | 补 `os.makedirs` |
| agent spawn 事件 | 不记录实际模型，per-role 配置无法审计 | spawn 事件带 `model` 字段，前端显示模型徽章 |

---

## 第五部分：当前状态与验证

### 5.1 完成度

| 项 | 状态 |
|----|------|
| P1 后端运行时（schemas/db/prompts/orchestrator/api）| ✅ |
| P2 前端对话内嵌（/loop 触发 + 卡片 + checkpoint）| ✅ |
| P3 熔断 + 事件回放 + markdown 归档 | ✅ |
| P4 Master 冷启动 + per-role 模型 + 命令验证 + User UX 审查 | ✅ |
| P5 STATE 脊柱（跨 loop 持久记忆 + STATE.md）| ✅ |
| P5 Schedule 触发（L1 报告 / L2 行动，cron）| ✅ |
| P5 Worktree 隔离（Builder 独立 worktree，成功才合并）| ✅ |
| P5 Budget + Kill Switch（token 预算 + loop-pause-all）| ✅ |
| P5 Post-Run Critique（自动反思写入 STATE）| ✅ |
| P6 文件记忆（扫描→小模型选择→预算注入→过期警告）| ✅ |
| 浏览器模拟 Bug 修复（#8-#18）| ✅ 10 个 |
| 登录/注册/登出 UI 接入 | ✅ |

### 5.2 测试覆盖

- 后端全量：**265 passed**（含 TestAdjustLoop、TestMasterBootstrap、TestRunVerification、TestLoopArchive、TestLoopOrchestrator、TestAgentsAPI、TestFileMemory）
- 前端：TypeScript 0 错误、ESLint 0 错误、生产构建通过

### 5.3 浏览器端到端验证过的场景

- [x] `/loop` 触发 → Planner 自动展开计划
- [x] CP1 继续/调整（两段式）/回退
- [x] Builder 生成代码 + 模型徽章
- [x] Reviewer CRITICAL_FAIL + 失败面板 + 重试提示
- [x] Master 冷启动（全新用户）→ 需求对齐完成
- [x] per-role 模型配置（UI 输入 + 生效 + 徽章）
- [x] 知识库上传 → 搜索 → RAG 问答
- [x] 登录/注册/登出
- [x] 全部 5 个 tab 渲染

---

## 第六部分：记忆机制与 Loop 循环详解

> 本章回答两个核心问题：**Agent Loop 怎么"记住"东西**（记忆机制），以及**它为什么是 loop 而不是一次性 pipeline**（循环闭环）。对应代码在 `backend/app/memory/` 与 `backend/app/agents/`。

### 6.1 记忆机制：四层金字塔

Agent Loop 的记忆不是单一存储，而是按**生命周期长短**分层的金字塔。越往上越"易失"，越往下越"持久"。

| 层级 | 名称 | 存储位置 | 生命周期 | 内容 | 代码 |
|------|------|----------|----------|------|------|
| L0 | 单次调用上下文 | 内存（LLM request 内） | 单次 LLM 调用 | 该 Agent 的 prompt + 注入上下文，**每次调用独立组装、用完即弃** | `orchestrator._call_agent_llm` |
| L1 | 会话运行日志 | SQLite `loop_events` | 单次 loop | 事件溯源（spawn/plan/verdict/done…），SSE 推送 + 刷新回放 | `agents/db.py` |
| L2 | 对话摘要 | SQLite `conversation_summary` | 跨会话 | 历史对话的 `summary` + `key_points`，最近 3 条随上下文恢复注入 | `memory/summary.py` |
| L3 | 画像 + 项目上下文 | SQLite `user_profile` / `project_context` | 长期 | 用户角色/偏好/技能 + 项目技术栈/进展/关键决策 | `memory/profile.py`、`memory/project.py` |
| L4 | **STATE 脊柱** | SQLite `project_states` + `STATE.md` | 跨 loop（持久） | 上次 loop 结果、未解决问题、已知约束、token 累计、critique | `agents/state.py` |
| L5 | **文件记忆**（P6） | 项目目录/`data/memory/` 下的文件 + 小模型选择 | 跨 loop（文件持久） | 按文件组织的记忆（类型标签+内容），扫描→选择→预算注入→过期警告 | `memory/file_memory.py` |

**数据流（写路径）**：

```
Master 冷启动对齐 ──→ memory/project.save_project_context()   （L3）
loop 结束/失败   ──→ agents/state.update_state_after_loop()   （L4，写 project_states + 镜像 STATE.md）
```

**数据流（读路径）**：

```
loop 启动 Phase 0 ──→ memory/restore.restore_context(user_id)   （组装 L2+L3 快照）
                  ──→ agents/state.load_project_state(...)      （读取 L4 STATE）
                  ──→ 拼接成 user_context 注入 Planner          （L2+L3+L4 一次性注入）
```

`restore_context()`（`memory/restore.py:10-25`）是 L2/L3 的统一入口：取用户画像 + 最近项目 + 最近 3 条摘要，打包成 `{user_profile, current_project, recent_summaries, has_context}`。`has_context` 决定是否触发 Master 冷启动。

**L4 STATE 脊柱为什么是关键**：L1-L3 都是"记录"，只有 L4 是"可被下次运行读取并强制执行约束"的记忆。它把"上次失败的原因"变成"这次 Planner 的禁止事项"，把"token 累计"变成"这次预算的起点"。没有 L4，loop 就是一次性 pipeline。

### 6.2 Loop 循环：三层闭环

"Loop"不是指跑一遍流水线，而是指**状态在一轮结束后作为下一轮的输入**。之前的实现只有单次流水线（Planner→Builder→Reviewer 跑完即止），P5 引入 durable STATE 后闭环变成三层嵌套。三层各有职责，缺任何一层都不是真正的 loop。

#### 第一层：单 loop 内部循环（一个 loop 内的多次往返）

**为什么需要**：让一次 loop 内部能自我纠正——计划错了用户能调整，代码没过审 Builder 能修。没有这层，Planner 一旦出错就只能整个 loop 失败重来。

```
① CP1 调整循环（Planner ↔ 用户）
   Planner 产出计划 → ⏸ 用户确认
   ├─ 继续   → 放行
   ├─ 调整   → 带 note 退回 Planner 重新规划（while True 循环）
   └─ 回退   → 终止

② Reviewer 熔断循环（Builder ↔ Reviewer，≤3 次）
   Builder 落盘 → Reviewer 用真实证据审查
   ├─ ALL_PASS      → 放行
   ├─ PARTIAL_FAIL  → 把 fix_direction 退回 Builder 修复
   └─ CRITICAL_FAIL / 达 MAX_ITER → loop_failed 升级给人

③ UX 审查升级（User Agent，前端任务）
   UX FAIL → 一次性升级给人（不做内部重试）
```

落地代码：CP1 是 `orchestrator.py` 的 `while True` + `adjust_notes` 累积；Reviewer 熔断是 `iteration` 计数 + `MAX_ITER=3`。这是**生成-评估分离**的核心：Builder 只改不评，Reviewer 只评不改，问题反馈转圈直到通过或熔断。

#### 第二层：跨 loop 循环（STATE 驱动）

**为什么需要**：让不同 loop 之间能传递经验。上次的未解决问题成为这次的任务，上次的失败约束成为这次的禁令。没有这层，跑 10 次 loop 互相不知道彼此的存在，每次都从零开始。

```
第 N 次 loop 结束 → update_state_after_loop()
    │  写入：last_loop_result / open_problems / constraints / token_consumption_total
    ▼
第 N+1 次 loop 开始 → load_project_state() → 注入 Planner / Builder 上下文
    │  读取：未解决问题成为新任务，constraints 成为禁令
    ▼
……循环往复，状态不断累积
```

P6 的**文件记忆（L5）也参与这一层**：记忆文件持久存在磁盘，每次 loop 启动扫描→小模型选择→注入，与 STATE 一起构成跨 loop 的"长期上下文"。区别是 STATE 是结构化约束（DB 行），文件记忆是非结构化参考（文件内容按需注入）。

#### 第三层：Critique 改进闭环（Post-Run Critique）

**为什么需要**：让系统能从自己的错误里学习。把前一轮犯的错变成后一轮的规则，让审查准确率持续收敛。没有这层，系统会反复犯同样的误报。

```
loop 完成 → generate_critique()（LLM 反思）
   │  产出：false_positives / duplicate_issues / adjustment_suggestions
   ▼
写入 STATE.critiques（保留最近 3 条）
   ▼
下次 loop 启动 → critiques 作为约束注入 prompt（"上次误报过这个问题，别再报"）
   ▼
持续收敛：减少重复问题、提高审查准确率
```

#### 三层闭环汇总图

```
        ┌───────────────────── L4 STATE 脊柱 + L5 文件记忆 ─────────────────────┐
        │  上次结果 / 未解决问题 / 约束 / token / critique / 相关记忆文件        │
        └───────────────────────────────▲──────────────────────────────────────┘
                                        │ 下次 loop 启动读取
┌───────────────────────────────────────┴────────────────────────────────────┐
│  run_loop：                                                               │
│    Master(冷启动,写L3) → Planner ⇄(CP1 调整) → Builder                      │
│    → Reviewer ⇄(熔断≤3) → User Agent → CP2 签字                             │
│       └──── 第一层：单 loop 内循环（自我纠正）────┘                            │
│    L1 事件流全程记录，SSE 推前端                                             │
└───────────────────────────────────────▲────────────────────────────────────┘
                                        │ 结束更新
        ┌───────────────────────────────┴──────────────────────────────────┐
        │  update_state_after_loop + generate_critique                      │
        │  └─ 第二层（跨 loop，STATE 传递经验）+ 第三层（critique 自我改进）──┘
```

一句话总结：**第一层让单次 loop 能自我纠正，第二层让多次 loop 能传递经验，第三层让系统能从错误中学习**。三层都靠"状态写回→下次读取"这条脊柱串起来，这就是它从 pipeline 变成 loop 的本质。

### 6.3 完整状态机（含 P5 新增分支）

```
run_loop(loop_id, api_key, model, user_id, role_models, mode, project_name)
  │
  ├─ 0. 读 L2/L3/L4 上下文（restore_context + load_project_state）
  ├─ 1. Master 冷启动（仅无项目上下文时，写 L3）
  ├─ 2. Planner 循环（含 CP1）
  ├─ 3. [L1 Report Mode] 只读分析 → emit report → 更新 STATE → 结束（不落盘）
  ├─ 4. Builder（P5: 在独立 git worktree 落盘）
  ├─ 5. Reviewer 熔断循环（PARTIAL_FAIL 退回 Builder）
  ├─ 6. User Agent UX 审查（前端任务）
  ├─ 7. CP2 最终签字
  │      approve → worktree 合并回主分支 → done → 更新 STATE + Critique
  │      reject  → worktree 丢弃 → failed
  └─ 异常分支
        BudgetExhausted → budget_exhausted 事件 → paused
        LoopPaused     → paused 事件 → paused
        其他异常         → error 事件 → failed
```

P5 新增模块一览：

| 模块 | 作用 | 文件 |
|------|------|------|
| STATE 脊柱 | 跨 loop 持久记忆（L4） | `agents/state.py`、`agents/db.py`（`project_states` 表） |
| 定时触发器 | cron 驱动自动 triage loop（L1 报告 / L2 行动） | `agents/schedule.py`、`agents/db.py`（`loop_schedules` 表） |
| Worktree 隔离 | Builder 在独立 git worktree 落盘，成功才合并 | `agents/worktree.py` |
| Budget + Kill Switch | 每 loop token 预算，超限暂停；`loop-pause-all` 全局开关 | `agents/budget.py`、`agents/db.py` |
| Post-Run Critique | 结束自动反思，写入 STATE 作为下次约束 | `agents/critique.py` |

### 6.4 文件记忆（File Memory，P6）

> L4 STATE 脊柱是"结构化约束记忆"（DB 行），L5 文件记忆是"文件式上下文记忆"：按文件组织，每文件头部是元数据（type/tag），正文是详细内容，由小模型按需选择性地注入 Agent 上下文。

#### 设计方案（四步）

```
1.扫描   记忆目录递归扫描，最多 200 个文件，每文件只读前 30 行（元数据），不调 LLM，成本极低
         ↓
2.摘要   所有元数据列成清单：[类型标签] 文件名 (最后修改时间)
         ↓
3.选择   用户 query + 清单 → 小模型选择最相关的 5 条
         - 宁缺毋滥：无关则返回空列表
         - 不选正在使用的工具的说明文档，可选已知问题/注意事项
         - 后校验：逐一确认文件真实存在（确定性代码兜底，不信任模型路径）
         ↓
4.注入   选中的记忆注入上下文
         - 单条上限 4kb，超限则截断 + 指针（指向文件路径便于按需读取）
         - 单轮上限 20kb，会话累计上限 60kb（超过停止注入 → 压缩）
         - 过期警告：超过 2 天未修改的记忆附过期提醒，使用前先验证实际状态
```

#### 代码结构

| 文件 | 职责 |
|------|------|
| `memory/file_memory.py` | 核心模块：扫描/清单/选择/注入/预算/过期 |
| `agents/orchestrator.py` Phase 0 | loop 启动时调用 `build_file_memory_context` 注入 |
| `agents/api.py` | `GET /memory/scan`（扫描预览）+ `POST /memory/select`（选择预览） |
| `memory/__init__.py` | 导出 file_memory 全部公共接口 |
| `test/test_file_memory.py` | 13 项测试覆盖扫描/清单/后校验/过期/预算 |

#### 关键实现细节

- **扫描不调 LLM**：`scan_memory_files()` 是纯文件系统操作，只 `readlines(30)`，200 个文件几千行文本，毫秒级。
- **类型标签自动提取**：先从头部 `type:`/`tag:`/`kind:`/`category:` 字段提取，失败则按目录名推断。
- **后校验是确定性的**：`_post_validate()` 只保留真实存在于磁盘且未路径穿越的文件，不信任模型返回的路径。
- **注入预算三重控制**：单条 4kb（超限截断+指针）、单轮 20kb、会话 60kb（持久化到 `file_memory_usage` 表，跨 loop 累计）。
- **过期提醒**：`check_stale()` 检查 `mtime`，超过 2 天附加警告文本，提醒 Agent 验证实际状态。
- **loop 自动注入**：`orchestrator.py` Phase 0 在读 L2/L3/L4 后，扫描项目目录或 `data/memory/`，调用小模型选择后注入 `user_context`，并 emit `memory_injected` 事件（前端可见扫描数/选中数/注入字节数/过期文件）。

#### 新增 API

| 端点 | 说明 |
|------|------|
| `GET /api/agents/memory/scan?root=...` | 扫描记忆目录（不调 LLM），返回元数据清单 |
| `POST /api/agents/memory/select` | query + 清单 → 小模型选择 → 预览注入内容 |

### 6.5 Agent 之间怎么传递信息

> 核心问题：Planner 产出的计划，Builder 怎么拿到？Reviewer 又怎么看到 Builder 的产物？这是多智能体系统的关键设计。

#### 传递方式：结构化 JSON 上下文注入（不是文件接力，也不是消息历史）

Agent 之间**不直接通信**。`orchestrator.py` 是唯一中枢，负责把上游 Agent 的输出序列化后注入下游 Agent 的 prompt。具体做法：

1. 上游 Agent 用 LLM 产出一坨文本 → `_parse_json()` 容错解析成 dict → `_validate_model()` 用 Pydantic 校验成结构化对象（`Plan` / `BuildOutput` / `ReviewResult`）。
2. `orchestrator` 把这个 Pydantic 对象 `model_dump()` 成 JSON，拼进下游 Agent 的 `user_context` 字符串。
3. 下游 Agent **独立调用 LLM**，只看这次注入的上下文，**不带任何对话历史**（防污染）。

#### 每一段传递的实际代码

| 上游 → 下游 | 注入内容 | 代码位置 |
|------------|----------|----------|
| Master → Planner | Master 对齐出的项目上下文（JSON）| `user_context += "\n\n" + master_bits` |
| Planner → Builder | `## 执行计划\n{plan.model_dump() as JSON}\n\n## 任务\n{task}` | `build_ctx = ...` |
| Builder → Reviewer | `## 执行计划\n{plan}\n\n## Builder 输出\n{build}\n\n## 实际执行证据（命令输出）\n{verify_results}` | `review_ctx = ...` |
| Reviewer → Builder（退回修复）| `## Reviewer 退回意见\n{review.fix_direction}`（追加到 build_ctx）| `build_ctx += ...` |
| STATE/文件记忆 → 所有 Agent | STATE 摘要 + 选中的记忆文件（Phase 0 一次性注入 user_context，所有 Agent 共享）| `context_bits.append(...)` |

#### 为什么这样设计（取舍）

| 设计 | 好处 | 代价 |
|------|------|------|
| **全上下文 JSON 注入** | 下游拿到完整、结构化、可校验的上游输出，不丢字段 | 上下文随传递累积变长，token 消耗高 |
| **不带对话历史** | Planner 的废话不污染 Builder，每个 Agent 只看该看的 | 无法基于多轮对话记忆（靠 STATE 补偿） |
| **Pydantic 校验** | 上游输出格式错误立刻 `RuntimeError` 暴露，不会把垃圾传给下游 | 对 LLM 输出格式有要求（prompt 强制 JSON） |
| **orchestrator 中枢** | 传递路径清晰、可审计（每步都 emit 事件）| 单点编排，非真正分布式 agent 通信 |

#### 辅助载体：事件表（不是 agent 通信主通道）

`loop_events` 表记录每一步（`_emit`），但它是给**前端展示和刷新回放**用的，**不是 agent 间传递信息的主载体**。Agent 拿到的上下文是 orchestrator 实时拼的 JSON，不是从事件表读的。两者并行：事件表负责"可观测"，JSON 注入负责"传递"。

#### 已知不足（架构 gap）

当前是**全上下文注入**：Builder 能看到 Planner 的整个计划，Reviewer 能看到 Builder 的整个输出。缺少**选择性回忆**和**上下文预算**——理想做法是下游只拿自己需要的字段。P6 的文件记忆已部分缓解（按需选择注入），但 agent 间传递本身仍是全量 JSON，后续可考虑字段级裁剪 + 上下文预算。

---

## 第七部分：已知限制 / 后续建议

1. **Builder 落盘需 project_dir**：P5 已在输入区上方提供"目录"输入框（`loop-settings-bar.tsx`），但用户需手动填绝对路径；建议后续改为项目目录选择器/自动探测。
2. **User Agent 截图依赖 playwright**：未安装时 UX 审查降级为纯文本视角（UX_SKIPPED 不阻塞）。
3. **对话历史未持久化**：会话列表只在内存，刷新丢失（Agent Loop 事件本身有 DB 回放）。
4. **per-role 模型跨 provider 时 key 管理**：如 Planner 用 OpenAI、Reviewer 用 DeepSeek，目前只用一套 key。
5. **匿名用户无 Master 冷启动**：Master 需要 user_id（登录态），匿名用户直接走 Planner。
6. **Schedule 调度器是进程内任务**：多 worker 部署时每个 worker 各自触发，可能重复执行；生产建议用外部 cron + `/schedules` 接口或引入分布式锁。
7. **L2 行动模式需人工确认**：Schedule 触发的 L2 loop 会在 CP2 暂停，用户需通过 `/loops` 找到 loop_id 再调 `/decision` approve 才会落盘。
8. **Worktree 依赖 git 仓库**：project_dir 非 git 仓库时回退为直接在主目录落盘（无隔离保护）。
9. **文件记忆目录默认空**：`data/memory/` 初始为空，需用户放入记忆文件（每文件头部写 `type: xxx` 标签）才能生效；也可通过 `FILE_MEMORY_ROOT` 环境变量或前端 API 指定其他目录。
10. **文件记忆选择依赖小模型**：小模型不可达时跳过注入（不影响 loop 主体流程）；建议用便宜模型（如 deepseek-chat）以控制成本。
