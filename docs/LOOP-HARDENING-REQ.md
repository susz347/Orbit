# Orbit Agent Loop - 安全加固 & 运维增强需求文档

> 版本: v1.0
> 日期: 2026-08-07
> 状态: 已完成

---

## 概述

基于 `loop-engineering` 参考仓库的最佳实践，对 Orbit agent loop 进行全面加固。按优先级分为 P0（安全必须）、P1（运维必须）、P2（体验增强）三个层级。

---

## P0: 安全护栏

### 1. 路径 Denylist + `gate.yaml` 机械执行

**现状问题**：
- `orchestrator.py` 有命令执行白名单（RCE 防护），但 Builder 落盘时没有路径 denylist
- 没有 `gate.yaml` 这样的机器可读安全配置
- `project-spec.md` 的 `forbidden_paths` 仅用于 Planner 的 prompt 提示，不是机械执行

**需求**：

#### 1.1 创建 `gate.yaml` 配置文件

在项目根目录（或 loop 运行时的工作目录）创建 `gate.yaml`：

```yaml
# gate.yaml — 机器可读，机械执行
# Agent loop 每次运行前必须读取并遵守

denylist:
  # 密钥 & 凭证
  - .env
  - .env.*
  - .env.local
  - .env.production

  # 认证相关路径
  - "**/secrets/**"
  - "**/credentials/**"
  - "**/certs/**"
  - "**/*.pem"
  - "**/*-key.json"
  - "**/serviceAccount.json"

  # 支付 & 计费
  - "**/payments/**"
  - "**/billing/**"

  # 基础设施配置
  - "**/terraform/**"
  - "**/*.tfstate"
  - "**/infrastructure/**"

  # CI/CD 配置
  - ".github/workflows/*-deploy*"
  - "**/deploy.yml"

  # 数据库迁移（高风险）
  - "**/migrations/**"

# 执行模式
enforcement: reject  # reject | warn | log_only

# 当命中 denylist 时
on_hit:
  action: abort_immediately  # abort_immediately | escalate | warn_only
  notify: true
  escalate_after: 24h

# 允许的测试命令前缀
allowed_commands:
  - "python -m pytest"
  - "npm test"
  - "npm run test"
  - "go test"
  - "cargo test"
  - "make test"
  - "pytest"
  - "eslint"
  - "mypy"
  - "ruff"
  - "black --check"
  - "prettier --check"

# 自动合并允许列表（L3 无人值守模式）
auto_merge_allowlist:
  only_if:
    - change_type_is: ["typo", "lint_fix", "import_sort", "comment_fix"]
    - not_in_denylist: true
    - all_tests_pass: true
```

#### 1.2 实现 `loop-gate` 检查

在 `backend/app/agents/` 下新增 `gate.py`：

```python
class LoopGate:
    """
    安全门控，每次 Builder 落盘前和 loop 启动时执行。
    
    功能:
    1. 加载 gate.yaml（支持项目级和全局默认）
    2. check_path(path) -> bool: 检查路径是否在 denylist
    3. check_build(build_files) -> GateResult: 批量检查
    4. check_command(cmd) -> bool: 检查命令是否在 allowed_commands
    """
```

#### 1.3 集成到现有流程

- `orchestrator.py` 的 `_apply_build()` 在落盘**每个文件之前**调用 `gate.check_path(file_path)`
- 命中 denylist 时：中断 loop、记录事件、推送 SSE 警告
- `builder` prompt 中也注入 denylist 摘要（双重防护）

---

### 2. State Prune 步骤

**现状问题**：
- `state.py` 的 `STATE.md` 只追加不清理
- 已合并的 PR、已关闭的 issue 永远留在 `open_problems` 中
- 导致上下文膨胀和理解债务螺旋

**需求**：

#### 2.1 实现 `prune_state()`

在 `state.py` 中新增：

```python
def prune_state(project_state: ProjectState, git_info: dict) -> ProjectState:
    """
    在每次 loop 开始前清理过时状态。
    
    清理规则:
    1. 检查 open_problems 中的每项，如果关联的 issue/PR 已关闭 → 移到 resolved 列表
    2. 超过 30 天未更新的 open_problems → 标记为 stale
    3. critique 历史超过 50 条 → 只保留最近 30 条 + 每条总结
    4. 已解决的问题移到 closed_problems（新增字段）
    """
```

#### 2.2 在 loop 启动时调用

- `orchestrator.py` 的 `restore_context()` 阶段，在加载 STATE 后调用 `prune_state()`
- 清理后的 state 写回 STATE.md 和 DB

---

## P1: 运维保障

### 3. 约束文件 `loop-constraints.md`

**现状问题**：
- 约束散落在 `prompts.py`、`orchestrator.py` 代码和场景文件里
- 用户无法编辑运行时行为规则（如"最多尝试几次""哪些路径不能碰"）

**需求**：

#### 3.1 创建 `loop-constraints.md`

位于项目根目录（与 STATE.md 同级）：

```markdown
# Agent Loop 约束文件

> 每次 loop 运行前必须读取。如需修改，在下次 loop 开始前生效。

## Push & Merge
- 推送前必须告知用户
- 禁止自动合并到 main 分支（需人工确认）
- 合并前必须通过所有测试

## Paths
- 禁止编辑 `.env`, `.env.*`, `auth/`, `payments/`, `secrets/`
- 禁止编辑基础设施配置（不分环境）
- 编辑超过 5 个文件时需要更严格的审查

## Code
- 修改代码后必须运行测试
- 禁止禁用测试来让 CI 变绿
- 每个问题最多 3 次修复尝试，超过则升级

## Budget
- Token 消耗达到每日上限 80% 时，切换到仅报告模式
- 如果 `loop-pause-all` 开关激活，立即退出

## Schedule
- 不要在凌晨 2-6 点自动运行破坏性操作
- 同一分支每小时最多一次 loop 修改
```

#### 3.2 实现 `load_constraints()`

- 在 `orchestrator.py` 的 Phase 0（上下文注入）中读取并注入到各 Agent 的 system prompt
- 支持用户编辑，每次 loop 重新读取（无需重启服务）

---

### 4. Run-Log 持久化

**现状问题**：
- `orchestrator.py` 用 SSE 推送事件，事件写入 `loop_events` 表但不是结构化运行日志
- 无法回答"上周 loop 跑了几次？各什么结果？"

**需求**：

#### 4.1 新增 `run_logs` 表

```sql
CREATE TABLE run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_id INTEGER NOT NULL,
    loop_group_id INTEGER,
    user_id INTEGER NOT NULL,
    project_name TEXT NOT NULL,
    pattern TEXT DEFAULT 'manual',  -- manual | daily-triage | ci-sweeper | schedule
    
    -- 时间
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_s REAL,
    
    -- 阶段耗时
    planner_duration_s REAL,
    builder_duration_s REAL,
    reviewer_duration_s REAL,
    
    -- 结果统计
    items_found INTEGER DEFAULT 0,     -- Planner 发现的问题数
    files_changed INTEGER DEFAULT 0,    -- Builder 修改的文件数
    iterations INTEGER DEFAULT 0,       -- Builder-Reviewer 迭代次数
    outcome TEXT,                       -- success | paused | failed | rejected | cancelled
    
    -- 决策
    human_decision TEXT,                -- approved | rejected | adjusted
    
    -- 资源
    tokens_estimate INTEGER DEFAULT 0,   -- 估算 token 消耗
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    
    -- 安全
    denylist_hits INTEGER DEFAULT 0,
    budget_warnings INTEGER DEFAULT 0,
    escalations INTEGER DEFAULT 0,
    
    -- 快照
    state_snapshot TEXT,  -- JSON dump of project_state at loop end
    
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

#### 4.2 实现结构化日志写入

- `orchestrator.py` 的 `run_loop()` 开始时创建 `run_log` 记录
- 每个 phase 结束时更新对应字段
- loop 完成时写入最终状态
- 提供 API 查询：`GET /api/agents/loop/{loop_id}/run-log`

#### 4.3 指标接口

```python
GET /api/agents/metrics?project=xxx&days=7

返回:
{
  "total_runs": 42,
  "success_rate": 0.85,
  "avg_duration_s": 65.3,
  "total_tokens": 1250000,
  "false_positive_rate": 0.12,      # 人工拒绝率
  "mean_time_to_human_awareness_s": 3600,
  "escalations": 3,
  "denylist_hits": 0,
  "daily_breakdown": [...]
}
```

---

### 5. 多 Loop 碰撞检测

**现状问题**：
- Schedule 触发器可以同时跑多个 loop
- 两个 Builder 可能同时修改同一批文件
- worktree 隔离解决机械冲突，但不解决逻辑冲突

**需求**：

#### 5.1 实现分支级互斥锁

```python
# state.py 新增
class BranchLock:
    """
    基于 STATE.md 的分支级锁。
    
    规则:
    - 每个 action loop 在 acting_on 字段写入 "branch:xxx"
    - spawn 前检查所有其他 state 文件（如存在）
    - 如果目标分支已被占用 → skip + 记录到 run_log
    
    实现:
    - 使用 STATE.md 的 frontmatter JSON 中的 acting_on 字段
    - 轻量级，无需外部锁服务
    """
```

#### 5.2 集成到启动流程

- `orchestrator.py` 的 `run_loop()` 入口处：
  1. 检查是否有其他 active loop 在操作同一分支
  2. 有冲突 → `_finish(loop_id, "skipped", reason="branch_locked")`
  3. 无冲突 → 写入 `acting_on: "branch:main"`，完成后清除

#### 5.3 冲突检测配置项

在 `loop-constraints.md` 中：
```markdown
## Collision
- 同一分支每小时最多一个 loop 修改
- triage 模式不占用分支锁（只读）
- action 模式必须获取分支锁
```

---

### 6. Early Exit: 空 Watchlist 直接退出

**现状问题**：
- Planner 产生空计划时，仍然会跑完整的 Builder-Reviewer 链路
- 浪费 token 和时间

**需求**：

#### 6.1 Planner 空结果检测

在 `orchestrator.py` 中，Planner 返回后：

```python
plan = parse_plan_result(...)
if not plan.files_to_modify and not plan.issues_found:
    await _finish(loop_id, "completed", 
                  outcome_detail="idle_noop",
                  message="Planner 未发现需要处理的问题")
    return
```

#### 6.2 状态记录

- 空 loop 也写入 run_log（outcome="success", items_found=0, files_changed=0）
- SSE 推送 "loop_idle" 事件
- 不计入 false_positive_rate 计算

---

## P2: 体验增强

### 7. 失败模式目录

**现状问题**：
- 我们修了 10 个 bug，但没有系统性分类
- `AGENT-LOOP-DEVLOG.md` 是时间线日志，非分类目录

**需求**：

#### 7.1 创建 `docs/failure-catalog.md`

按 S1/S2/S3 分级，每种故障模式包含：
- 严重度
- 描述
- 检测方法
- 当前防护状态
- 残余风险

#### 7.2 内容提纲

覆盖 12 种故障模式：
1. Infinite Fix Loop（S2）— 已有 MAX_ITER=3
2. State Rot（S1→S2）— 新增 prune 步骤
3. Verifier Theater（S2）— 部分覆盖
4. Notification Fatigue（S1→S2）— 待优化
5. Token Burn（S1）— 新增 early exit
6. Over-Reach（S2→S3）— 新增 gate.yaml
7. Comprehension Debt Spiral（S2）— 待覆盖
8. Cognitive Surrender（S2 文化）— 待覆盖
9. Parallel Collision（S2）— 新增碰撞检测
10. Escalation Failure（S2）— 待覆盖
11. Prompt Drift（S1）— 待覆盖
12. Blind Spot Accumulation（S2）— 待覆盖

---

### 8. L1→L2→L3 毕业/降级标准

**现状问题**：
- 有 L1/L2 模式开关，但没有量化的毕业标准
- 不知道什么时候可以放心地从 L1 升到 L2，或从 L2 降到 L1

**需求**：

#### 8.1 毕业标准

```markdown
## L1（仅报告）→ L2（辅助修复）毕业条件:
- [ ] 连续 2 周 L1 运行，High Priority 噪声率 <20%
- [ ] Verifier 在手动尝试中验证过
- [ ] Denylist 已配置（gate.yaml）
- [ ] 测试命令已在 constraints 中定义
- [ ] Audit score ≥ 58（人工评分）

## L2（辅助修复）→ L3（无人值守）毕业条件:
- [ ] Denylist 在 gate.yaml 中
- [ ] Auto-merge 关闭 或 有严格 allowlist
- [ ] Kill switch 已就位且可独立触发
- [ ] 人工 gate 已文档化
- [ ] 连续 1 个月 L2 零工伤

## 降级触发器:
- Token 预算 >80% 不到周末 → L3 → L2
- 误报率（人工拒绝率）>30% → L2 → L1
- 同一 issue 48h 内升级 2+ 次 → 降一级
- 重大发布周 → 暂停 auto-fix，仅报告
```

#### 8.2 实现

- 在 STATE.md 中记录当前 level 和毕业进度
- API 端点：`GET /api/agents/loop/graduation-status`

---

### 9. 指标看板数据接口

**现状问题**：
- 没有运行统计数据

**需求**：

#### 9.1 API 扩展

基于 run_logs 表，提供：
- `GET /api/agents/metrics/summary` — 总体指标
- `GET /api/agents/metrics/daily` — 按日分组
- `GET /api/agents/metrics/by-pattern` — 按 pattern 分组

#### 9.2 关键指标

| 指标 | 计算方式 | 告警阈值 |
|------|---------|---------|
| 运行次数 | count(run_logs) | - |
| 成功率 | success / total | <80% 告警 |
| 误报率 | rejected / total human decisions | >30% 告警 |
| MTTHA | avg(time_to_human_awareness) | >4h 告警 |
| Token 消耗 | sum(total_tokens) | >80% 预算告警 |
| 迭代效率 | avg(iterations) | >3 告警 |

---

### 10. 通知规则优化

**现状问题**：
- 每次 loop 都推送 SSE 事件，没有"只在需要人类决策时通知"的过滤

**需求**：

在 `orchestrator.py` 中实现通知过滤：

```python
NOTIFY_ONLY_WHEN = [
    "checkpoint_reached",      # 需要人工 continue/adjust/rollback
    "escalation",              # 升级事件
    "budget_warning",          # 预算警告
    "denylist_hit",            # 安全违规
    "loop_failed",             # 运行失败
    "loop_completed_with_changes",  # 有修改完成
]

# 以下事件不主动通知
SKIP_NOTIFICATION = [
    "loop_idle",               # 无事可做
    "phase_started",           # 阶段开始
    "phase_completed",         # 阶段完成
    "progress_update",         # 进度更新
]
```

---

## 实施计划

| 编号 | 项目 | 优先级 | 预估工时 | 依赖 |
|------|------|--------|---------|------|
| 1 | 路径 Denylist + gate.yaml | P0 | 2h | - |
| 2 | State Prune | P0 | 1.5h | - |
| 3 | loop-constraints.md | P1 | 1h | - |
| 4 | Run-Log 持久化 | P1 | 2h | - |
| 5 | 多 Loop 碰撞检测 | P1 | 1.5h | 4 |
| 6 | Early Exit | P1 | 0.5h | - |
| 7 | 失败模式目录 | P2 | 1h | - |
| 8 | 毕业/降级标准 | P2 | 1h | 4 |
| 9 | 指标接口 | P2 | 1.5h | 4 |
| 10 | 通知规则优化 | P2 | 0.5h | - |

---

## 验收标准

- [ ] Builder 不能修改 `.env`、`auth/`、`payments/` 等路径
- [ ] STATE.md 中的已解决问题在下次 loop 前被清理
- [ ] `loop-constraints.md` 修改后下次 loop 立即生效
- [ ] 每次 loop 运行产生结构化 run_log 记录
- [ ] 两个同时修改同一分支的 loop 会检测到冲突并 skip
- [ ] 空 watchlist 的 loop 直接退出，不消耗后续 token
- [ ] failure-catalog.md 包含 12 种故障模式的完整描述
- [ ] 毕业标准可量化、可追踪
- [ ] 指标接口返回正确的统计数据
- [ ] 非关键事件不再产生通知
