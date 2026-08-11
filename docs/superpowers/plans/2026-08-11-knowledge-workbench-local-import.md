# Knowledge Workbench 3.4.2 本地文件夹安全导入实施计划

**目标：** 把浏览器选择的本地多格式文件夹导入为租户隔离、不可变的服务器批次，再复用 3.4.1 的完整 RAG 工作台。

**架构：** 后端按领域模型、SQLite 仓储、文件系统服务和 FastAPI 路由四层拆分。上传先流式写入租户 staging，完成时验证清单并原子冻结到 `knowledge/imports/ready` 。前端只传规范化相对路径，冻结后使用服务端返回的 `relative_path` 调用既有 `planFolder()`。

**技术栈：** FastAPI、Pydantic、SQLite、Python 流式 IO、Next.js 16、React 19、TypeScript、Vitest、Testing Library。

## Task 1：导入领域模型与持久化

**Files:**

- Create: `backend/app/knowledge_agent/import_models.py`
- Create: `backend/app/knowledge_agent/import_repository.py`
- Create: `backend/test/test_knowledge_import_repository.py`

- [ ] 先写租户隔离、状态持久化、文件路径唯一性和冻结后禁止写入的失败测试。
- [ ] 定义 `ImportBatch`、`ImportFileRecord`、`ImportStatus` 与稳定错误类别。
- [ ] 实现 SQLite schema、批次创建/读取、文件记录、状态转换与租户条件查询。
- [ ] 运行 `pytest test/test_knowledge_import_repository.py -q` 并提交。

## Task 2：安全流式上传与原子冻结

**Files:**

- Create: `backend/app/knowledge_agent/imports.py`
- Create: `backend/test/test_knowledge_imports.py`

- [ ] 先写路径穿越、绝对路径、不支持扩展名、重复路径、单文件/批次超限、空批次和冻结后写入的失败测试。
- [ ] 实现 POSIX 相对路径规范化，仅允许 `.md/.docx/.xlsx/.pdf`。
- [ ] 以 1 MiB 分块流式写入临时文件并同时计算 SHA-256；失败时删除当前临时文件。
- [ ] 完成时校验非空清单、文件数和总大小，使用同文件系统 `replace()` 冻结目录并返回受控相对路径。
- [ ] 运行服务层测试并提交。

## Task 3：受认证的导入 API

**Files:**

- Create: `backend/app/api/knowledge_imports.py`
- Modify: `backend/app/main.py`
- Create: `backend/test/test_knowledge_import_api.py`

- [ ] 先写未登录 401、跨租户 404、创建、上传、查询、冻结与删除的 API 失败测试。
- [ ] 实现 `POST /imports`、`POST /imports/{id}/files`、`POST /imports/{id}/complete`、`GET/DELETE /imports/{id}`。
- [ ] 路由层只映射稳定错误到 400/404/409/413/422，不返回服务器绝对路径。
- [ ] 验证冻结后的 `relative_path` 可直接进入现有 `plan-folder` 端点。
- [ ] 运行 API 与 Knowledge 回归并提交。

## Task 4：前端导入契约与文件夹界面

**Files:**

- Modify: `frontend/src/components/knowledge-workbench/workbench-types.ts`
- Modify: `frontend/src/lib/knowledge-api.ts`
- Modify: `frontend/src/lib/knowledge-api.test.ts`
- Create: `frontend/src/components/knowledge-workbench/steps/import-step.tsx`
- Modify: `frontend/src/components/knowledge-workbench/steps/source-step.tsx`
- Modify: `frontend/src/components/knowledge-workbench/knowledge-workbench.tsx`
- Modify: `frontend/src/components/knowledge-workbench/knowledge-workbench.test.tsx`

- [ ] 先写 API 路径、目录文件列表、不支持类型预检、逐文件进度、失败停留和冻结后自动进入规划步骤的失败测试。
- [ ] 使用 `<input type="file" webkitdirectory multiple>` 选择文件夹，以 `webkitRelativePath` 作为相对路径；不读取客户端绝对路径。
- [ ] 逐文件调用上传 API，全部成功后 complete，将 `relative_path` 写入现有规划表单。
- [ ] 单文件失败时保留成功记录和稳定错误，不自动规划。
- [ ] 运行组件测试、typecheck 和定向 lint 并提交。

## Task 5：验收、文档与发布检查

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-11-knowledge-workbench-design.md` only if implementation decisions differ

- [ ] 运行全部前端测试、typecheck、生产构建和定向 lint。
- [ ] 运行全部 `test_knowledge_*.py` 回归，并检查 `git diff --check`。
- [ ] 在 README 增加本地文件夹导入限制、七步流程和开发运行方式。
- [ ] 核对不相关未暂存变更仍未被纳入任何提交。
- [ ] 推送 `dev/knowledge` 并更新现有 Draft PR 的验证结果。
