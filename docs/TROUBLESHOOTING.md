# Orbit 项目排查手册

> 用途：快速掌握项目架构、理解数据流转、独立定位问题、用 curl 直接调试接口。
> 适用场景：对话功能异常、检索不到内容、模型报错、前后端不通等。

---

## 一、项目全景架构

```
┌─────────────────────────────────────────────────────────┐
│                     浏览器 (localhost:3000)               │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐ │
│  │ Settings │  │ Chat UI  │  │ KnowledgeBase / 策略   │ │
│  │ Panel    │  │          │  │ 面板                   │ │
│  └────┬─────┘  └────┬─────┘  └───────────┬───────────┘ │
│       │              │                    │             │
│       └──────────────┼────────────────────┘             │
│                      ▼                                  │
│           ┌──────────────────┐                          │
│           │  api.ts (统一层)  │  ← 所有 API 调用进这里   │
│           │  getApiKey()     │  ← 读 localStorage       │
│           │  getModel()      │                          │
│           │  request()/      │                          │
│           │  streamAsk()     │                          │
│           └────────┬─────────┘                          │
└────────────────────┼────────────────────────────────────┘
                     │ HTTP (fetch)
                     ▼
┌────────────────────┼────────────────────────────────────┐
│              后端 (localhost:8001)                       │
│  ┌─────────────────▼──────────────────────────────┐    │
│  │  main.py                                       │    │
│  │  ├─ CORS 中间件                                 │    │
│  │  ├─ RequestID 中间件                            │    │
│  │  └─ 注册 8 个路由模块                           │    │
│  └──────────┬─────────────────────────────────────┘    │
│             ▼                                          │
│  ┌──────────────────────────────────────────────┐      │
│  │           api/knowledge.py                     │      │
│  │  /api/knowledge/ask/stream  ← 对话入口          │      │
│  │  /api/knowledge/search       ← 检索入口         │      │
│  │  /api/knowledge/upload       ← 上传入口         │      │
│  └──┬──────────┬──────────┬─────────────────────┘      │
│     ▼          ▼          ▼                            │
│  ┌──────┐ ┌──────┐ ┌──────────┐                       │
│  │stream│ │search│ │generate  │  ← 三种问答方式         │
│  │(流式)│ │(检索)│ │(非流式)  │                        │
│  └──┬───┘ └──┬───┘ └────┬─────┘                       │
│     │        │           │                             │
│     └────────┼───────────┘                             │
│              ▼                                         │
│  ┌───────────────────────────────────────┐            │
│  │         核心处理链 (stream)            │            │
│  │  ① cache   → 语义缓存命中？直接返回    │            │
│  │  ② search  → 向量检索知识库            │            │
│  │  ③ router  → 意图识别 + 模型选择       │            │
│  │  ④ LLM API → DeepSeek/OpenAI 生成     │            │
│  └───────────────────────────────────────┘            │
│                                                        │
│  支撑层:                                                │
│  ┌────────┐ ┌───────┐ ┌───────┐ ┌───────────┐        │
│  │ store  │ │ embed │ │ chunk │ │ middleware │        │
│  │ChromaDB│ │向量化 │ │文本切割│ │ auth认证  │        │
│  └────────┘ └───────┘ └───────┘ └───────────┘        │
└────────────────────────────────────────────────────────┘
```

---

## 二、一次对话的完整数据流（最重要）

以 "hello" 为例，从用户点击发送到看到回复：

### 第 1 层：前端（浏览器）

```
① chat-interface.tsx:handleSend("hello")
   └─ 创建 user 消息 + assistant 占位消息 → setMessages

② api.ts:streamAsk("hello", 5, onToken, onDone, onError, signal)
   ├─ getApiKey()    → 读 localStorage["orbit_llm_models_v2"] → 取 enabled 模型的 apiKey
   ├─ getModel()     → 同上 → 取 enabled 模型的 name
   ├─ getToken()     → localStorage["orbit_token"]
   └─ fetch("http://localhost:8001/api/knowledge/ask/stream?q=hello&top_k=5")
        Headers: { Authorization, X-API-Key, X-LLM-Model }
```

### 第 2 层：后端路由

```
③ api/knowledge.py api_ask_stream()
   ├─ 读 headers: X-API-Key, X-LLM-Model
   ├─ 读 query param: q="hello", top_k=5
   └─ 返回 StreamingResponse(stream_ask(...))
```

### 第 3 层：流式处理链（stream/__init__.py）

```
④ 缓存检查
   cache_get("hello") → 命中则直接返回，miss 则继续

⑤ 向量检索
   search("hello", top_k=5)
   ├─ embed/__init__.py → encode(["hello"]) → 384 维向量
   ├─ store/__init__.py → get_collection() → ChromaDB
   └─ 返回 [{text, metadata, score}, ...] 或空列表
   相关度过滤：score < 0.3 的结果丢弃

⑥ 模型路由
   route_model("hello", scores)
   ├─ Layer 1: 正则匹配 → e.g. "short_query", conf=0.60
   ├─ Layer 2: 语义路由 (embedding 匹配意图描述)
   └─ 返回 { tier, model, reason, confidence, needs_clarification }

⑦ API Key / 模型决断
   api_key = 前端传入 || 环境变量 LLM_API_KEY || ""
   model   = 前端传入 || 路由推荐 || 环境变量 LLM_MODEL || "gpt-4o-mini"

⑧ 调用 LLM
   POST https://api.deepseek.com/v1/chat/completions
   Header: Authorization: Bearer {api_key}
   Body: { model, messages, temperature, max_tokens, stream: true }

⑨ 流式返回
   逐行读 SSE → yield _sse("token", {"text": "你"}) → ... → yield _sse("done", ...)
```

### 第 4 层：前端解析

```
⑩ api.ts:streamAsk 的 while(true) 循环
   每行 → 检查 data: 前缀 → JSON.parse
   ├─ data.stage   → 跳过（状态事件）
   ├─ data.message → onError()（错误事件）
   ├─ data.text    → onToken() → chat-interface.tsx 拼内容
   └─ data.model   → onDone() → setIsLoading(false)
```

### SSE 流事件对照表

| 事件 | 含义 | 关键字段 |
|------|------|----------|
| `status` | 处理阶段 | `stage`: start / cache_miss / retrieving / retrieved / routing |
| `token` | LLM 流式输出 | `text` |
| `error` | 出错 | `message`（如 `HTTP Error 401: Authorization Required`） |
| `done` | 结束 | `model`（实际发送的模型名）、`error` |

> 排查要点：`routing` 里的 `model` 是**路由推荐**的模型；`done` 里的 `model` 是**实际发送**的模型。两者不一致时，说明前端或配置层覆盖了路由结果。

---

## 三、文件地图：什么地方坏了看哪个文件

### 🔴 对话功能相关（出问题时优先看）

| 文件 | 负责什么 | 什么时候看它 |
|------|----------|--------------|
| `frontend/src/components/chat/chat-interface.tsx` | 聊天界面主逻辑、消息收发 | 发送没反应、消息不显示 |
| `frontend/src/lib/api.ts` | 所有 API 调用、localStorage 读写、SSE 解析 | API Key/模型名读取不对、SSE 解析错误 |
| `frontend/src/components/settings/settings-panel.tsx` | 模型配置页、API Key 保存 | 配置保存后不生效 |
| `backend/app/api/knowledge.py` | 知识库全部 HTTP 路由 | 后端没收到请求、路由报错 |
| `backend/app/stream/__init__.py` | **流式问答核心逻辑**（最重要） | 回答内容不对、报错、不走 LLM |
| `backend/app/router/__init__.py` | 意图识别、模型选择 | 模型选错、说话不对题 |
| `backend/app/search/__init__.py` | 向量检索 | 搜不到东西、检索不相关 |
| `backend/app/cache/__init__.py` | 语义缓存 | 相同问题返回旧答案、「没输出」 |

### 🟡 支撑模块

| 文件 | 负责什么 |
|------|----------|
| `backend/app/embed/__init__.py` | 文本 → 向量（sentence-transformers） |
| `backend/app/store/__init__.py` | ChromaDB 存储 |
| `backend/app/chunk/__init__.py` | 文档切割 |
| `backend/app/ingest/__init__.py` | 文件解析（PDF/Markdown/TXT） |
| `backend/app/generate/__init__.py` | 非流式问答（/api/knowledge/ask POST） |
| `backend/app/config.py` | 全局策略配置 |
| `backend/app/main.py` | FastAPI 入口、CORS、路由注册 |
| `backend/app/middleware/auth.py` | JWT 认证 |

### 🟢 前端其他组件

| 文件 | 负责什么 |
|------|----------|
| `frontend/src/app/page.tsx` | 页面入口、标签切换、引导流程 |
| `frontend/src/lib/auth-context.tsx` | 登录状态管理 |

---

## 四、用 curl 直接调接口（不走前端）

### 1. 健康检查

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

### 2. 流式对话（最常用）

```bash
# 无 API Key（走环境变量 fallback）
curl -sN "http://localhost:8001/api/knowledge/ask/stream?q=hello&top_k=5"

# 带 API Key + 指定模型
curl -sN "http://localhost:8001/api/knowledge/ask/stream?q=hello&top_k=5" \
  -H "X-API-Key: sk-你的真实Key" \
  -H "X-LLM-Model: deepseek-chat"
```

调试技巧：只过滤关键事件，跳过 status：

```bash
curl -sN "http://localhost:8001/api/knowledge/ask/stream?q=hello&top_k=5" \
  -H "X-API-Key: sk-xxx" -H "X-LLM-Model: deepseek-chat" \
  2>&1 | grep -E "^event: (error|done|token)" -A1
```

### 3. 非流式对话

```bash
curl -s http://localhost:8001/api/knowledge/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-xxx" \
  -H "X-LLM-Model: deepseek-chat" \
  -d '{"question": "hello", "top_k": 5}' | python3 -m json.tool
```

### 4. 知识库检索

```bash
# 搜文档
curl -s "http://localhost:8001/api/knowledge/search?q=Orbit是什么&top_k=3" | python3 -m json.tool

# 格式化文本输出
curl -s "http://localhost:8001/api/knowledge/search?q=Orbit&top_k=3&format=text" | python3 -m json.tool
```

### 5. 上传文档

```bash
# 上传文件
curl -s http://localhost:8001/api/knowledge/upload \
  -F "file=@/path/to/your/document.pdf" | python3 -m json.tool

# 直接上传文本
curl -s -X POST "http://localhost:8001/api/knowledge/upload-text?text=Orbit是一个AI系统&source=manual" | python3 -m json.tool
```

### 6. 策略查看 / 修改

```bash
# 查看当前策略
curl -s http://localhost:8001/api/knowledge/strategy | python3 -m json.tool

# 修改 chunk_size
curl -s -X PATCH http://localhost:8001/api/knowledge/strategy \
  -H "Content-Type: application/json" \
  -d '{"chunk": {"chunk_size": 800}}' | python3 -m json.tool
```

### 7. 认证

```bash
# 注册
curl -s -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"123456"}' | python3 -m json.tool

# 登录
curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"123456"}' | python3 -m json.tool
```

### 8. 缓存管理

```bash
# 查看缓存统计
curl -s http://localhost:8001/api/knowledge/cache/stats | python3 -m json.tool

# 清空缓存（解决"相同问题返回旧答案"）
curl -s -X DELETE http://localhost:8001/api/knowledge/cache | python3 -m json.tool
```

### 9. 删除索引

```bash
curl -s -X DELETE "http://localhost:8001/api/knowledge/source?source=test_doc.md" | python3 -m json.tool
```

---

## 五、排错速查表

| 现象 | 第一步该看的文件 | 第二步 |
|------|-----------------|--------|
| 发送没反应 | `chat-interface.tsx` handleSend | 浏览器 Console 有无报错 |
| 一直转圈没输出 | 后端日志 `tail -f /tmp/orbit_backend.log` | `stream/__init__.py` LLM 调用是否成功 |
| 显示 401/400 错误 | curl 直接调接口 | `api.ts:getApiKey()` 读的 localStorage 值对不对 |
| 模型名不对 | 浏览器 Console: `localStorage.getItem("orbit_llm_models_v2")` | settings-panel `persist()` 是否正确写入 |
| 回答内容不对 | `stream/__init__.py` 的 system_prompt | `router/__init__.py` 路由决策 |
| 搜不到文档 | curl `/api/knowledge/search?q=xxx` | `search/__init__.py` + `store/__init__.py` |
| 后端起不来 | `tail -30 /tmp/orbit_backend.log` | `main.py` 或 `embed/__init__.py` 模型加载 |

---

## 六、日常调试流程（推荐）

```
出问题了
  │
  ├─ 1. 先用 curl 调接口确认是前端还是后端问题
  │     curl "http://localhost:8001/api/knowledge/ask/stream?q=test" \
  │       -H "X-API-Key: sk-xxx" -H "X-LLM-Model: deepseek-chat"
  │
  ├─ 2. 如果 curl 通 → 前端问题
  │     打开浏览器 F12 → Network → 看请求头/响应体
  │     打开 Console → 查 localStorage
  │
  └─ 3. 如果 curl 不通 → 后端问题
        tail -f /tmp/orbit_backend.log
        再不行，在 stream/__init__.py 加 logging 打印 payload
```

### 浏览器端排查辅助命令（F12 Console）

```javascript
// 查看当前 localStorage 中实际存储的模型配置
const models = JSON.parse(localStorage.getItem("orbit_llm_models_v2") || "[]");
console.table(models.map(m => ({ name: m.name, enabled: m.enabled, apiKey: m.apiKey ? m.apiKey.slice(0,8)+'...' : '(空)' })));

// 检查启用模型的 Key 是否有效
const active = models.find(m => m.enabled);
console.log("启用模型:", active?.name);
console.log("API Key 长度:", active?.apiKey?.length, "(DeepSeek 应为 35，sk- 开头)");
console.log("API Key 前10位:", active?.apiKey?.slice(0, 10));
```

---

## 七、实战案例：对话 401/400 报错排查

### 案例背景

前端对话返回 `event: error / HTTP Error 401: Authorization Required`，但 curl 直接调 DeepSeek 是通的。

### 关键线索

```
event: status
data: {"stage": "routing", "model": "gpt-4o-mini", ...}   ← 路由推荐
...
event: error
data: {"message": "HTTP Error 401: Authorization Required"}
event: done
data: {"model": "deepseek-chat", "error": true}           ← 实际发送
```

### 排查结论（两个常见坑）

**坑 1：模型名无效**
- 真实模型名是 `deepseek-chat` / `deepseek-reasoner`，不是 `deepseek v4`（带空格是无效名）。
- 前端传的 `X-LLM-Model` 会**直接覆盖**路由推荐：
  ```python
  model_name = model or route.model or os.getenv("LLM_MODEL", "gpt-4o-mini")
  ```
- 后端按模型名子串选择 base_url（`"deepseek" in model_name.lower()` → DeepSeek API）。

**坑 2：API Key 里粘贴了整条 curl 命令**
- 把 `curl -s https://api.deepseek.com/v1/chat/completions -H ... -d ...`（256 字符）整个贴进了 API Key 输入框。
- 结果后端发的是 `Authorization: Bearer curl -s https://api.deepseek.com...`，必然 401。
- 正确做法：只复制 `Bearer ` 后面的 `sk-xxx...` 部分（约 35 位）。

### 教训总结

1. 出错时先看 SSE 里 `error` 事件的具体 message，不要只看状态码。
2. 对比 `routing.model`（推荐）与 `done.model`（实际），判断是否被覆盖。
3. 检查 localStorage 中 API Key 的**长度和前几位**，一眼看出是不是贴错内容。
4. 模型配置读写链路是实时的（无缓存）：`settings-panel.tsx` 每次按键写 localStorage → `api.ts` 每次请求实时读取。

---

## 八、常用运维命令

```bash
# 启动后端（后台运行，日志到 /tmp/orbit_backend.log）
cd /Users/ace/Desktop/Skill/Orbit/backend
pkill -f "uvicorn app.main" || true
nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001 > /tmp/orbit_backend.log 2>&1 &

# 实时看后端日志
tail -f /tmp/orbit_backend.log

# 检查前后端进程
lsof -ti :8001 && echo "BACKEND_RUNNING" || echo "BACKEND_DOWN"
lsof -ti :3000 && echo "FRONTEND_RUNNING" || echo "FRONTEND_DOWN"

# 后端加 LLM 请求 debug 日志的位置（stream/__init__.py）
# 在 payload 构建后、urllib.request.Request 前打印 payload；在 except 里打印 e.read() 响应体
```
