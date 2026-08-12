# CI/CD

> CI/CD 不是测试体系本身，而是测试体系的执行者和门卫——每次 push/PR 自动跑测试、lint、安全扫描，失败则阻断合并。

---

## 与测试体系的关系

```
测试体系回答：怎么测
CI/CD 回答：什么时候测、测完怎么办
```

---

## GitHub Actions 配置

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend-tests:
    name: "Backend Tests (Python ${{ matrix.python-version }})"
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]   # 三版本并行
      fail-fast: false  # 一个版本挂了不取消其他版本
```

### Backend Tests Job

```yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-python@v5
    with:
      python-version: ${{ matrix.python-version }}

  - name: Install dependencies
    working-directory: backend
    run: |
      pip install --upgrade pip
      pip install -r requirements.txt

  - name: Lint with ruff
    working-directory: backend
    run: |
      pip install ruff
      ruff check app/ --ignore=E501,F841 || true  # 先不阻塞 CI

  - name: Run tests
    working-directory: backend
    run: python -m pytest test/ -v --tb=short
```

**Python 三版本矩阵**：确保代码在 3.10、3.11、3.12 上都能跑。`fail-fast: false` 意味着一个版本失败不影响其他版本的测试继续进行。

**ruff lint 先不阻塞**：`|| true` 表示 lint 报错不会让 CI 变红，等团队逐步修复 lint 问题后再收紧。

### Dependency Security Scan Job

```yaml
dependency-scan:
  name: "Dependency Security Scan"
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Run pip-audit
      working-directory: backend
      run: |
        pip install pip-audit
        pip-audit -r requirements.txt
```

`pip-audit` 检查 `requirements.txt` 中的每个包是否在 PyPA 漏洞数据库中有已知 CVE。

### Frontend Tests Job

```yaml
frontend-tests:
  name: "Frontend Tests"
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: 20

    - name: Install dependencies
      working-directory: frontend
      run: npm ci

    - name: Lint
      working-directory: frontend
      run: npm run lint

    - name: Build check
      working-directory: frontend
      run: npm run build
```

至少确保前端能编译通过。配合 Vitest 测试框架，后续可加入 `npm run test`。

---

## 完整的质量门控链

```
push/PR to main
    │
    ├── Backend Tests (Python 3.10, 3.11, 3.12)
    │   ├── ruff lint
    │   └── pytest (283 用例)
    │
    ├── Dependency Security Scan
    │   └── pip-audit (CVE 检查)
    │
    └── Frontend Tests
        ├── npm lint
        └── npm build check
              │
         全部通过？
         /        \
       是          否
        │           │
    ✅ 可合并    ❌ 阻断合并
```

---

## 当前状态

| 阶段 | 状态 |
|------|------|
| CI（持续集成） | ✅ 已完成 |
| CD（持续部署） | ⏳ 待实施 — Docker 镜像构建 + 推送到 Registry + 自动部署 |

CD 需要的 Dockerfile 和 docker-compose.yml 已就绪，可在 CI 末尾追加 `docker build && docker push` 步骤实现。
