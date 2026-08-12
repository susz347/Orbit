# LLM 调用可靠性

> AI Agent 系统最脆弱的一环就是外部 LLM API 调用。改之前失败直接抛异常，改之后有了完整的重试 + 熔断 + Fallback 三板斧。

---

## 三层防护金字塔

```
         ┌─────────────────┐
         │  Fallback 模型    │  ← 主模型彻底不行了，切备用模型
         ├─────────────────┤
         │  熔断器           │  ← 连续失败 N 次，拒绝所有请求 60 秒
         ├─────────────────┤
         │  指数退避重试     │  ← 网络抖动、429 限流，等一等重试
         └─────────────────┘
```

---

## 第一层：指数退避重试（tenacity）

### 可重试判断

不是所有异常都应该重试：

```python
def _is_retryable(exception: Exception) -> bool:
    if isinstance(exception, urllib.error.URLError):
        return True                        # 网络不通 → 重试
    if isinstance(exception, urllib.error.HTTPError):
        code = getattr(exception, "code", 0)
        return code == 429 or (500 <= code < 600)  # 限流/服务端错误 → 重试
    if isinstance(exception, TimeoutError):
        return True                        # 超时 → 重试

    # 关键词兜底
    msg = str(exception).lower()
    for kw in ["timeout", "rate limit", "server error"]:
        if kw in msg:
            return True
    return False  # 401 认证失败、403 权限不足 → 不重试
```

### 重试策略

```python
retry(
    stop=stop_after_attempt(3),              # 最多 3 次
    wait=wait_exponential(min=1.0, max=30.0), # 等待 1s → 2s → 4s → 最多 30s
    retry=retry_if_exception(_is_retryable),
    reraise=True,                             # 3 次都失败才向上抛
)
```

---

## 第二层：熔断器（pybreaker）

连续失败不是偶然——如果 LLM API 宕机了，反复重试只会耗尽本服务资源。

```python
_breaker = pybreaker.CircuitBreaker(
    fail_max=5,          # 连续失败 5 次 → 触发熔断
    reset_timeout=60,    # 60 秒后自动半开尝试恢复
    name="llm_api",
)
```

**状态机**：

```
 CLOSED（正常）──连续失败5次──→ OPEN（拒绝所有请求）
                                     │
                                60 秒后
                                     │
                                     ▼
                              HALF_OPEN（下一次请求试探）
                              /                \
                        成功 → CLOSED    失败 → OPEN（重新计时）
```

---

## 第三层：Fallback 模型

```python
# 环境变量配置
LLM_MODEL=deepseek-v4-pro          # 主模型
LLM_FALLBACK_MODEL=gpt-4o-mini     # 备用模型
LLM_FALLBACK_API_KEY=sk-...        # 备用模型的 Key（默认与主模型共用）
```

连 fallback 模型都有自己独立的熔断器，防止级联故障。

---

## 核心调用流程

```python
def call_llm_with_retry(call_fn, model_name, fallback_model, fallback_api_key):
    last_error = None

    try:
        if _breaker.current_state == "open":
            raise CircuitBreakerError("主模型熔断器已开启")

        decorated_call = retry_decorator(_breaker.call)
        result = decorated_call(call_fn)
        return {"success": True, "data": result, "model_used": model_name}

    except CircuitBreakerError as e:
        last_error = e
    except Exception as e:
        last_error = e

    # ── Fallback ──
    if not fallback_api_key:
        raise LLMCallFailedError(f"LLM 调用失败: {last_error}")

    try:
        if _breaker_fallback.current_state == "open":
            raise CircuitBreakerError("Fallback 熔断器已开启")

        decorated_fallback = retry_decorator(_breaker_fallback.call)
        result = decorated_fallback(call_fn)
        return {"success": True, "data": result, "model_used": fallback_model}

    except Exception as e:
        raise LLMCallFailedError(
            f"主模型 {model_name} 和 fallback {fallback_model} 均调用失败: {e}"
        )
```

返回值统一含 `model_used` 字段——上层代码能知道最终用了哪个模型，记录到日志和指标。

---

## 集成位置

两个 LLM 调用入口都已集成：

- `backend/app/generate/service.py`：非流式 RAG 问答，调用后记录 token、延迟、模型到结构化日志
- `backend/app/stream/service.py`：流式 RAG 问答，流式连接建立也走重试逻辑

---

## 效果

| 场景 | 改前 | 改后 |
|------|------|------|
| 网络抖动 | 直接报错 | 自动重试 3 次，延迟 1s/2s/4s |
| LLM API 429 | 直接报错 | 等待后自动重试 |
| LLM API 持续宕机 | 每次请求都超时等 30s | 5 次失败后熔断，后续请求直接拒绝 |
| DeepSeek 挂了 | 服务瘫痪 | 自动切到 GPT-4o-mini 继续服务 |
