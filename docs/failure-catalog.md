# Agent Loop 失败模式目录

> 基于 `loop-engineering` 参考仓库的 12 种失败模式，系统性分类。
> 严重度: S1=烦人（可自动恢复）| S2=有害（需人工介入）| S3=严重（数据/安全风险）

---

## S1 - 烦人（可自动恢复）

### 1. Token Burn（Token 烧钱）

| 属性 | 值 |
|------|-----|
| **状态** | 已覆盖 — 有预算上限 + 新增 early exit |
| **描述** | 空 watchlist 或无需修改时，loop 仍跑完完整 Planner→Builder→Reviewer 链路 |
| **检测** | `items_found=0 AND files_changed=0` 的 run_log |
| **防护** | `LOOP_TOKEN_BUDGET` 环境变量 + `BudgetExhausted` 异常 + early exit（P1-6） |
| **残余风险** | 低 |

### 2. State Rot（状态腐烂）

| 属性 | 值 |
|------|-----|
| **状态** | 新增防护 — prune_state() |
| **描述** | STATE.md 中的 open_problems 只追加不清理，已解决的问题永远留在列表里 |
| **检测** | open_problems 数量线性增长却无对应 resolution |
| **防护** | `prune_state()` 每次 loop 启动前清理（P0-2） |
| **残余风险** | prune 依赖 git issue/PR 状态查询（需 git 仓库）|

### 3. Notification Fatigue（通知疲劳）

| 属性 | 值 |
|------|-----|
| **状态** | 新增防护 — 通知过滤（P2-10）|
| **描述** | 每次 loop 的每个阶段都推送 SSE 事件，用户麻木后忽略真正重要的通知 |
| **检测** | 用户 ignore/miss 升级事件 |
| **防护** | NOTIFY_ONLY_WHEN 白名单：仅在 checkpoint/escalation/budget_warning/denylist_hit/failed 时通知 |
| **残余风险** | 过滤过严可能漏掉真正需要关注的事件 |

### 4. Prompt Drift（Prompt 漂移）

| 属性 | 值 |
|------|-----|
| **状态** | 未覆盖 |
| **描述** | 随时间推移，修复的 prompt 优化使 agent 行为逐渐偏离最初设计预期 |
| **检测** | 定期 A/B 测试（对比新旧 prompt 在同样输入下的输出差异）|
| **防护** | 无（待实现：prompt 版本化管理 + 回归测试套件）|
| **残余风险** | 高 — 每个 prompt 调整都可能引入行为漂移 |

---

## S2 - 有害（需人工介入）

### 5. Infinite Fix Loop（无限修复循环）

| 属性 | 值 |
|------|-----|
| **状态** | 已覆盖 — MAX_ITER=3 |
| **描述** | Builder-Reviewer 反复 PARTIAL_FAIL 循环，都不收敛 |
| **检测** | `iteration >= MAX_ITER` 触发熔断 |
| **防护** | `orchestrator.py:830` — 迭代熔断后升级 CRITICAL_FAIL |
| **残余风险** | MAX_ITER=3 对某些复杂问题可能不够；反之某些简单问题可能在第 2 次就该升级 |

### 6. Verifier Theater（验证走过场）

| 属性 | 值 |
|------|-----|
| **状态** | 部分覆盖 |
| **描述** | Reviewer 证据是"看着没问题"而非真实命令输出，形同虚设 |
| **检测** | stage_results 中 evidence 字段为空或太短 |
| **防护** | Reviewer prompt 要求真实证据；验证命令输出注入 review_ctx |
| **残余风险** | Reviewer 和 Builder 使用同一模型时"同谋"风险；应要求不同模型 |

### 7. Over-Reach（越界操作）

| 属性 | 值 |
|------|-----|
| **状态** | 新增防护 — gate.yaml（P0-1）|
| **描述** | Builder 修改了不该碰的文件（.env, auth/, payments/）|
| **检测** | `gate.check_build()` 落盘前机械拦截 |
| **防护** | path denylist + 命令白名单 + on_hit abort_immediately |
| **残余风险** | denylist 需要人工维护；新建的敏感目录可能未列入 |

### 8. Comprehension Debt Spiral（理解债务螺旋）

| 属性 | 值 |
|------|-----|
| **状态** | 未覆盖 |
| **描述** | loop 越快，你没读过的代码越多。CP2 签字如果变成 rubber-stamp，理解债务爆炸 |
| **检测** | 用户在 CP2 的平均 decision 时间持续下降 |
| **防护** | 无（需前端 UX 设计：CP2 强制展示 diff + 最少阅读时间）|
| **残余风险** | 高 — 这是文化问题，不是技术问题 |

### 9. Cognitive Surrender（认知投降）

| 属性 | 值 |
|------|-----|
| **状态** | 未覆盖 |
| **描述** | "loop 会处理"——开发者不再有设计意见，失去对 codebase 的整体把控 |
| **检测** | 指标：如果成功指标是"跑了几次"而非"省了多少时间且质量达标" |
| **防护** | 无（需组织层面：成功指标重新定义 + 定期人工 review）|
| **残余风险** | 高 — 这是组织文化问题 |

### 10. Parallel Collision（并行碰撞）

| 属性 | 值 |
|------|-----|
| **状态** | 新增防护 — BranchLock（P1-5）|
| **描述** | 两个 Builder 同时修改同一批文件，worktree 隔离解决机械冲突但不解决逻辑冲突 |
| **检测** | `acting_on` 字段检查 |
| **防护** | STATE.md 的 acting_on 分支锁 + spawn 前冲突检测 |
| **残余风险** | 仅当前 Orbit 实例内有效；多实例部署需外部锁 |

### 11. Escalation Failure（升级失败）

| 属性 | 值 |
|------|-----|
| **状态** | 部分覆盖 — 有升级但无超时 |
| **描述** | High Priority 问题生成后 48h 无人处理，升级链断裂 |
| **检测** | `open_problems` 中"High Priority"超过 24h 未处理 |
| **防护** | 升级有 emit 但无超时告警（待实现）|
| **残余风险** | 中 — 依赖人看到通知并行动 |

### 12. Blind Spot Accumulation（盲点积累）

| 属性 | 值 |
|------|-----|
| **状态** | 未覆盖 |
| **描述** | Reviewer 每次审查相同的维度，新的代码模式（新框架、新范式）产生后没有更新审查维度 |
| **检测** | 引入新依赖/框架后，Reviewer 未更新 stage_results 覆盖范围 |
| **防护** | 无（待实现：Reviewer prompt 动态注入项目 spec 中的 completion_dimensions）|
| **残余风险** | 中 — 新引入的技术栈可能成为审查盲区 |

---

## 防护总结

| 故障模式 | 严重度 | 防护状态 | 覆盖方式 |
|---------|--------|---------|---------|
| Token Burn | S1 | ✅ 已覆盖 | budget + early exit |
| State Rot | S1 | ✅ 新增 | prune_state() |
| Notification Fatigue | S1 | ✅ 新增 | 通知过滤白名单 |
| Prompt Drift | S1 | ❌ 未覆盖 | — |
| Infinite Fix Loop | S2 | ✅ 已覆盖 | MAX_ITER=3 |
| Verifier Theater | S2 | ⚠️ 部分 | prompt + 证据注入 |
| Over-Reach | S2 | ✅ 新增 | gate.yaml |
| Comprehension Debt | S2 | ❌ 未覆盖 | — |
| Cognitive Surrender | S2 | ❌ 未覆盖 | — |
| Parallel Collision | S2 | ✅ 新增 | BranchLock |
| Escalation Failure | S2 | ⚠️ 部分 | 有升级，缺超时 |
| Blind Spot Accumulation | S2 | ❌ 未覆盖 | — |

**覆盖率**: 7/12 已覆盖，2/12 部分覆盖，3/12 未覆盖（其中 2 个是组织/文化问题）
