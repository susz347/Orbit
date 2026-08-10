# Agent Loop 约束文件

> 每次 loop 运行前必须读取。如需修改，在下次 loop 开始前生效。
> Agent 违反约束时 loop 自动中止。

## Push & Merge
- 推送前必须告知用户
- 禁止自动合并到 main 分支（需人工确认）
- 合并前必须通过所有测试
- 不推送未经验证的代码

## Paths
- 禁止编辑 `.env`, `.env.*`, `auth/`, `payments/`, `secrets/`
- 禁止编辑基础设施配置（不分环境）
- 禁止编辑 CI/CD 部署配置
- 编辑超过 5 个文件时需要更严格的审查

## Code
- 修改代码后必须运行测试
- 禁止禁用测试来让 CI 变绿
- 禁止删除或注释掉现有测试
- 每个问题最多 3 次修复尝试，超过则升级

## Budget
- Token 消耗达到每日上限 80% 时，切换到仅报告模式（L1）
- 如果 `loop-pause-all` 开关激活，立即退出
- 单次 loop 不超过 10 万 token

## Schedule
- 不要在凌晨 2-6 点自动运行破坏性操作（L2 模式）
- 同一分支每小时最多一次 loop 修改
- triage 模式不占用分支锁（只读）

## Collision
- 同一分支每小时最多一个 action loop 修改
- triage 模式不占用分支锁（只读报告）
- action 模式必须获取分支锁才能落盘

## Escalation
- 同一问题 48h 内升级 2 次以上 → 暂停 auto-fix
- High Priority 问题超过 24h 未处理 → 通知用户
- CRITICAL_FAIL 立即升级，不等待
