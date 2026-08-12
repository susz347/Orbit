# Orbit 工程化体系

> 12 篇文档，覆盖从测试到可观测性的完整工程化体系。

## 文档目录

| 序号 | 文档 | 对应模块 |
|------|------|----------|
| 1 | [测试体系](./01-测试体系.md) | 隔离层 · 辅助层 · 测试层 · CI 触发层 |
| 2 | [认证与授权](./02-认证与授权.md) | 渐进式认证 · bcrypt · JWT · 租户隔离 |
| 3 | [结构化日志](./03-结构化日志.md) | structlog · JSON 输出 · request_id 注入 |
| 4 | [全局异常处理](./04-全局异常处理.md) | 统一 JSON 错误 · 堆栈隐藏 · 生产/开发区分 |
| 5 | [LLM 调用可靠性](./05-LLM调用可靠性.md) | 指数退避重试 · 熔断器 · Fallback 模型 |
| 6 | [数据库迁移](./06-数据库迁移.md) | Alembic · 版本化 schema · 升级/回滚 |
| 7 | [Docker 容器化](./07-Docker容器化.md) | 多阶段构建 · 非 root 用户 · docker-compose |
| 8 | [CI/CD](./08-CICD.md) | GitHub Actions · 矩阵测试 · 依赖安全扫描 |
| 9 | [环境配置验证](./09-环境配置验证.md) | 启动时强制校验 · 拒绝不安全的部署 |
| 10 | [API 版本管理](./10-API版本管理.md) | /api/v1 前缀 · 前后端同步 · 向后兼容 |
| 11 | [可观测性三支柱](./11-可观测性三支柱.md) | Metrics · Traces · Error Tracking |
| 12 | [Agent Loop 行为约束](./12-AgentLoop行为约束.md) | gate.yaml · loop-constraints.md · 安全门控 |

## 完整清单

参见 [ENGINEERING-CHECKLIST.md](../ENGINEERING-CHECKLIST.md)。
