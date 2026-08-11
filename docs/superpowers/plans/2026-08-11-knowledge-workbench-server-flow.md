# Knowledge Workbench 3.4.1 服务器目录流程实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有服务器 `knowledge/` 目录的 KnowledgeRun 后端闭环接入一个可恢复、可审阅、可发布和可回滚的七步前端工作台。

**Architecture:** 前端使用强类型 API 客户端、纯函数状态归约器和按步骤拆分的 React 组件；页面只根据服务端 Run、评测报告和活动版本推导动作。后端只补充租户隔离的最近运行列表，不改变 3.3 状态机和发布事务。

**Tech Stack:** Next.js 16、React 19、TypeScript、Tailwind CSS 4、Vitest、Testing Library、jsdom、FastAPI、SQLite、pytest

---

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `frontend/vitest.config.ts` | Vitest、jsdom 与路径别名配置 |
| `frontend/src/test/setup.ts` | Testing Library DOM matcher 和测试清理 |
| `frontend/src/components/knowledge-workbench/workbench-types.ts` | 与后端契约一致的领域类型 |
| `frontend/src/components/knowledge-workbench/workbench-state.ts` | 纯状态推导、步骤和动作白名单 |
| `frontend/src/lib/knowledge-api.ts` | KnowledgeRun 强类型 HTTP 客户端 |
| `frontend/src/components/knowledge-workbench/knowledge-workbench.tsx` | 数据装配、恢复与向导布局 |
| `frontend/src/components/knowledge-workbench/workbench-summary.tsx` | 当前 Run 与下一动作摘要 |
| `frontend/src/components/knowledge-workbench/steps/*.tsx` | 七个独立步骤视图 |
| `backend/app/knowledge_agent/repository.py` | 最近运行游标查询 |
| `backend/app/api/knowledge_plan.py` | `GET /api/knowledge/runs` 认证端点 |

## Task 1：前端测试基础设施

**Files:**

- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/smoke.test.ts`

- [ ] **Step 1：安装测试依赖并增加脚本**

```powershell
npm install --save-dev vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

在 `package.json` 增加：

```json
"test": "vitest run",
"test:watch": "vitest",
"typecheck": "tsc --noEmit"
```

- [ ] **Step 2：写最小测试配置和 smoke test**

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
});
```

```ts
// src/test/setup.ts
import "@testing-library/jest-dom/vitest";
```

```ts
// src/test/smoke.test.ts
import { expect, test } from "vitest";
test("vitest is configured", () => expect(true).toBe(true));
```

- [ ] **Step 3：运行测试并确认基础设施可用**

Run: `npm test -- src/test/smoke.test.ts`

Expected: `1 passed`。

- [ ] **Step 4：提交**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts frontend/src/test/smoke.test.ts
git commit -m "test: configure frontend component testing"
```

## Task 2：领域类型与状态推导

**Files:**

- Create: `frontend/src/components/knowledge-workbench/workbench-types.ts`
- Create: `frontend/src/components/knowledge-workbench/workbench-state.ts`
- Create: `frontend/src/components/knowledge-workbench/workbench-state.test.ts`

- [ ] **Step 1：先写状态推导失败测试**

```ts
import { describe, expect, it } from "vitest";
import { deriveWorkbenchState } from "./workbench-state";

describe("deriveWorkbenchState", () => {
  it.each([
    ["review_required", "review", ["approve"]],
    ["approved", "execution", ["execute"]],
    ["evaluating", "evaluation", ["evaluate"]],
    ["promoted", "release", ["rollback"]],
    ["failed", "execution", ["restart"]],
  ])("maps %s to %s", (status, step, actions) => {
    const result = deriveWorkbenchState({ run: { ...RUN, status }, evaluation: null, activeVersion: null });
    expect(result.step).toBe(step);
    expect(result.actions).toEqual(actions);
  });

  it("never enables promote for a rejected report", () => {
    const result = deriveWorkbenchState({
      run: { ...RUN, status: "rejected" },
      evaluation: { ...REPORT, status: "rejected" },
      activeVersion: null,
    });
    expect(result.actions).not.toContain("promote");
  });
});
```

- [ ] **Step 2：运行 RED**

Run: `npm test -- src/components/knowledge-workbench/workbench-state.test.ts`

Expected: FAIL，模块尚不存在。

- [ ] **Step 3：实现后端契约类型和纯函数**

定义 `RunStatus`、`CorpusProfile`、`StrategyDecision`、`AgentAttempt`、`FolderPlan`、`KnowledgeRun`、`EvaluationReport`、`ActiveIndexVersion`、`WorkbenchStep` 和 `WorkbenchAction`。实现：

```ts
export function deriveWorkbenchState(input: WorkbenchInput): DerivedWorkbenchState {
  const { run, evaluation, activeVersion } = input;
  if (!run) return { step: "source", actions: ["plan"], readOnly: false };
  if (run.status === "planned" || run.status === "review_required") {
    return { step: "review", actions: ["approve"], readOnly: false };
  }
  if (run.status === "approved") {
    return { step: "execution", actions: ["execute"], readOnly: false };
  }
  if (run.status === "indexing") {
    return { step: "execution", actions: ["refresh"], readOnly: true };
  }
  if (run.status === "evaluating" && evaluation?.status === "passed") {
    return { step: "release", actions: ["promote"], readOnly: false };
  }
  if (run.status === "evaluating") {
    return { step: "evaluation", actions: ["evaluate"], readOnly: false };
  }
  if (run.status === "promoted") {
    const isActive = activeVersion?.run_id === run.run_id;
    return { step: "release", actions: isActive ? ["rollback"] : ["refresh"], readOnly: !isActive };
  }
  if (["failed", "rejected", "invalidated"].includes(run.status)) {
    return { step: run.status === "rejected" ? "evaluation" : "execution", actions: ["restart"], readOnly: true };
  }
  return { step: "release", actions: ["refresh"], readOnly: true };
}
```

- [ ] **Step 4：运行 GREEN**

Run: `npm test -- src/components/knowledge-workbench/workbench-state.test.ts`

Expected: PASS。

- [ ] **Step 5：提交**

```powershell
git add frontend/src/components/knowledge-workbench/workbench-types.ts frontend/src/components/knowledge-workbench/workbench-state.ts frontend/src/components/knowledge-workbench/workbench-state.test.ts
git commit -m "feat: model the Knowledge Workbench state"
```

## Task 3：强类型 Knowledge API 客户端

**Files:**

- Create: `frontend/src/lib/knowledge-api.ts`
- Create: `frontend/src/lib/knowledge-api.test.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1：先写请求契约失败测试**

```ts
it("calls the authenticated run lifecycle endpoints", async () => {
  const fetcher = vi.fn().mockResolvedValue(response({ run_id: "r1" }));
  const api = createKnowledgeApi(fetcher);
  await api.planFolder({ path: "fixtures", use_agent: false });
  await api.approve("r1");
  await api.execute("r1");
  await api.evaluate("r1");
  await api.promote("r1");
  await api.rollback("r1");
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    expect.stringEndingWith("/api/knowledge/plan-folder"),
    expect.stringEndingWith("/api/knowledge/runs/r1/approve"),
    expect.stringEndingWith("/api/knowledge/runs/r1/execute"),
    expect.stringEndingWith("/api/knowledge/runs/r1/evaluate"),
    expect.stringEndingWith("/api/knowledge/runs/r1/promote"),
    expect.stringEndingWith("/api/knowledge/runs/r1/rollback"),
  ]);
});

it("preserves stable backend error details", async () => {
  const api = createKnowledgeApi(vi.fn().mockResolvedValue(response({ detail: "run_not_active" }, 409)));
  await expect(api.rollback("r1")).rejects.toMatchObject({ status: 409, detail: "run_not_active" });
});
```

- [ ] **Step 2：运行 RED**

Run: `npm test -- src/lib/knowledge-api.test.ts`

Expected: FAIL，`createKnowledgeApi` 尚不存在。

- [ ] **Step 3：实现客户端**

客户端复用 token、API Key 和模型读取规则，但只暴露：`listRuns`、`getRun`、`planFolder`、`approve`、`execute`、`evaluate`、`getEvaluation`、`getActiveVersion`、`promote`、`rollback`。所有 path segment 使用 `encodeURIComponent`；错误转换为：

```ts
export class KnowledgeApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}
```

- [ ] **Step 4：运行 GREEN 和类型检查**

Run: `npm test -- src/lib/knowledge-api.test.ts`

Run: `npm run typecheck`

Expected: 全部通过。

- [ ] **Step 5：提交**

```powershell
git add frontend/src/lib/knowledge-api.ts frontend/src/lib/knowledge-api.test.ts frontend/src/lib/api.ts
git commit -m "feat: add the typed Knowledge Run client"
```

## Task 4：最近运行列表后端

**Files:**

- Modify: `backend/app/knowledge_agent/repository.py`
- Modify: `backend/app/api/knowledge_plan.py`
- Create: `backend/test/test_knowledge_run_list.py`
- Modify: `backend/test/test_knowledge_plan_api.py`

- [ ] **Step 1：先写租户隔离、顺序和游标失败测试**

```python
def test_list_runs_is_tenant_scoped_and_cursor_paginated(tmp_path):
    database = tmp_path / "audit.sqlite3"
    create_runs(database, user_id=7, count=3)
    create_runs(database, user_id=8, count=1)
    first = list_runs(database_path=database, user_id=7, limit=2)
    assert len(first.items) == 2
    assert all(item.user_id == 7 for item in first.items)
    second = list_runs(database_path=database, user_id=7, limit=2, cursor=first.next_cursor)
    assert len(second.items) == 1
    assert {item.run_id for item in first.items}.isdisjoint(item.run_id for item in second.items)
```

API 测试断言未登录为 401、`limit=101` 为 422、其他租户 Run 不出现在响应中。

- [ ] **Step 2：运行 RED**

Run: `python -m pytest test/test_knowledge_run_list.py test/test_knowledge_plan_api.py -q --noconftest`

Expected: FAIL，列表模型和函数尚不存在。

- [ ] **Step 3：实现查询和端点**

增加 `KnowledgeRunPage(items, next_cursor)`，游标编码严格的 `created_at|run_id`，查询条件：

```sql
WHERE user_id IS ?
  AND (? IS NULL OR (created_at, run_id) < (?, ?))
ORDER BY created_at DESC, run_id DESC
LIMIT ?
```

API：

```python
@router.get("/runs")
def api_list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    return list_runs(
        database_path=_database_path(), user_id=current_user["user_id"],
        limit=limit, cursor=cursor,
    )
```

- [ ] **Step 4：运行 GREEN**

Run: `python -m pytest test/test_knowledge_run_list.py test/test_knowledge_plan_api.py -q --noconftest`

Expected: PASS。

- [ ] **Step 5：提交**

```powershell
git add backend/app/knowledge_agent/repository.py backend/app/api/knowledge_plan.py backend/test/test_knowledge_run_list.py backend/test/test_knowledge_plan_api.py
git commit -m "feat: list tenant Knowledge Runs"
```

## Task 5：来源、规划、审阅和摘要 UI

**Files:**

- Create: `frontend/src/components/knowledge-workbench/knowledge-workbench.tsx`
- Create: `frontend/src/components/knowledge-workbench/workbench-summary.tsx`
- Create: `frontend/src/components/knowledge-workbench/workbench-progress.tsx`
- Create: `frontend/src/components/knowledge-workbench/steps/source-step.tsx`
- Create: `frontend/src/components/knowledge-workbench/steps/planning-step.tsx`
- Create: `frontend/src/components/knowledge-workbench/steps/review-step.tsx`
- Create: `frontend/src/components/knowledge-workbench/knowledge-workbench.test.tsx`

- [ ] **Step 1：先写服务器目录成功到审阅的失败测试**

```tsx
it("plans a server folder and opens forced-review documents", async () => {
  const api = fakeApi({ planFolder: vi.fn().mockResolvedValue(REVIEW_PLAN) });
  render(<KnowledgeWorkbench api={api} />);
  await user.click(screen.getByRole("button", { name: "服务器目录" }));
  await user.type(screen.getByLabelText("知识目录相对路径"), "fixtures");
  await user.click(screen.getByRole("button", { name: "生成策略计划" }));
  expect(api.planFolder).toHaveBeenCalledWith({ path: "fixtures", use_agent: true });
  expect(await screen.findByText("需要人工复核")).toBeVisible();
  expect(screen.getByText("pdf_ocr_review_v1")).toBeVisible();
});
```

另测：路径为空不能提交、关闭 Agent 后请求 `use_agent=false`、摘要展示 Run ID 和复核数。

- [ ] **Step 2：运行 RED**

Run: `npm test -- src/components/knowledge-workbench/knowledge-workbench.test.tsx`

Expected: FAIL，组件尚不存在。

- [ ] **Step 3：实现最小组件树**

`KnowledgeWorkbench` 接受可注入的 `api: KnowledgeApi`；生产默认使用 `knowledgeApi`。来源步骤只启用服务器目录，本地目录卡显示“下一阶段接入”但保持相同布局槽位。审阅按 `requires_review`、文件类型和路径稳定排序，强制复核项使用原生 `<details open>`。

- [ ] **Step 4：运行 GREEN、无障碍查询和 lint**

Run: `npm test -- src/components/knowledge-workbench/knowledge-workbench.test.tsx`

Run: `npm run lint`

Expected: PASS，无 `button-name`、label 或 hook lint 错误。

- [ ] **Step 5：提交**

```powershell
git add frontend/src/components/knowledge-workbench
git commit -m "feat: add Knowledge Workbench planning review"
```

## Task 6：审批、执行、评测、发布与回滚 UI

**Files:**

- Create: `frontend/src/components/knowledge-workbench/steps/execution-step.tsx`
- Create: `frontend/src/components/knowledge-workbench/steps/evaluation-step.tsx`
- Create: `frontend/src/components/knowledge-workbench/steps/release-step.tsx`
- Modify: `frontend/src/components/knowledge-workbench/knowledge-workbench.tsx`
- Modify: `frontend/src/components/knowledge-workbench/knowledge-workbench.test.tsx`

- [ ] **Step 1：先写完整生命周期失败测试**

```tsx
it("requires confirmation and completes evaluate promote rollback", async () => {
  const api = lifecycleApi();
  render(<KnowledgeWorkbench api={api} initialPlan={REVIEW_PLAN} />);
  await user.click(screen.getByRole("button", { name: "批准计划" }));
  await user.click(screen.getByRole("button", { name: "确认批准" }));
  await user.click(screen.getByRole("button", { name: "执行隔离索引" }));
  expect(await screen.findByText("等待离线评测")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "运行离线评测" }));
  expect(await screen.findByText("MRR")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "发布活动版本" }));
  await user.click(screen.getByRole("button", { name: "确认发布" }));
  expect(await screen.findByText("当前活动版本")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "回滚上一版本" }));
  await user.click(screen.getByRole("button", { name: "确认回滚" }));
  expect(api.rollback).toHaveBeenCalled();
});
```

另测：评测 `rejected` 不渲染发布按钮、409 后调用 `getRun` 和 `getActiveVersion`、请求期间按钮禁用、422 显示稳定错误分类。

- [ ] **Step 2：运行 RED**

Run: `npm test -- src/components/knowledge-workbench/knowledge-workbench.test.tsx`

Expected: FAIL，生命周期按钮和视图尚不存在。

- [ ] **Step 3：实现生命周期步骤**

审批、发布和回滚使用可访问的确认对话框；执行和评测不允许并发重复提交。评测卡以百分比展示 Hit 指标，以两位小数展示 MRR/nDCG；失败原因显示稳定代码和中文解释，不展示底层异常。

- [ ] **Step 4：运行 GREEN**

Run: `npm test -- src/components/knowledge-workbench/knowledge-workbench.test.tsx`

Expected: PASS。

- [ ] **Step 5：提交**

```powershell
git add frontend/src/components/knowledge-workbench
git commit -m "feat: complete the Knowledge Workbench lifecycle"
```

## Task 7：运行恢复、页面接入与验收

**Files:**

- Modify: `frontend/src/components/knowledge-base/kb-panel.tsx`
- Modify: `frontend/src/components/knowledge-workbench/knowledge-workbench.tsx`
- Modify: `frontend/src/components/knowledge-workbench/knowledge-workbench.test.tsx`
- Modify: `README.md`

- [ ] **Step 1：先写刷新恢复失败测试**

```tsx
it("restores the last tenant run and active version", async () => {
  localStorage.setItem("orbit_knowledge_run_id", "r1");
  const api = fakeApi({
    listRuns: vi.fn().mockResolvedValue({ items: [RUN], next_cursor: null }),
    getRun: vi.fn().mockResolvedValue(RUN),
    getActiveVersion: vi.fn().mockResolvedValue(ACTIVE),
    getEvaluation: vi.fn().mockResolvedValue(PASSED_REPORT),
  });
  render(<KnowledgeWorkbench api={api} />);
  expect(await screen.findByText("当前活动版本")).toBeVisible();
  expect(api.getRun).toHaveBeenCalledWith("r1");
});
```

另测：本地 Run 不存在时回退最近一条、无 Run 时显示来源选择、网络失败保留重试按钮。

- [ ] **Step 2：运行 RED**

Run: `npm test -- src/components/knowledge-workbench/knowledge-workbench.test.tsx`

Expected: FAIL，恢复逻辑尚不存在。

- [ ] **Step 3：实现恢复和接入**

`KnowledgeBasePanel` 以 `KnowledgeWorkbench` 为主内容；旧上传 UI 移入默认关闭的“兼容单文件上传”区域。恢复只保存 Run ID，不把报告、token 或文件内容写入 localStorage。

- [ ] **Step 4：完整前端验证**

Run: `npm test`

Run: `npm run lint`

Run: `npm run typecheck`

Run: `npm run build`

Expected: 全部退出码 0。

- [ ] **Step 5：后端与范围验证**

Run: `$env:PYTHONPATH=(Resolve-Path '.\.pydeps').Path; $ragTests=(Get-ChildItem -LiteralPath '.\test' -Filter 'test_knowledge_*.py').FullName; python -m pytest $ragTests -q --noconftest`

Run: `git diff --check`

Expected: Knowledge 回归无失败；三项既有无关工作区变更未暂存。

- [ ] **Step 6：更新文档并提交**

README 增加 3.4.1 工作台入口、运行恢复、服务器目录使用说明，并明确本地文件夹在 3.4.2 接入。

```powershell
git add frontend/src/components/knowledge-base/kb-panel.tsx frontend/src/components/knowledge-workbench README.md
git commit -m "docs: document the Knowledge Workbench server flow"
```

## 3.4.1 验收清单

- [ ] 登录用户能从 `fixtures` 创建策略计划并看到七份文件。
- [ ] 强制复核文件默认展开，Agent、规则和最终策略来源清楚。
- [ ] 审批、执行、评测、发布和回滚严格跟随后端状态。
- [ ] 评测拒绝不能发布，409 会刷新状态。
- [ ] 页面刷新能恢复当前用户最近 Run 和活动版本。
- [ ] 旧上传保留为兼容入口，不进入正式向导。
- [ ] 前端测试、lint、类型检查、生产构建和后端 Knowledge 回归通过。
