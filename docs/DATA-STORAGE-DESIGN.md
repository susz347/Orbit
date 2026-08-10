# Orbit 数据存储设计方案

> 状态：草案 v1
> 范围：对话消息持久化、记忆层、缓存层、数据库选型与整合
> 背景：当前 Orbit 原始对话消息未落库，刷新即丢；本文档定义可落地的存储架构与分阶段实施计划

---

## 1. 现状诊断

### 1.1 核心缺陷：原始对话消息未持久化

| 数据 | 当前位置 | 是否持久化 | 问题 |
|---|---|---|---|
| 原始对话消息 | 仅 React state（内存） | ❌ 刷新即丢 | `frontend/src/components/chat/chat-interface.tsx:97` `useState<Message[]>([])`，无任何落盘 |
| 会话列表 conversations | 仅 React state（内存） | ❌ 刷新即丢 | `frontend/src/app/page.tsx:24`，且 `Conversation` 接口只有 `id/title`，无消息内容 |
| LLM 配置 | localStorage | ✅ | 与对话无关 |
| 对话总结 | `data/memory/YYYY-MM-DD.md` | ✅ | `backend/app/api/logos.py:16`，需前端主动 POST 整段文本，存的是总结非原文 |
| 对话摘要+要点 | `backend/memory.db` SQLite `conversation_summary` 表 | ✅ | `backend/app/memory/summary.py:10`，只存摘要非原文 |

**结论**：当前只保存了对话的"压缩版"（总结/摘要），原始一问一答未落库。用户刷新浏览器、切换会话再切回，对话记录即丢失；侧边栏点"历史对话"只会切 `activeConversation` id，不会恢复消息（`ChatInterface` 无按 conversationId 加载历史的逻辑）。

### 1.2 现有存储资产

- SQLite × 3：`backend/memory.db`（记忆）、`backend/multitenant`（用户/租户/session）、`backend/structured_data.db`（Excel/CSV 导入）
- 向量库：ChromaDB（`backend/app/store/`，多租户 Collection 隔离）
- 文件：`data/memory/YYYY-MM-DD.md`（Logos 总结）、`data/uploads/`（上传文件）
- 预留：`backend/app/multitenant/db.py:11` `_resolve_db_path()` 已支持 `DATABASE_URL` scheme 解析，预留 PostgreSQL 升级路径

---

## 2. 参考架构：CodeBuddy 实测存储

通过对本机 CodeBuddy/WorkBuddy 实际落盘文件的探查，提炼可借鉴的设计模式。

### 2.1 目录分层

- `~/.workbuddy/` —— 主数据根目录
- `~/.codebuddy/` —— CLI/插件侧：会话 JSONL、记忆 md、settings、skills
- `~/Library/Application Support/CodeBuddyExtension/` —— IDE 扩展：`Cache/`(68K) `Data/` `Logs/`

### 2.2 四种存储介质并用

| 介质 | 用途 | 实测实例 |
|---|---|---|
| Markdown | 人可读/可编辑/可 diff 的记忆 | `~/.workbuddy/MEMORY.md` `SOUL.md` `USER.md` `IDENTITY.md`；`~/.codebuddy/memery/<workspace-uuid>_memery.md` |
| JSONL 追加 | 流式对话/日志，天然时序 | `~/.codebuddy/projects/Users-ace-Code/<session-uuid>.jsonl` + 同名目录 `tool-results/`；`history.jsonl` 字段 `display/pastedContents/timestamp/project` |
| SQLite + WAL | 需查询/事务/并发的结构化数据 | `~/.workbuddy/edge-sync-mapping.db` + `.db-wal`(655K) + `.db-shm` + `.workbuddy-sqlite-migrations/` |
| 文件系统 blob/索引 | 内容寻址、大文件、缓存 | `blobs/`(151) `artifact-index/`(169) `file-history/`(212) `audit-log/` `automation-backups/` `clipboard-images/`；`.policy-cache.json` |

### 2.3 可借鉴的设计哲学

1. **人机双读**：记忆用 Markdown，可 git diff、可审计、可手改
2. **追加优先**：对话用 JSONL 追加写，匹配流式 + 时序，不丢增量
3. **结构化才上 DB**：只有需查询/事务/并发的数据才进 SQLite
4. **WAL 模式**：SQLite 开 `journal_mode=WAL` 提升并发读
5. **内容寻址分离**：`blobs/` 存内容、`artifact-index/` 存索引，互不耦合
6. **缓存轻量**：Cache 仅 68K，策略缓存用小 JSON，不滥用 DB

---

## 3. 选型原则

按数据特征选介质，不一 DB 打天下。

| 数据特征 | 选型 | 理由 |
|---|---|---|
| 人需读写的偏好/总结 | Markdown | 可 diff、可审计、零运维 |
| 追加型时序/流式消息 | JSONL | 追加写性能好、天然时序、易归档 |
| 需查询/事务/并发 | SQLite + WAL | 轻量、单文件、并发读够用 |
| 向量检索 | ChromaDB（已有） | 语义检索 |
| 热数据缓存 | 进程内 LRU + JSON 文件 | 省 token、低延迟 |
| 结构化导入(Excel/CSV) | 独立 SQLite | 按来源隔离，避免污染主库 |

**现阶段不上 PostgreSQL/Redis 的理由**：单机、用户量小，SQLite WAL 并发读足够（CodeBuddy 自己也是 SQLite + WAL）；零运维、单文件易备份。等到「多实例共享 / 高并发写 / 强多租户隔离」任一需求出现再迁。

---

## 4. 目标架构

### 4.1 存储介质矩阵

```
┌─────────────────────────────────────────────────────────────┐
│                       Orbit 存储层                          │
├──────────────┬──────────────────────────────────────────────┤
│ Markdown     │ data/memory/YYYY-MM-DD.md  (对话总结，人读)  │
│              │ data/profiles/<user>/PROFILE.md (用户画像)    │
├──────────────┼──────────────────────────────────────────────┤
│ JSONL        │ data/sessions/<uid>/<conv_id>.jsonl (原始消息)│
│              │ data/sessions/<uid>/<conv_id>/tool-results/  │
├──────────────┼──────────────────────────────────────────────┤
│ SQLite+WAL   │ orbit.db: conversations / messages_meta /    │
│ (主库)       │   user_profile / project_context /           │
│              │   conversation_summary / users / sessions    │
├──────────────┼──────────────────────────────────────────────┤
│ SQLite       │ structured_data.db (Excel/CSV 导入，独立)    │
├──────────────┼──────────────────────────────────────────────┤
│ ChromaDB     │ 向量检索（多租户 Collection 隔离，保留）     │
├──────────────┼──────────────────────────────────────────────┤
│ 缓存 L1      │ 进程内 LRU: embedding / LLM 响应 / ctx 窗口 │
│ 缓存 L2      │ .cache/*.json: 健康/路由/策略                │
└──────────────┴──────────────────────────────────────────────┘
```

### 4.2 对话消息落库（修当前痛点）

**双写策略：JSONL 存原文 + SQLite 存元数据。**

- 原始消息 → JSONL 追加：`data/sessions/<user_id>/<conv_id>.jsonl`，每条一行
- 元数据 → SQLite `conversations` 表，供侧边栏列表/检索
- SQLite 只存元数据 + 近期热消息索引，海量原始消息留 JSONL——避免 DB 膨胀（CodeBuddy 同款做法）

**写入时机**：
- 用户消息：`handleSend` 提交时立即 append 一条 user 记录
- 助手消息：流式完成后 append 一条 assistant 记录（流式过程中只更 state，完成再落盘）
- tool 调用结果：写入 `data/sessions/<uid>/<conv_id>/tool-results/<call_id>.json`，消息里只存引用

### 4.3 记忆/总结层（保留现有，补强）

- 保留 `data/memory/YYYY-MM-DD.md`（Logos 总结，人可读，按天归档）
- 保留 SQLite `conversation_summary`（可查询的摘要 + key_points）
- 新增 `data/profiles/<user>/PROFILE.md`：用户画像的 Markdown 版（人可编辑），与 SQLite `user_profile` 表双写，Markdown 为权威源、SQLite 为查询索引

### 4.4 缓存层（当前缺失，三层设计）

| 层 | 介质 | 内容 | 失效策略 |
|---|---|---|---|
| L1 | 进程内 LRU（`functools.lru_cache` / dict + 容量上限） | embedding 结果（text→vector）、LLM 响应（hash(prompt)→answer）、当前 session 上下文窗口 | 容量上限 + TTL |
| L2 | 文件 JSON（`.cache/*.json`） | 健康检查结果、模型路由表、策略缓存 | mtime TTL |
| L3 | Redis（暂不引入） | 多实例共享缓存 | 等多 worker/多实例需求出现 |

**优先实现 L1**：embedding 缓存和 LLM 响应缓存能立刻省 token、降延迟，ROI 最高。

### 4.5 DB 整合方案

**合并 3 个 SQLite 为 1 个 `orbit.db`**（memory + multitenant + 会话元数据多表），减少连接管理。关键配置：

```sql
PRAGMA journal_mode=WAL;       -- CodeBuddy 实测在用，提升并发读
PRAGMA synchronous=NORMAL;     -- WAL 下安全且更快
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;      -- 避免短时锁等待报错
```

**保留独立**：
- `structured_data.db`（Excel/CSV 导入，按来源隔离，避免污染主库）
- ChromaDB（向量检索，独立进程）

**迁移**：用 `.orbit-migrations/` 目录管理 schema 版本（对标 CodeBuddy 的 `.workbuddy-sqlite-migrations/`），每次建表/改表一个版本脚本，启动时自动执行未应用的。

---

## 5. 数据模型

### 5.1 orbit.db 表结构

```sql
-- 会话元数据
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,          -- conv-<timestamp>
    user_id     INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT '新对话',
    jsonl_path  TEXT NOT NULL,             -- data/sessions/<uid>/<id>.jsonl
    message_count INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC);

-- 消息元数据（仅近期/热数据，原文在 JSONL）
CREATE TABLE messages_meta (
    id              TEXT PRIMARY KEY,      -- msg-<seq>
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,         -- user / assistant / system
    content_preview TEXT,                  -- 前 200 字，供列表预览
    tool_calls      TEXT,                  -- JSON: tool 调用引用
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX idx_msg_conv ON messages_meta(conversation_id, created_at);

-- 已有表保留：user_profile / project_context / conversation_summary
-- 已有表保留：users / tenants / sessions（来自 multitenant）
```

### 5.2 JSONL 消息格式

`data/sessions/<user_id>/<conv_id>.jsonl`，每行一条：

```json
{"id":"msg-1","role":"user","content":"总结文档","ts":1722768000123}
{"id":"msg-2","role":"assistant","content":"...","ts":1722768002345,"model":"deepseek-chat","tokens":{"in":120,"out":800}}
{"id":"msg-3","role":"assistant","content":"调用工具","ts":1722768003456,"tool_call":{"id":"call-1","name":"kb_search","result_ref":"tool-results/call-1.json"}}
```

### 5.3 文件布局

```
data/
├── sessions/
│   └── <user_id>/
│       ├── <conv_id>.jsonl
│       └── <conv_id>/
│           └── tool-results/
│               └── <call_id>.json
├── memory/
│   └── YYYY-MM-DD.md              # Logos 总结
├── profiles/
│   └── <user_id>/
│       └── PROFILE.md             # 用户画像（人可编辑）
├── uploads/                       # 上传文件（已有）
└── structured_data.db             # Excel/CSV 导入（独立）
backend/
├── orbit.db                       # 合并后的主库
├── orbit.db-wal
├── orbit.db-shm
└── .orbit-migrations/             # schema 版本脚本
    ├── 001_init.sql
    └── 002_add_messages_meta.sql
.cache/                            # L2 文件缓存
├── health.json
├── model-routing.json
└── policy.json
```

---

## 6. API 设计

### 6.1 新增对话相关接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat/conversations` | 创建会话，返回真实 conv_id 与 jsonl_path |
| GET | `/api/chat/conversations` | 列出当前用户会话（分页，按 updated_at DESC） |
| GET | `/api/chat/conversations/{id}/messages` | 拉取历史消息（优先 JSONL，热数据走 messages_meta） |
| POST | `/api/chat/conversations/{id}/messages` | 追加一条消息（同时写 JSONL + messages_meta） |
| PATCH | `/api/chat/conversations/{id}` | 更新标题等 |
| DELETE | `/api/chat/conversations/{id}` | 删除会话（删 JSONL + DB 记录） |

### 6.2 缓存接口（内部）

- `cache_get(category, key)` / `cache_set(category, key, value, ttl)` —— 统一封装 L1（进程内）+ L2（文件），L3 预留

---

## 7. 落地实施计划

按优先级分阶段，每阶段可独立上线、独立验证。

### 阶段 1：对话消息持久化（最高优先，解决刷新即丢）

**后端**
- `backend/app/storage/session_store.py`（新增）：JSONL 读写 + conversations/messages_meta 表操作
- `backend/app/api/chat.py`（新增）：上节 6.1 接口
- `backend/app/db.py`（新增）：统一连接 + WAL 配置 + 迁移执行器

**前端**
- `chat-interface.tsx`：`handleSend` 提交时 POST 消息；组件挂载时按 conversationId GET 历史回填 `messages`
- `page.tsx`：`conversations` 改为从 `GET /api/chat/conversations` 拉取；`handleNewChat` 调后端创建

**验收**：刷新页面后对话记录仍在；侧边栏历史可点击恢复完整消息。

### 阶段 2：DB 合并 + WAL + 迁移

- 新建 `orbit.db`，把 `memory.db`/`multitenant` 的表迁入
- 启用 WAL，配置 PRAGMA
- 建 `.orbit-migrations/` 与迁移执行器
- 删除旧 `memory.db`/`multitenant` 引用，统一走 `orbit.db`

**验收**：单文件备份；并发读不阻塞写；迁移可重复执行幂等。

### 阶段 3：缓存层 L1

- `backend/app/cache.py`（新增）：LRU + TTL，封装 embedding/LLM 响应/上下文窗口缓存
- 接入 `backend/app/rag/`（embedding）与 LLM 调用处

**验收**：相同 prompt 命中缓存不重复调 LLM；embedding 重复文本不重算。

### 阶段 4：记忆层补强

- `data/profiles/<user>/PROFILE.md` 双写（Markdown 权威 + SQLite 索引）
- 启动时加载 PROFILE.md 进上下文（对标 CodeBuddy 每次对话加载 MEMORY）

**验收**：用户画像可在 Markdown 手改后下次对话生效。

### 阶段 5（按需）：L2 文件缓存 / Redis / PostgreSQL

- L2 文件缓存：健康检查、模型路由表
- Redis：出现多 worker 共享缓存需求时
- PostgreSQL：出现多租户高并发写需求时（已有 DATABASE_URL scheme 预留）

---

## 8. 风险与回滚

| 风险 | 应对 |
|---|---|
| JSONL 文件并发写冲突 | 单会话串行 append；跨会话天然隔离；WAL 模式下 SQLite 元数据并发安全 |
| JSONL 文件增长过大 | 按月/按大小切分；老会话归档到 `data/sessions/_archive/`；只保留 messages_meta 预览 |
| DB 合并迁移丢数据 | 迁移脚本幂等 + 旧库保留 N 天 + 迁移前后行数校验 |
| 缓存与源数据不一致 | L1 只缓存纯函数结果（embedding/LLM）；业务数据不走 L1；L2 带 mtime TTL |
| 用户画像双写不一致 | Markdown 为权威源，SQLite 仅作索引，启动时以 Markdown 重建索引 |

---

## 9. 附录：CodeBuddy 实测路径清单

| 路径 | 作用 |
|---|---|
| `~/.workbuddy/MEMORY.md` | 永久记忆（人可编辑） |
| `~/.workbuddy/SOUL.md` | 行为准则 |
| `~/.workbuddy/USER.md` | 用户画像 |
| `~/.workbuddy/IDENTITY.md` | 身份 |
| `~/.workbuddy/edge-sync-mapping.db` + `-wal` + `-shm` | 同步映射（SQLite WAL） |
| `~/.workbuddy/.workbuddy-sqlite-migrations/` | schema 迁移 |
| `~/.workbuddy/blobs/` `artifact-index/` `file-history/` | 内容寻址 + 索引 + 历史 |
| `~/.codebuddy/projects/<user-project>/<session-uuid>.jsonl` | 对话消息（JSONL） |
| `~/.codebuddy/projects/<user-project>/<session-uuid>/tool-results/` | 工具调用结果 |
| `~/.codebuddy/memery/<workspace-uuid>_memery.md` | 项目级记忆 |
| `~/.codebuddy/history.jsonl` | 命令历史 |
| `~/Library/Application Support/CodeBuddyExtension/Cache/` | IDE 缓存（68K，轻量） |
