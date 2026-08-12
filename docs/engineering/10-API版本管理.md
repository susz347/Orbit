# API 版本管理

> 所有路由统一加 `/api/v1/` 前缀，为未来不兼容变更留空间。前端用常量集中管理，健康检查保持 `/health` 不动。

---

## 改前 vs 改后

**改前**：
```
GET  /api/auth/login
POST /api/knowledge/ask
GET  /api/agents/loops
```

**改后**：
```
GET  /api/v1/auth/login
POST /api/v1/knowledge/ask
GET  /api/v1/agents/loops
```

`/health` 保持不变——健康检查不应受 API 版本影响。

---

## 后端：9 个路由文件统一修改

```python
# 每个路由文件的 APIRouter 定义
router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])  # 原来是 /api/knowledge
router = APIRouter(prefix="/api/v1/auth",       tags=["auth"])
router = APIRouter(prefix="/api/v1/agents",     tags=["agents"])
router = APIRouter(prefix="/api/v1/memory",     tags=["memory"])
router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])
router = APIRouter(prefix="/api/v1/storage",    tags=["storage"])
```

3 个共享 `/api/knowledge` 前缀的路由（knowledge、performance、strategy、logos）统一改为 `/api/v1/knowledge`。

---

## 测试文件：9 个文件同步更新

```python
# 改前
client.post("/api/auth/register", ...)
client.get("/api/knowledge/search", ...)

# 改后
client.post("/api/v1/auth/register", ...)
client.get("/api/v1/knowledge/search", ...)
```

使用 `replace_all=True` 批量替换，确保没遗漏。

---

## 前端：一个常量管全部

```typescript
// frontend/src/lib/api.ts

const V1 = "/api/v1";

export const auth = {
  register: (...) => request(`${V1}/auth/register`, ...),
  login: (...)    => request(`${V1}/auth/login`, ...),
};

export const knowledge = {
  upload: (...) => request(`${V1}/knowledge/upload`, ...),
  search: (...) => request(`${V1}/knowledge/search?q=...`, ...),
  ask: (...)    => request(`${V1}/knowledge/ask`, ...),
};

export const agents = {
  runLoop: (...) => request(`${V1}/agents/loop`, ...),
  ...
};

export const strategy = {
  get: ()   => request(`${V1}/knowledge/strategy`),
  patch: () => request(`${V1}/knowledge/strategy`, ...),
};
```

**收益**：未来升级 v2 时，只需改 `const V1 = "/api/v2"` 一个地方，老客户端继续走 v1，新客户端走 v2。

---

## 设计决策

| 决策 | 原因 |
|------|------|
| 不重定向旧路径 | 强制升级，防止旧路径隐蔽存活 |
| `/health` 不加版本 | 健康检查与 API 版本无关 |
| 前端用常量 | 避免 100+ 处硬编码路径 |
| 测试同步更新 | 防止测试断言旧路径"恰好通过" |
