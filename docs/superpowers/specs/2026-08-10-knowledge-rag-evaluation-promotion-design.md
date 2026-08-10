# Knowledge Agent 3.3 设计规范：RAG 评测、发布与回滚闭环

_Orbit `dev/knowledge` 连续演进设计，2026-08-10_

---

## 目标

3.3 将 3.2 生成的隔离 staging collection 变成可重复评测、可安全发布、可查询当前版本并可回滚的正式 RAG 索引。完成后，Knowledge Agent 后端形成以下闭环：

```text
文件画像 → 策略规划 → 人工审批 → 多格式执行 → staging
→ 离线检索评测 → 质量门禁 → 原子发布 → 活动索引检索 → 回滚
```

本阶段结束的是 RAG 后端数据闭环，不包含 3.4 Knowledge Workbench 页面。前端现有搜索和问答接口会自动使用活动版本，不要求用户理解 collection 名称。

## 方案选择

### 采用：确定性评测门禁 + SQLite 活动索引指针

第一版硬门禁只依赖版本化 ground truth 和确定性检索指标。LLM Judge 可作为可选建议项，但缺少密钥、网络失败或评分波动不得阻塞本地测试，也不得单独决定发布。

发布不复制向量、不重命名 Chroma collection。系统在 SQLite 事务内切换租户的活动 collection 指针，旧 collection 保留为上一版本，因此发布和回滚都是常量时间操作。

### 不采用：LLM Judge 作为唯一门禁

该方案能衡量回答相关性和忠实度，但存在成本、网络依赖和评分漂移，不适合作为当前小型固定测试集的唯一发布依据。

### 暂不采用：线上双索引 A/B

在线影子流量和用户反馈适合大规模生产系统，但当前只有七份 fixture，实施成本高于能获得的质量信号。3.3 保留版本和审计结构，未来可在其上增加在线评测。

## 研究依据

- AWS 将 RAG 评测拆为 retrieve-only 与 retrieve-and-generate，允许外部 RAG 提交推理结果，说明检索与生成应独立诊断。
- Microsoft 将有 ground truth 的 Document Retrieval 与 Groundedness、Relevance、Completeness 分开，并提供 nDCG 等检索指标。
- Google 建议先区分检索失败和生成失败，再分别衡量 Faithfulness 与 Answer Relevance。
- OpenAI Knowledge Retrieval 样例使用版本化 JSONL、supporting passage、ideal answer，并同时支持本地确定性评分和托管 Evals。

因此 Orbit 3.3 先建立不依赖 LLM 的检索硬门禁，并保留后续回答级评测扩展点。

## 评测数据契约

`knowledge/evals/questions.jsonl` 升级为版本化用例。每行至少包含：

```json
{
  "schema_version": "rag-retrieval.v1",
  "id": "clean-policy-p1-target",
  "question": "What is the P1 first response target?",
  "expected_answer": "four hours",
  "relevant_sources": ["clean-policy.md"],
  "relevant_locators": [{"heading": "Support levels"}],
  "critical": true,
  "tags": ["markdown", "heading"]
}
```

规则：

- `id` 在一个 schema 版本内唯一。
- `relevant_sources` 不能为空；路径使用相对知识文件夹的 POSIX 格式。
- locator 使用结构化字段：`heading`、`page`、`sheet`、`row_number`，不能继续依赖自由文本解析。
- `expected_answer` 为 3.4 回答级评测保留，3.3 检索门禁不调用生成模型。
- 修改问题语义、ground truth 或评分规则时必须升级 schema 或数据集版本。

第一版保留现有五个核心问题，并补充同义问法、混乱文档和跨格式定位用例。核心问题全部标记为 `critical=true`。

## Staging 检索接口

`StagingStore` 增加只读 `query()`：

```text
query(run_id, user_id, question, top_k) -> tuple[RetrievedChunk, ...]
```

查询只允许通过计算出的 `kr_<tenant>_<run>` collection 名执行，不接受客户端传入任意 collection 名。返回值包含 rank、distance、chunk_id、source_path、page、sheet、heading_path、row_number 和 text；评测报告不持久化完整 `text`。

问题向量复用当前 Embedding backend。测试注入固定 encoder 和 Fake Chroma，真实 Chroma 集成测试在依赖可用时执行。

## 确定性指标

逐题计算：

- `source_hit_at_5`：Top 5 是否包含任一期望来源。
- `locator_hit_at_5`：Top 5 是否同时满足来源和至少一个结构化 locator。
- `reciprocal_rank`：首个满足来源与 locator 的结果排名倒数。
- `ndcg_at_5`：相关 Chunk 在 Top 5 中的折损累计增益；第一版相关性为二值。

运行级同时记录：

- 问题数、关键问题数、逐题结果和失败用例 ID。
- `source_hit_rate_at_5`、`locator_hit_rate_at_5`、`mean_reciprocal_rank`、`mean_ndcg_at_5`。
- 空 Chunk 数、重复 Chunk ID 数、staging 实际数量与审计 `chunk_count` 是否一致。
- 总评测耗时和单题耗时，不把不稳定的机器耗时作为硬门禁。

第一版硬门禁：

```text
所有 critical 用例 source_hit_at_5 = true
所有 critical 用例 locator_hit_at_5 = true
source_hit_rate_at_5 = 1.0
locator_hit_rate_at_5 >= 0.90
mean_reciprocal_rank >= 0.80
mean_ndcg_at_5 >= 0.90
empty_chunk_count = 0
duplicate_chunk_count = 0
actual_vector_count = KnowledgeRun.chunk_count
```

阈值以带版本的 `EvaluationPolicy` 固化在代码中。API 不能由调用者临时降低阈值。

## 评测状态与审计

新增 `knowledge_evaluation_runs` 和 `knowledge_evaluation_cases`。SQLite 保存指标、rank、chunk_id、来源定位、耗时和脱敏失败分类，不保存 Chunk 全文、问题向量或 Authorization 信息。

执行规则：

```text
KnowledgeRun 必须处于 evaluating
→ 创建 evaluation attempt
→ 校验 staging count
→ 执行全部问题
→ 保存逐题和汇总指标
→ 门禁通过：run 保持 evaluating，evaluation=passed，等待显式发布
→ 门禁未通过：run evaluating→rejected，evaluation=rejected
→ 评测基础设施异常：run evaluating→failed，evaluation=failed
```

同一运行只能有一个成功的当前评测。重复请求返回已有报告；并发评测通过数据库条件更新保证只有一个 attempt 获得执行权。

状态机调整为：

```text
evaluating -> promoted | rejected | failed
promoted  -> rolled_back
```

`rejected` 表示人工拒绝或质量门禁不通过；`failed` 只表示执行/评测基础设施失败。

## 活动版本注册表

新增两张表：

```text
knowledge_active_indexes
  user_id, run_id, collection_name, generation, updated_at

knowledge_index_releases
  release_id, user_id, run_id, collection_name,
  previous_run_id, previous_collection_name,
  status, promoted_at, rolled_back_at
```

约束：

- 每个租户最多一个活动指针。
- 尚无活动指针时，读取回退到现有 `user_<user_id>` collection，保证旧数据兼容。
- 只有拥有 `passed` 当前评测且仍为 `evaluating` 的运行可以发布。
- 发布在一个 SQLite `BEGIN IMMEDIATE` 事务内校验 run、评测和当前 generation，写 release、更新活动指针并转换为 `promoted`。
- 发布不复制或删除向量。事务提交前，现有搜索仍读旧指针；提交后，新请求读新指针。
- 只允许回滚当前活动 release。回滚事务恢复 `previous_collection_name`，把运行转为 `rolled_back` 并记录时间。
- 3.3 不自动删除历史 collection；垃圾回收需要独立保留策略，不能与发布事务耦合。

## 搜索与问答收口

现有 `/api/knowledge/search`、`/ask` 和 `/ask/stream` 必须通过统一 `resolve_active_collection(user_id)` 获取 collection：

```text
存在活动指针 → 查询该 staging/release collection
不存在活动指针 → 查询 legacy user_<user_id> collection
```

禁止 Knowledge Agent 把 staging collection 直接暴露给用户输入。搜索结果继续返回来源定位元数据，问答引用不因版本切换丢失。

旧 `/api/knowledge/upload` 暂时保留，但首次发布 KnowledgeRun 后，它写入的 legacy collection 不再是该租户的活动版本。README 必须明确正式知识入库已收敛到 KnowledgeRun。

## API

新增认证端点：

| 端点 | 行为 |
| --- | --- |
| `POST /api/knowledge/runs/{run_id}/evaluate` | 对 evaluating Run 执行或返回幂等评测 |
| `GET /api/knowledge/runs/{run_id}/evaluation` | 返回汇总和逐题报告，不返回 Chunk 全文 |
| `POST /api/knowledge/runs/{run_id}/promote` | 仅发布评测通过的当前租户 Run |
| `POST /api/knowledge/runs/{run_id}/rollback` | 仅回滚当前活动 release |
| `GET /api/knowledge/active-version` | 返回当前 Run、collection、generation 和 legacy 状态 |

不存在或跨租户统一返回 404；状态/并发冲突返回 409；评测基础设施错误返回 422；质量门禁不通过返回 200 的评测报告，状态明确为 `rejected`。

## 错误与恢复

- 评测失败不得修改活动指针或删除 staging，以便人工检查和重新规划。
- 发布事务失败后活动指针和 Run 状态必须同时保持原值。
- Chroma collection 缺失、数量不一致或 metadata 不完整属于 `evaluation_input_error`。
- Embedding 失败为 `embedding_error`，Chroma 查询失败为 `storage_error`，其他异常统一为 `internal_error`；不保存底层异常正文。
- 回滚目标 collection 不存在时拒绝回滚，不修改当前指针。
- 进程在评测中断后，后续请求可把超时 attempt 标记失败并重新建立 attempt；第一版不自动后台重试。

## 测试策略

1. JSONL schema、唯一 ID、来源和 locator 校验。
2. Hit@5、MRR、nDCG 的纯函数单元测试，包括无命中和多相关结果。
3. Fake StagingStore 的通过、拒绝、数量不一致、Embedding/Storage 失败测试。
4. 租户隔离、评测幂等和并发 attempt 测试。
5. 发布门禁、首次 legacy 迁移、连续两次发布、当前版本回滚和缺失 collection 测试。
6. Search/Ask 使用活动指针及无指针 legacy 回退测试。
7. API 认证、404/409/422 和脱敏报告测试。
8. 安装 Chroma 时执行真实本地 collection 查询、发布和回滚集成测试。
9. 3.1、3.2 与现有 RAG 搜索/问答回归全部通过。

## 验收标准

- 现有核心问题的期望来源全部进入 Top 5，关键 locator 全部命中。
- 未通过门禁的运行不能发布，活动索引保持不变。
- 通过门禁的运行可以原子发布，现有搜索和问答自动读取新版本。
- 连续发布后可以回滚到上一完整版本，跨租户和非当前版本回滚被拒绝。
- 发布与回滚不复制向量，不删除历史 collection。
- 评测和发布审计不保存原文、Embedding、凭据或底层异常正文。
- 无外部 LLM 和无网络时，确定性测试与发布门禁仍可运行。
- README、API 表和阶段文档明确 3.3 已完成，RAG 后端开发闭环结束。

## 明确不包含

- Knowledge Workbench 前端页面（3.4）。
- 在线 A/B、用户反馈学习和自动策略调参。
- 历史 collection 自动清理。
- LLM Judge 作为硬发布条件。
- 任意历史版本跳转；第一版只回滚当前版本到直接上一版本。
