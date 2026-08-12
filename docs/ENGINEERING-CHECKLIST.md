# Orbit 工程化体系清单

> 生成日期：2026-08-11 | 目标：从"能跑通"到"能交付"的生产级系统

---

## 一、已具备的工程化能力 ✅

### 1. 测试体系
| 能力 | 实现 | 文件 |
|------|------|------|
| 30 测试文件覆盖全部模块 | pytest + pytest-asyncio | `backend/test/test_*.py` (30 个文件) |
| 环境隔离 | conftest.py 自动切临时目录 | `backend/test/conftest.py` |
| Mock LLM | fixture 拦截 HTTP 请求 | `conftest.py: mock_llm` |
| 自动清理 | `_clean_state` autouse fixture | `conftest.py` |
| 认证辅助 | `auth_token` + `auth_headers` fixture | `conftest.py` |
| 禁用限流 | TestClient 中禁用 slowapi | `conftest.py: client` |

### 2. 渐进式认证
| 能力 | 实现 | 文件 |
|------|------|------|
| JWT 签发/验证 | HS256, 7 天过期, python-jose | `backend/app/middleware/auth.py` |
| 密码哈希 | bcrypt, work_factor=12, 自动加盐 | `backend/app/multitenant/password.py` |
| 可选认证 | `get_optional_user()` 无 Token 不报错 | `backend/app/middleware/auth.py` |
| 强制认证 | `get_current_user()` Depends 拦截 401 | `backend/app/middleware/auth.py` |
| SQL 注入防护 | 全部使用 `?` 参数化查询 | `backend/app/multitenant/users.py` |
| 租户隔离 | collection 按 `user_{user_id}` 隔离 | `backend/app/multitenant/users.py` |
| 授权控制 | loop 级归属校验 | `backend/app/agents/api.py: _check_loop_access()` |
| 登录限流 | 5 次/分钟 slowapi | `backend/app/api/auth.py` |

### 3. 角色 Onboarding
| 能力 | 实现 | 文件 |
|------|------|------|
| 5 种角色模板 | developer/pm/manager/student/enterprise | `backend/app/onboarding/` |
| 自动偏好配置 | 角色选择后自动配置默认值 | `backend/app/api/onboarding.py` |
| 首次使用引导 | 非空白页，带引导流程 | `backend/app/onboarding/` |

### 4. 多模型管理
| 能力 | 实现 | 文件 |
|------|------|------|
| 全局模型配置 | settings 单例 | `backend/app/config.py` |
| Per-Role 独立模型/Key | Planner/Builder/Reviewer/User 各自配置 | `backend/app/llm/` |
| 3 层级联路由 | 规则引擎 → 语义路由 → LLM 分类 | `backend/app/router/` |
| 安全分类器 | 敏感内容过滤 | `backend/app/router/` |

### 5. Logo's 对话总结（审计笔记）
| 能力 | 实现 | 文件 |
|------|------|------|
| 结构化 Markdown 输出 | `data/memory/YYYY-MM-DD.md` | `backend/app/api/logos.py` |
| 人机双读 | Markdown 格式，git diff 可审计 | `data/memory/` |
| 自动持久化 | 对话结束后自动写入 | `backend/app/api/logos.py` |

### 6. 全链路追踪
| 能力 | 实现 | 文件 |
|------|------|------|
| X-Request-ID 注入 | 优先使用客户端传的值，否则生成 UUID4 | `backend/app/middleware/request_id.py` |
| 响应回传 | `X-Request-ID` 头在响应中原样返回 | `backend/app/middleware/request_id.py` |
| 上下文传递 | `get_request_id(request)` 供下游模块使用 | `backend/app/middleware/request_id.py` |

### 7. 安全基线
| 能力 | 实现 | 文件 |
|------|------|------|
| IP 限流 | slowapi `get_remote_address` | `backend/app/main.py` |
| CORS 配置 | 白名单 origin + 自定义 headers | `backend/app/main.py` |
| XSS 防护 | 前端 rehype-sanitize | `frontend/` |
| 命令白名单 | gate.yaml 允许的命令前缀 | `gate.yaml` |
| 文件黑名单 | denylist（密钥、支付、CI/CD 等） | `gate.yaml` |
| 强制拒绝 | `enforcement: reject` | `gate.yaml` |

### 8. Agent Loop 约束（额外亮点）
| 能力 | 实现 | 文件 |
|------|------|------|
| 预算控制 | Token 上限 80% 警告、单次 ≤10 万 | `loop-constraints.md` |
| 时间约束 | 凌晨 2-6 禁止破坏性操作 | `loop-constraints.md` |
| 碰撞控制 | 同分支每小时最多 1 次 action loop | `loop-constraints.md` |
| 升级机制 | 48h 内升级 2 次 → 暂停 auto-fix | `loop-constraints.md` |
| 自动合并规则 | typo/lint/import_sort/doc_update 自动合并 | `gate.yaml` |
| 智能调度 | schedule 调度器每分钟检查到期 schedule | `backend/app/agents/schedule.py` |

### 9. 健康检查
| 能力 | 实现 | 文件 |
|------|------|------|
| 深度健康检查 | ChromaDB heartbeat + SQLite SELECT + LLM API Key | `backend/app/main.py: /health` |

---

## 二、待实现的工程化能力 ❌

### P0 — 生产环境必须立即补齐

#### P0-1: 结构化日志（Structured Logging）
- **现状**：全部使用 `logging.getLogger(__name__)` 纯文本日志
- **问题**：无法按 `request_id`/`user_id` 过滤；无法接入 ELK/Loki/CLS
- **方案**：引入 `structlog`，JSON 输出 + 自动注入 request_id
- **文件**：`backend/app/logging_config.py` (新建) + `backend/app/main.py` (修改)

#### P0-2: 全局异常处理中间件（Global Exception Handler）
- **现状**：无集中异常处理，未捕获异常直接 500 + 可能泄露堆栈
- **方案**：`@app.exception_handler(Exception)` 统一返回 JSON 错误 + 隐藏堆栈
- **文件**：`backend/app/middleware/error_handler.py` (新建) + `backend/app/main.py` (修改)

#### P0-3: LLM 调用重试与熔断（Retry + Circuit Breaker）
- **现状**：LLM API 调用失败直接抛异常，无重试/降级/熔断
- **方案**：tenacity 指数退避重试 + pybreaker 熔断器 + fallback 模型
- **文件**：`backend/app/llm/retry.py` (新建) + `backend/app/llm/client.py` (修改)

#### P0-4: 数据库迁移（Database Migration）
- **现状**：`CREATE TABLE IF NOT EXISTS` 原生 SQL，无版本管理
- **方案**：引入 Alembic，版本化 schema 变更
- **文件**：`backend/alembic/` (新建) + `backend/app/multitenant/db.py` (修改)

### P1 — 应尽快补齐

#### P1-1: 容器化（Docker + Docker Compose）
- **现状**：无 Dockerfile，无 docker-compose.yml
- **方案**：后端 Dockerfile + 前端 Dockerfile + docker-compose.yml
- **文件**：`Dockerfile` + `frontend/Dockerfile` + `docker-compose.yml` (新建)

#### P1-2: CI/CD Pipeline
- **现状**：无 CI 配置
- **方案**：GitHub Actions `.github/workflows/ci.yml` — push 自动跑测试 + lint
- **文件**：`.github/workflows/ci.yml` (新建)

#### P1-3: 环境配置验证（Config Validation on Startup）
- **现状**：缺失 API Key 时静默降级；SECRET_KEY 缺失时自动生成随机值
- **方案**：启动时 pydantic-settings 声明式校验，缺失则拒绝启动
- **文件**：`backend/app/config.py` (修改)

### P2 — 进一步提升质量

#### P2-1: API 版本管理 ✅
- **实现**：全部路由加 `/api/v1/` 前缀；前端 `api.ts` 用 `const V1 = "/api/v1"` 统一管理；健康检查保持 `/health` 不动
- **文件**：`backend/app/api/*.py` (9 个路由) + `backend/test/*.py` (9 个测试) + `frontend/src/lib/api.ts`

#### P2-2: 可观测性三支柱（Metrics + Traces + Logs）✅
- **实现**：`backend/app/monitoring/` 模块，含 Prometheus `/metrics` 端点（启用开关 `ENABLE_PROMETHEUS=1`）、Sentry 错误追踪（`SENTRY_DSN` 环境变量）、自定义 LLM/RAG 指标（懒加载，缺依赖不阻塞启动）
- **文件**：`backend/app/monitoring/__init__.py` + `backend/app/main.py`

#### P2-3: Token 成本追踪面板 ✅
- **实现**：后端 `GET /api/v1/knowledge/usage` 端点（返回当日 token 消耗、按模型拆分、费用估算、预算告警）+ 前端 `TokenUsagePanel` 组件（进度条、模型表格、费用展示）
- **文件**：`backend/app/api/usage.py` + `frontend/src/components/settings/token-usage-panel.tsx` + `frontend/src/lib/api.ts`

#### P2-4: 依赖安全扫描 ✅
- **实现**：CI 中集成 pip-audit，自动检测已知 CVE
- **文件**：`.github/workflows/ci.yml`

#### P2-5: 前端测试补齐 ✅
- **实现**：Vitest + jsdom 测试框架；`test/lib/api.test.ts` 覆盖 API 版本前缀验证、请求成功/失败处理、认证头注入等 12 个用例
- **文件**：`frontend/vitest.config.ts` + `frontend/test/setup.ts` + `frontend/test/lib/api.test.ts` + `frontend/package.json`

---

## 三、实施进度

| 编号 | 项目 | 优先级 | 状态 | 完成日期 |
|------|------|--------|------|----------|
| P0-1 | 结构化日志 | P0 | ✅ 已完成 | 2026-08-11 |
| P0-2 | 全局异常处理 | P0 | ✅ 已完成 | 2026-08-11 |
| P0-3 | LLM 重试+熔断 | P0 | ✅ 已完成 | 2026-08-11 |
| P0-4 | 数据库迁移 | P0 | ✅ 已完成 | 2026-08-11 |
| P1-1 | 容器化 | P1 | ✅ 已完成 | 2026-08-11 |
| P1-2 | CI/CD Pipeline | P1 | ✅ 已完成 | 2026-08-11 |
| P1-3 | 环境配置验证 | P1 | ✅ 已完成 | 2026-08-11 |
| P2-1 | API 版本管理 | P2 | ✅ 已完成 | 2026-08-11 |
| P2-2 | 可观测性三支柱 | P2 | ✅ 已完成 | 2026-08-11 |
| P2-3 | Token 成本面板 | P2 | ✅ 已完成 | 2026-08-11 |
| P2-4 | 依赖安全扫描 | P2 | ✅ 已完成 | 2026-08-11 |
| P2-5 | 前端测试补齐 | P2 | ✅ 已完成 | 2026-08-11 |

---

## 四、参考资料

- [FastAPI Production Best Practices (2026)](https://github.com/freddy-c/fastapi-production-template) — 98% test coverage, Auth0, PostgreSQL, CI/CD
- [structlog 官方文档](https://www.structlog.org/) — Python 结构化日志标准库
- [Alembic 官方文档](https://alembic.sqlalchemy.org/) — SQLAlchemy 数据库迁移工具
- [tenacity 官方文档](https://tenacity.readthedocs.io/) — Python 重试库
- [pybreaker](https://github.com/danielfm/pybreaker) — Python 熔断器
- [OWASP LLM Security](https://owasp.org/www-project-top-10-for-large-language-model-applications/) — LLM 应用安全 Top 10
