# Agent Loop 行为约束

> AI Agent 自主运行时最大的风险是"没有约束"。Orbit 通过两份配置文件构建了双重安全门控——机器可执行的 `gate.yaml` 和运行时约束 `loop-constraints.md`。

---

## 双重约束体系

```
         ┌─────────────────────────────┐
         │     gate.yaml               │
         │  "你不能碰什么"                │
         │  文件黑名单 · 命令白名单        │
         │  自动合并规则                  │
         ├─────────────────────────────┤
         │     loop-constraints.md     │
         │  "你不能什么时候做什么"          │
         │  预算 · 时间 · 碰撞 · 升级     │
         └─────────────────────────────┘
```

**两者配合**：gate.yaml 管空间（哪些资源不能动），loop-constraints.md 管时间（什么情况下做什么）。

---

## gate.yaml：机器可执行的安全门控

### 文件黑名单（denylist）

Agent Loop 在操作文件前，必须先检查目标路径是否在黑名单中：

```yaml
denylist:
  # 密钥 & 凭证
  - .env
  - .env.*
  - "**/secrets/**"
  - "**/*-key.json"
  - "**/serviceAccount.json"

  # 认证相关
  - "**/credentials/**"
  - "**/certs/**"

  # 支付 & 计费
  - "**/payments/**"
  - "**/billing/**"

  # 基础设施配置
  - "**/terraform/**"
  - "**/infrastructure/**"

  # CI/CD
  - ".github/workflows/*-deploy*"
  - "**/deploy.yml"

  # 数据库迁移（高风险）
  - "**/migrations/**"

enforcement: reject  # 命中黑名单 = 拒绝执行
on_hit:
  action: abort_immediately
  notify: true
```

**`enforcement: reject`** 意味着这不是"建议"，是铁律。Agent 试图编辑 `.env` 会被立即中止，并通知用户。

### 命令白名单（allowed_commands）

Agent Builder 在执行代码之前，生成的验证命令必须匹配白名单：

```yaml
allowed_commands:
  - "python -m pytest"
  - "python3 -m pytest"
  - "npm test"
  - "npm run lint"
  - "go test"
  - "cargo test"
  - "pytest"
  - "eslint"
  - "mypy"
  - "ruff check"
  - "black --check"
  - "git status"
  - "git diff"
  - "git log"
  # ... 白名单外的命令一律拒绝
```

**不会出现在白名单中的命令**：`rm -rf`、`sudo`、`curl | sh`、`eval`、`chmod 777`——Agent 无法生成并执行这些命令。

### 自动合并白名单

```yaml
auto_merge_allowlist:
  only_if:
    - change_type_is: ["typo", "lint_fix", "import_sort", "comment_fix", "doc_update"]
    - not_in_denylist: true
    - all_tests_pass: true
```

只有 5 类"不会改逻辑"的变更可以自动合并。且必须满足"不涉及黑名单文件"和"所有测试通过"两个条件。

---

## loop-constraints.md：运行时行为约束

### 预算控制

```
- Token 消耗达到每日上限 80% 时，切换到仅报告模式（L1）
- 如果 `loop-pause-all` 开关激活，立即退出
- 单次 loop 不超过 10 万 token
```

设计意图：防止 AI 陷入"无限循环调优"（反复生成→审查→修改→再生成），烧光预算。

### 时间约束

```
- 不要在凌晨 2-6 点自动运行破坏性操作（L2 模式）
- 同一分支每小时最多一次 loop 修改
- triage 模式不占用分支锁（只读）
```

凌晨是业务低峰期，但也是"AI 无人值守的代码修改没人 review"的高风险窗口。

### 碰撞控制

```
- 同一分支每小时最多一个 action loop 修改
- triage 模式不占用分支锁（只读报告）
- action 模式必须获取分支锁才能落盘
```

**分支锁机制**：两个 loop 同时看到同一个分支有问题，但只有一个能拿到锁执行修改。另一个会被 skip，防止并发修改冲突。

### 升级机制

```
- 同一问题 48h 内升级 2 次以上 → 暂停 auto-fix
- High Priority 问题超过 24h 未处理 → 通知用户
- CRITICAL_FAIL 立即升级，不等待
```

关键设计：**同一个问题反复出现说明 AI 修不好，需要人工介入**。暂停 auto-fix 防止 AI 陷入"修了又坏、坏了又修"的死循环。

---

## 约束执行流程

```
Agent Loop 运行
    │
    ├── 读 gate.yaml（每次 loop 开始前）
    │   ├── 目标文件在 denylist？ → abort
    │   ├── 命令在白名单？      → 通过
    │   └── 需自动合并？        → 检查 change_type + tests_pass
    │
    └── 读 loop-constraints.md（每次 loop 开始前）
        ├── Token 预算超 80%？   → 切 L1 只读模式
        ├── 凌晨 2-6 且 L2？     → 拒绝破坏性操作
        ├── 同分支已有锁？       → skip
        └── 同问题升级 2 次？    → 暂停 auto-fix + 通知用户
```
