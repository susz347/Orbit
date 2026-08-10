# Knowledge Agent 3.3 RAG 评测、发布与回滚实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 3.2 staging collection 运行确定性检索评测，通过门禁后按租户原子发布，并让现有搜索/问答使用可回滚的活动索引版本。

**Architecture:** `EvaluationEngine` 只读取版本化 JSONL 和 `StagingStore.query()`，把逐题及汇总指标写入 SQLite。`ReleaseRepository` 在单个 SQLite 事务内校验评测、切换活动 collection 指针和转换 Run 状态；现有 `search()` 通过 `ActiveIndexResolver` 获取命名 collection，无活动指针时回退 legacy `user_<id>`。

**Tech Stack:** Python 3.12、Pydantic 2、FastAPI、SQLite、ChromaDB 0.5、pytest

---

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `knowledge/evals/questions.jsonl` | 版本化检索 ground truth |
| `backend/app/knowledge_agent/evaluation_models.py` | 用例、检索结果、逐题与汇总报告模型 |
| `backend/app/knowledge_agent/evaluation_dataset.py` | 加载与校验 JSONL |
| `backend/app/knowledge_agent/retrieval_metrics.py` | Hit@K、MRR、nDCG 纯函数 |
| `backend/app/knowledge_agent/staging_store.py` | staging 查询和 collection 存在性检查 |
| `backend/app/knowledge_agent/evaluation_repository.py` | 评测 attempt、case 与报告审计 |
| `backend/app/knowledge_agent/evaluation.py` | 评测编排和质量门禁 |
| `backend/app/knowledge_agent/releases.py` | 活动指针、原子发布与回滚 |
| `backend/app/store/__init__.py` | 按名称安全取得 collection |
| `backend/app/search/__init__.py` | 使用活动版本解析器检索 |
| `backend/app/api/knowledge_plan.py` | evaluate/report/promote/rollback/active-version API |

## Task 1：版本化评测数据契约

**Files:**

- Modify: `knowledge/evals/questions.jsonl`
- Create: `backend/app/knowledge_agent/evaluation_models.py`
- Create: `backend/app/knowledge_agent/evaluation_dataset.py`
- Create: `backend/test/test_knowledge_evaluation_dataset.py`

- [ ] **Step 1：先写失败测试**

```python
def test_loads_versioned_unique_retrieval_cases():
    cases = load_evaluation_cases(QUESTIONS)
    assert len(cases) >= 5
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.schema_version == "rag-retrieval.v1" for case in cases)
    assert all(case.relevant_sources for case in cases)


def test_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(VALID_LINE + "\n" + VALID_LINE, encoding="utf-8")
    with pytest.raises(EvaluationDatasetError, match="duplicate_case_id"):
        load_evaluation_cases(path)
```

- [ ] **Step 2：运行并确认 RED**

```powershell
python -m pytest test/test_knowledge_evaluation_dataset.py -q --noconftest
```

Expected: FAIL，评测模型与 loader 尚不存在。

- [ ] **Step 3：实现模型和 loader**

```python
class RelevantLocator(BaseModel):
    model_config = ConfigDict(frozen=True)
    heading: str | None = None
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    row_number: int | None = Field(default=None, ge=1)


class RetrievalEvaluationCase(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: Literal["rag-retrieval.v1"]
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    relevant_sources: tuple[str, ...] = Field(min_length=1)
    relevant_locators: tuple[RelevantLocator, ...] = Field(min_length=1)
    critical: bool = True
    tags: tuple[str, ...] = ()
```

loader 逐行 `json.loads()`、Pydantic 校验、拒绝空行以外的非法 JSON 和重复 ID，异常只暴露 `invalid_jsonl`、`invalid_case`、`duplicate_case_id`。

- [ ] **Step 4：迁移现有五条问题并运行 GREEN**

将自由文本 `source/locator` 迁移为设计规范的结构字段，保留原问题和答案。

- [ ] **Step 5：提交**

```powershell
git add knowledge/evals/questions.jsonl backend/app/knowledge_agent/evaluation_models.py backend/app/knowledge_agent/evaluation_dataset.py backend/test/test_knowledge_evaluation_dataset.py
git commit -m "feat: version knowledge retrieval evaluation cases"
```

## Task 2：确定性检索指标与门禁策略

**Files:**

- Create: `backend/app/knowledge_agent/retrieval_metrics.py`
- Create: `backend/test/test_knowledge_retrieval_metrics.py`

- [ ] **Step 1：先写指标失败测试**

```python
def test_ranked_metrics_reward_early_relevant_result():
    relevance = [False, True, False, False, False]
    assert hit_at_k(relevance, 5) is True
    assert reciprocal_rank(relevance) == 0.5
    assert ndcg_at_k(relevance, 5) == pytest.approx(1 / math.log2(3))


def test_gate_requires_every_critical_case():
    reports = (case_report("critical", source_hit=False, critical=True),)
    decision = evaluate_gate(reports, empty_chunks=0, duplicates=0, counts_match=True)
    assert decision.passed is False
    assert "critical_source_miss" in decision.failures
```

- [ ] **Step 2：运行 RED**

- [ ] **Step 3：实现纯函数和不可由 API 覆盖的 `EvaluationPolicy`**

`EvaluationPolicy` 固定 `top_k=5`、source hit 1.0、locator hit 0.90、MRR 0.80、nDCG 0.90，并检查空/重复 Chunk 和数量一致性。nDCG 无相关结果时为 0。

- [ ] **Step 4：运行 GREEN 并提交**

```powershell
git add backend/app/knowledge_agent/retrieval_metrics.py backend/test/test_knowledge_retrieval_metrics.py
git commit -m "feat: score deterministic RAG retrieval quality"
```

## Task 3：StagingStore 只读检索

**Files:**

- Modify: `backend/app/knowledge_agent/staging_store.py`
- Create: `backend/test/test_knowledge_staging_query.py`

- [ ] **Step 1：先写查询失败测试**

Fake collection 返回 Chroma 形状的 `ids/documents/metadatas/distances`，断言 rank、distance、来源、heading JSON、page/sheet/row 被恢复，且 query 只访问 `staging_collection_name(run_id, user_id)`。

- [ ] **Step 2：运行 RED**

- [ ] **Step 3：实现 `RetrievedChunk` 与 `StagingStore.query()`**

问题只编码一次；collection count 为零返回空 tuple；`n_results=min(top_k,count)`；Embedding/Storage 异常继续转换为已有脱敏异常。增加 `exists()`，通过 `list_collections()` 名称检查，不因检查而创建缺失 collection。

- [ ] **Step 4：运行 GREEN 并提交**

```powershell
git add backend/app/knowledge_agent/staging_store.py backend/test/test_knowledge_staging_query.py
git commit -m "feat: query isolated knowledge staging indexes"
```

## Task 4：评测审计与 EvaluationEngine

**Files:**

- Modify: `backend/app/knowledge_agent/models.py`
- Modify: `backend/app/knowledge_agent/run_state.py`
- Create: `backend/app/knowledge_agent/evaluation_repository.py`
- Create: `backend/app/knowledge_agent/evaluation.py`
- Create: `backend/test/test_knowledge_evaluation_repository.py`
- Create: `backend/test/test_knowledge_evaluation_engine.py`

- [ ] **Step 1：先写通过、拒绝和异常失败测试**

```python
def test_all_critical_hits_produce_passed_report(context):
    report = evaluate_run(context.run_id, ..., store=context.store)
    assert report.status == "passed"
    assert report.source_hit_rate_at_5 == 1.0
    assert get_run(...).status == "evaluating"


def test_quality_miss_rejects_run_without_deleting_staging(context):
    context.store.results["critical-id"] = ()
    report = evaluate_run(...)
    assert report.status == "rejected"
    assert get_run(...).status == "rejected"
    assert context.store.deleted == []
```

另覆盖 count 不一致 `evaluation_input_error`、Embedding/Storage 分类、重复请求返回同一 report、跨租户不存在。

- [ ] **Step 2：运行 RED**

- [ ] **Step 3：实现增量 schema 和报告持久化**

两表只保存 case ID、指标、命中 chunk ID、来源定位和耗时；不保存 text/embedding。attempt 状态为 `running|passed|rejected|failed`，`run_id + attempt_number` 唯一。

- [ ] **Step 4：实现引擎**

要求 Run 为 `evaluating`；确认 collection 存在及 count 相符；逐题调用 store.query；保存 case；应用固定 policy；passed 保持 evaluating，未达标原子转 rejected，基础设施错误转 failed。

- [ ] **Step 5：运行 GREEN 并提交**

```powershell
git add backend/app/knowledge_agent/models.py backend/app/knowledge_agent/run_state.py backend/app/knowledge_agent/evaluation_repository.py backend/app/knowledge_agent/evaluation.py backend/test/test_knowledge_evaluation_repository.py backend/test/test_knowledge_evaluation_engine.py
git commit -m "feat: evaluate staged knowledge retrieval"
```

## Task 5：活动版本、发布与回滚事务

**Files:**

- Create: `backend/app/knowledge_agent/releases.py`
- Create: `backend/test/test_knowledge_releases.py`

- [ ] **Step 1：先写发布门禁和回滚失败测试**

覆盖：无 passed report 不能发布；首次发布 previous 为 `user_7`；第二次发布 generation+1；回滚当前版本恢复上一 collection；跨租户、非当前版本和目标 collection 缺失均拒绝且不改指针。

- [ ] **Step 2：运行 RED**

- [ ] **Step 3：实现 schema 与只读 resolver**

`get_active_index()` 返回 `ActiveIndexVersion(collection_name, run_id, generation, legacy)`；无记录回退 `user_<id>`，全局用户回退配置默认 collection。

- [ ] **Step 4：实现 `promote_run()` 单事务**

使用 `BEGIN IMMEDIATE`：校验租户 Run=evaluating、当前评测=passed、staging 存在；写 release；upsert active pointer；条件更新 Run=promoted；任一步失败 rollback。

- [ ] **Step 5：实现 `rollback_run()` 单事务**

只允许当前 active run；先确认 previous collection 存在；恢复 pointer；标记 release rolled_back；条件更新 Run=rolled_back。

- [ ] **Step 6：运行 GREEN 并提交**

```powershell
git add backend/app/knowledge_agent/releases.py backend/test/test_knowledge_releases.py
git commit -m "feat: promote and roll back knowledge index versions"
```

## Task 6：现有 Search/Ask 使用活动索引

**Files:**

- Modify: `backend/app/store/__init__.py`
- Modify: `backend/app/search/__init__.py`
- Modify: `backend/app/api/knowledge.py`
- Create: `backend/test/test_knowledge_active_search.py`

- [ ] **Step 1：先写活动与 legacy 回退测试**

注入 resolver/client，断言有活动版本时搜索命名 `kr_` collection，无指针时仍读 `user_7`；格式化来源优先 `source_path`，兼容 legacy `source`。

- [ ] **Step 2：运行 RED**

- [ ] **Step 3：实现 `get_collection_by_name()`**

只供服务端已解析名称使用；搜索不得接受 HTTP collection 参数。保留现有 `get_collection()` 给旧上传/删除接口。

- [ ] **Step 4：修改 search**

增加可测试的 `resolve_collection(user_id)`，默认调用 releases resolver 和 Knowledge Agent SQLite 路径；count cache key 使用真实活动 collection 名。Ask/stream 已复用 search，无需复制版本逻辑。

- [ ] **Step 5：运行现有 RAG 回归并提交**

```powershell
git add backend/app/store/__init__.py backend/app/search/__init__.py backend/app/api/knowledge.py backend/test/test_knowledge_active_search.py
git commit -m "feat: search the active knowledge index version"
```

## Task 7：评测、发布、回滚与版本 API

**Files:**

- Modify: `backend/app/api/knowledge_plan.py`
- Modify: `backend/test/test_knowledge_plan_api.py`

- [ ] **Step 1：先写五个端点的失败测试**

使用认证用户、Fake Store 和已执行 Run，覆盖 evaluate 200、report 200、promote 200、active-version 200、rollback 200；未认证 401、跨租户 404、未通过发布 409、基础设施错误 422。

- [ ] **Step 2：运行 RED**

- [ ] **Step 3：实现端点与统一错误映射**

端点不接受阈值或 collection 名。质量 rejected 返回报告；不存在 404；状态/并发 409；脱敏执行错误 422。

- [ ] **Step 4：运行 GREEN 并提交**

```powershell
git add backend/app/api/knowledge_plan.py backend/test/test_knowledge_plan_api.py
git commit -m "feat: expose knowledge evaluation and release APIs"
```

## Task 8：README、完整回归与发布

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-05-knowledge-run-indexing-design.md`

- [ ] **Step 1：更新中文文档**

把边界更新为 3.3 RAG 后端闭环完成；补充 evaluate→promote→active-version→rollback curl；明确 3.4 仅为工作台 UI，旧 upload 为 legacy。

- [ ] **Step 2：运行完整回归**

```powershell
python -m pytest test/test_knowledge_*.py -q --noconftest
```

再运行现有 search/ask 相关测试。Expected: 无失败；真实 Chroma 仅在依赖缺失时 skip。

- [ ] **Step 3：安全与范围检查**

```powershell
git diff --check
git grep -n "collection_name.*Query\|threshold.*Body" -- backend/app/api
git status --short
```

确认 API 不接收 collection/阈值，审计不写原文，既有无关三项脏状态未暂存。

- [ ] **Step 4：代码审查、提交与推送**

```powershell
git add README.md docs/superpowers/specs/2026-08-05-knowledge-run-indexing-design.md
git commit -m "docs: complete the versioned RAG backend workflow"
git push susz347 dev/knowledge
```

更新现有草稿 PR #1 的标题/正文和验证结果，不转 Ready。

## 验收清单

- [ ] 版本化 JSONL 可验证且核心用例来源 Top 5 全命中。
- [ ] 检索门禁不依赖外部 LLM，失败不能发布。
- [ ] 发布原子切换活动指针，不复制向量。
- [ ] Search/Ask 自动使用活动版本，无版本时兼容 legacy。
- [ ] 当前版本可回滚到直接上一完整 collection。
- [ ] 跨租户、并发、缺失 collection 和错误分类有测试。
- [ ] SQLite 不保存 Chunk 全文、Embedding、凭据或底层异常。
- [ ] 3.1/3.2/现有 RAG 回归通过，README 宣告后端 RAG 闭环完成。
