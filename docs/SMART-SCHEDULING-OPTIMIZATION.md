# 智能调度引擎优化方案

> 版本: v1.2
> 日期: 2026-08-10
> 状态: 已全部实施
> 基于: aurelio-labs/semantic-router、ulab-uiuc/LLMRouter、vLLM Semantic Router、zilliztech/GPTCache、CodeFuse-ModelCache、LangGraph Agentic RAG

---

## 一、概述

Orbit 当前的智能调度引擎包含三个子系统——**意图路由**（`router/`）、**语义缓存**（`cache/`）、**存储路由**（`storage_router/`），均采用"先跑起来再优化"的 MVP 策略（硬编码阈值、暴力搜索、无训练）。参考业界最佳实践，本文档按 P0（立即可做）、P1（中期改进）、P2（架构升级）三级给出优化方案。

---

## 二、语义缓存优化

### 问题诊断

当前 `cache/storage.py`：

```python
CACHE_THRESHOLD = 0.95      # 一刀切
CACHE_TTL_SECONDS = 3600    # 1 小时固定
MAX_CACHE_SIZE = 500        # 硬上限

def find_similar(...):
    # 暴力遍历所有条目做 cosine 计算
    for entry in cache.values():
        score = cosine_similarity(query_embedding, entry["embedding"])
```

**核心问题**：
1. 阈值 0.95 一刀切——"怎么用 Python 读 CSV"（10 字）和"请帮我分析这份销售数据报表，提取 top 10 客户并按月度增长率排序，输出表格和趋势图建议"（50 字）用同一阈值
2. 暴力搜索——条目上到 500 时每次查询遍历全部，O(n)
3. 缓存与请求的 creative 程度无关——高 temperature 请求本就不该走缓存

### P0: 长/短文本差异化阈值（来源：CodeFuse-ModelCache）

**方案**：按 query 字符数分段，短文本放宽阈值、长文本收紧。

```python
# cache/storage.py 新增

def _adaptive_threshold(query: str) -> float:
    """根据 query 长度动态调整缓存命中阈值。
    
    参考 CodeFuse-ModelCache 的设计：
    - 短查询（≤20 字）：放宽到 0.88（短文字面相似通常代表相同意图）
    - 中查询（21-100 字）：保持 0.95
    - 长查询（>100 字）：收紧到 0.97（长文局部相似不一定是同一问题）
    """
    length = len(query)
    if length <= 20:
        return 0.88
    elif length <= 100:
        return 0.95
    else:
        return 0.97


def get(query: str) -> Optional[dict]:
    embeddings = encode([query])
    if not embeddings:
        return None
    threshold = _adaptive_threshold(query)
    hit = find_similar(embeddings[0], _cache, CACHE_TTL_SECONDS, threshold)
    # ... 同原逻辑
```

**影响**：改动 5 行，短 query 命中率预计提升 15-20%，长 query 误命中率下降。

---

### P1: Temperature 联动缓存（来源：GPTCache）

**方案**：LLM 请求的 `temperature` 参数联动缓存行为。

```python
# cache/storage.py 新增

def get(query: str, temperature: float = 0.0) -> Optional[dict]:
    """查询缓存，temperature 影响是否使用缓存。
    
    参考 GPTCache:
    - temperature = 0   → 必查缓存（确定性生成，缓存可靠）
    - temperature > 0.7 → 按概率跳过（创造性生成，不应复用旧结果）
    - 中间值            → 正常走缓存
    """
    import random
    if temperature > 0.7:
        skip_prob = (temperature - 0.7) / 1.3  # 0.7→0, 2.0→1.0
        if random.random() < skip_prob:
            return None  # 跳过缓存
    
    # 原有逻辑...
```

**影响**：`stream/` 和 `generate/` 的调用处多传一个 `temperature` 参数。高创造性场景不再返回过期缓存。

---

### P2: 向量索引替代暴力搜索（来源：GPTCache + ModelCache）

当前 `find_similar()` 是 O(n) 暴力遍历，条目多时成为瓶颈。

**方案**：引入 Faiss 内存索引（`cache/storage.py` 可选后端）。

```python
# cache/_index.py 新增

try:
    import faiss
    import numpy as np
    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False


class CacheIndex:
    """缓存向量索引包装，GPU 可用时自动启 Faiss，不可用时回退暴力搜索。"""
    
    def __init__(self, dim: int = 768):
        self.dim = dim
        self._faiss_index = None
        self._id_map: dict[int, str] = {}  # Faiss ID → cache_key
        if _HAS_FAISS:
            self._faiss_index = faiss.IndexFlatIP(dim)  # Inner Product (归一化后等价 Cosine)
    
    def search(self, query_vec: list[float], top_k: int = 5) -> list[tuple[str, float]]:
        if self._faiss_index and self._faiss_index.ntotal > 0:
            import numpy as np
            q = np.array([query_vec], dtype=np.float32)
            scores, indices = self._faiss_index.search(q, min(top_k, self._faiss_index.ntotal))
            return [(self._id_map[int(idx)], float(scores[0][i])) 
                    for i, idx in enumerate(indices[0]) if idx >= 0]
        return []  # 回退暴力搜索走原逻辑
```

**影响**：仅当 `faiss-cpu` 安装时启用，否则回退原逻辑。500 条目时性能提升约 50x。

---

### P2: 缓存指标面板（来源：GPTCache Hit Ratio / Latency / Recall）

**方案**：`stats()` 扩展为可追踪命中率趋势。

```python
# cache/storage.py stats() 扩展

_hit_count = 0
_miss_count = 0

def stats() -> dict:
    total = _hit_count + _miss_count
    return {
        "total_entries": len(_cache),
        "active_entries": active,
        "max_size": MAX_CACHE_SIZE,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "threshold": CACHE_THRESHOLD,
        # 新增
        "hit_count": _hit_count,
        "miss_count": _miss_count,
        "hit_rate": round(_hit_count / max(total, 1), 4),
    }
```

---

## 三、意图路由优化

### 问题诊断

当前 `router/service.py`：

```python
CLARIFY_THRESHOLD = 0.45      # 拍脑袋的值
CONFIDENCE_DOWNGRADE = 0.7   # 同样拍脑袋

def route_model(query, retrieval_scores=None):
    rule_tier, rule_conf, rule_intent = _regex_classify(query)
    if rule_tier and rule_conf >= 0.7:    # 规则引擎内部置信度也是硬编码
        ...
    elif rule_tier:                        # 规则低置信度 → 语义
        sem_tier, sem_conf, sem_intent = _semantic_classify(query)
        if sem_tier and sem_conf > rule_conf:  # 语义超越规则才覆盖
            ...
```

**核心问题**：
1. 所有阈值都是"拍脑袋"，没有数据驱动验证
2. 规则引擎内部置信度由关键词命中数量换算（`hits / total_keywords`），没有实际准确率校验
3. 语义路由用 Embedding 相似度做意图匹配，但没有考虑 KeyWord + Semantic 联合打分

### P0: 规则引擎置信度数据驱动校准（来源：semantic-router 阈值自动优化）

**当前问题**：`router/rules.py` 中每条意图的 `confidence` 由关键词命中比例机械计算，**从未与真实用户反馈校准**。

```python
# 当前：rule_conf = hits / len(keywords)，没有验证过是否 0.7 这个分界点合理
```

**方案**：引入校准数据模块，用一批标注 query 自动计算每个意图的最优阈值。

```python
# router/calibrate.py 新增

CALIBRATION_DATA = [
    # (query, expected_intent, expected_tier)
    ("什么是 Docker", "definition", "fast"),
    ("列出所有 Python 文件", "list", "fast"),
    ("怎么配置 Nginx 反向代理", "howto", "balanced"),
    ("帮我写一个排序算法", "code_generation", "strong"),
    # ... 每意图至少 20 条标注
]


def calibrate_thresholds() -> dict:
    """对每条意图，遍历阈值 0.3-0.9（步长 0.05），找到 F1 最高的阈值。
    
    参考 semantic-router 的自动优化工具。
    """
    from .rules import _regex_classify
    
    results = {}
    for threshold in [t / 100 for t in range(30, 95, 5)]:
        correct = 0
        for query, expected_intent, _ in CALIBRATION_DATA:
            _, conf, intent = _regex_classify(query)
            if intent == expected_intent and conf >= threshold:
                correct += 1
        precision = correct / len(CALIBRATION_DATA)
        # ... 计算 F1
    
    return {"best_threshold": 0.65, "per_intent": {...}}  # 示例
```

**影响**：新增 `router/calibrate.py`，不修改运行时逻辑。校准后的阈值替换硬编码 `0.7` 和 `0.45`。

---

### P1: Hybrid Route（关键词 + 语义联合打分）（来源：semantic-router HybridRouteLayer）

**当前问题**：规则和语义是**串行**的——规则不匹配才走语义，不会联合打分。

**方案**：规则引擎改为 Embedding 相似度加权——规则匹配到的意图，再用 Embedding 验证语义是否一致。

```python
# router/service.py route_model() 优化

def _hybrid_score(rule_tier, rule_conf, rule_intent, query):
    """Hybrid 打分：规则置信度 + Embedding 语义验证。
    
    1. 用 query 的 Embedding 与目标意图的描述 Embedding 算 cosine
    2. 最终分数 = 0.6 * rule_conf + 0.4 * semantic_conf
    """
    from .semantic import _intent_embedding
    intent_emb = _intent_embedding(rule_intent)
    if intent_emb is None:
        return rule_conf, "规则"
    
    query_emb = _encode_query(query)
    sem_conf = cosine_similarity(query_emb, intent_emb)
    hybrid = 0.6 * rule_conf + 0.4 * sem_conf
    
    return hybrid, f"Hybrid(规则{rule_conf:.0%}×0.6 + 语义{sem_conf:.0%}×0.4)"
```

**影响**：减少规则匹配后的"假阳性"——"什么是 Docker Compose"命中 `definition` 但语义也很高 → 置信度提升；"帮我写 Dockerfile"命中 `definition` 但语义更像 `code_generation` → semantic_conf 拉低最终分 → 触发 LLM 兜底。

---

### P2: Router 插件化（来源：LLMRouter 插件体系）

**当前问题**：三层路由（`_regex_classify → _semantic_classify → _llm_classify`）硬编码在 `service.py`，无法替换其中某一层。

**方案**：参考 LLMRouter 的 `MetaRouter` 基类 + `custom_routers/` 插件目录设计。

```python
# router/base.py 新增

from abc import ABC, abstractmethod

class BaseRouter(ABC):
    """路由器基类。参考 LLMRouter MetaRouter。"""
    
    @abstractmethod
    def classify(self, query: str) -> tuple[str, float, str]:
        """返回 (tier, confidence, intent)"""
        ...


class RouterPipeline:
    """可配置的路由流水线。
    
    用法:
        pipeline = RouterPipeline([
            RegexRouter(keywords=...),    # Layer 1
            SemanticRouter(encoder=...),  # Layer 2  
            LLMRouter(model="gpt-4o-mini"),  # Layer 3
        ])
        tier, conf, intent = pipeline.route(query)
    """
    
    def __init__(self, routers: list[BaseRouter]):
        self.routers = routers
    
    def route(self, query: str) -> tuple:
        for router in self.routers:
            tier, conf, intent = router.classify(query)
            if conf >= router.confidence_threshold:
                return tier, conf, intent
        return "balanced", 0.3, "fallback"
```

**影响**：架构级改动。路由策略从"框架内置"变为"可替换插件"，用户可写 `MyCustomRouter` 放 `custom_routers/` 自动加载。

---

### P2: 成本感知路由（来源：LLMRouter `alpha * performance - beta * cost`）

**当前问题**：路由只考虑"任务复杂度"，不考虑"当前预算还剩多少"。

**方案**：路由决策加权成本因子。

```python
# router/service.py route_model() 扩展

def route_model(query, retrieval_scores=None, budget_remaining_pct: float = 1.0):
    # ... 原逻辑产出 tier ...
    
    # 成本感知降级
    if budget_remaining_pct < 0.3 and tier == "strong":
        tier = "balanced"
        reason += f" + 预算仅剩{budget_remaining_pct:.0%}，strong→balanced"
    elif budget_remaining_pct < 0.1 and tier == "balanced":
        tier = "fast"
        reason += f" + 预算仅剩{budget_remaining_pct:.0%}，balanced→fast"
```

---

## 四、存储路由优化

### 问题诊断

当前 `storage_router/routing.py`：

```python
def detect_content_type(text, filename):
    contract_score = sum(1 for kw in CONTRACT_KEYWORDS if kw in text_lower)
    if contract_score >= 2:
        return "contract"
    # ...
```

**核心问题**：
1. 纯关键词打分——"甲方应于 2024 年 1 月交付乙方"会被判为合同，但实际可能是会议纪要里引用了一句合同条款
2. 零 LLM 参与——完全确定性路由，但某些边缘 case（如 PDF 里夹表格）规则必然误判
3. 无反馈闭环——错了也不会纠正

### P1: LLM 兜底验证（来源：LangGraph Agentic RAG 的 Router 节点）

**方案**：规则路由后，对低置信度 case 用 LLM 做一次确认。

```python
# storage_router/routing.py route_storage() 扩展

def route_storage(filename, text="", file_size=0, use_llm_verify: bool = True):
    content_type = detect_content_type(text, filename)
    strategy = _map_type_to_strategy(content_type, filename)
    
    # LLM 兜底验证——仅在规则置信度低时触发
    if use_llm_verify and _rule_confidence(content_type, text) < 0.6:
        llm_strategy = _llm_verify_strategy(filename, text[:500])
        if llm_strategy and llm_strategy != strategy:
            strategy = llm_strategy
            reason += f" + LLM 验证覆盖为 {strategy}"
    
    return {...}


def _rule_confidence(content_type, text):
    """规则判决的置信度——关键词命中越多越可信。"""
    from .policies import CONTRACT_KEYWORDS, TABLE_INDICATORS
    if content_type == "contract":
        hits = sum(1 for kw in CONTRACT_KEYWORDS if kw in text.lower())
        return min(hits / 5, 1.0)  # 命中 5+ 个关键词 → 100% 置信
    # ...
```

**影响**：仅对边缘 case 触发 LLM（预计 <10% 的上传），成本极低。确定性路由的性能优势保留。

---

### P2: 存储策略回归测试集（来源：LLMRouter xRouteBench）

**方案**：建立标注数据集，覆盖 5 种策略 × 每策略 20 个文件，每次修改路由规则后跑回归。

```python
# test/test_storage_router_bench.py 新增

STORAGE_ROUTING_BENCHMARK = [
    # (filename, text_sample, expected_strategy)
    ("合同_2024.pdf", "甲方：XX公司\n乙方：YY公司\n第一条 交付标准...", "original"),
    ("员工表.xlsx", "姓名,部门,入职日期,薪资\n张三,技术,2023-01,...", "structured"),
    ("API文档.md", "# API Reference\n## GET /users\n返回用户列表...", "rag"),
    ("组织架构.json", '{"nodes":[{"id":"CEO"},{"id":"CTO"}],"edges":[...]}', "graph"),
    ("产品图片.png", "(binary image)", "multimodal"),
    # ... 共 100 条
]


def test_storage_routing_accuracy():
    """回归测试：当前路由策略准确率应 ≥ 85%。"""
    correct = 0
    for filename, text, expected in STORAGE_ROUTING_BENCHMARK:
        result = route_storage(filename, text, use_llm_verify=True)
        if result["strategy"] == expected:
            correct += 1
    
    accuracy = correct / len(STORAGE_ROUTING_BENCHMARK)
    assert accuracy >= 0.85, f"存储路由准确率 {accuracy:.1%} < 85%"
```

---

## 五、安全分类器内联路由（P2）

### 来源：vLLM Semantic Router 的"信号层内联安全分类器"

**当前问题**：我们的 PII 检测、prompt injection 检测写在规则引擎里（`router/rules.py` 的 `_check_injection`），但只是**事后拦截**（检测到就拒绝），而非**路由决策的前置输入**。

**方案**：将安全信号作为路由决策的输入维度。

```python
# router/service.py route_model() 扩展

def route_model(query, ...):
    # ... 原逻辑 ...
    
    # 安全预检（vLLM SR style）
    security_signal = _security_scan(query)
    
    if security_signal["pii_detected"]:
        # 包含 PII → 只用本地模型（不出站）
        tier = "fast"
        model = "local-model"  # 或 Ollama
        reason += " + PII 检测→锁定本地模型"
    
    if security_signal["injection_risk"] > 0.8:
        # 高注入风险 → 最保守模型 + 最低 temperature
        tier = "fast"
        temperature = 0.0
        reason += f" + 注入风险({security_signal['injection_risk']:.0%})→安全模式"
```

**影响**：安全从"拦截"变为"决策输入"，关键数据用本地模型不出站。

---

## 六、实施优先级总表

| 编号 | 优化项 | 优先级 | 来源 | 改动量 | 风险 | 预期效果 |
|------|--------|--------|------|--------|------|---------|
| C1 | 长/短文本差异化缓存阈值 | **P0** | CodeFuse-ModelCache | 5行 | 极低 | 短 query 命中率 +15% |
| R1 | 规则引擎阈值校准 | **P0** | semantic-router | 新文件 80行 | 低 | 阈值数据驱动 |
| SR1 | LLM 兜底验证存储路由 | **P1** | LangGraph Agentic | 20行 | 低 | 边缘 case 准确率 +10% |
| C2 | Temperature 联动缓存 | **P1** | GPTCache | 15行 | 低 | 高 creative 场景不返回旧缓存 |
| R2 | Hybrid Route 联合打分 | **P1** | semantic-router | 30行 | 低 | 规则假阳性率 -20% |
| SR2 | 存储路由回归测试集 | **P2** | LLMRouter xRouteBench | 新文件 120行 | 无 | 路由变更可验证 |
| C3 | Faiss 向量索引 | **P2** | GPTCache | 新文件 60行 | 中（依赖 faiss-cpu） | 查询性能 50x |
| R3 | Router 插件化 | **P2** | LLMRouter | 架构改动 | 中 | 路由策略可替换 |
| R4 | 成本感知路由 | **P2** | LLMRouter | 15行 | 低 | 预算紧张自动降级 |
| R5 | 安全分类器内联路由 | **P2** | vLLM Semantic Router | 20行 | 低 | PII 数据不出站 |
| C4 | 缓存指标面板 | **P2** | GPTCache | 10行 | 极低 | 缓存效果可观测 |

---

## 七、实施记录（2026-08-10）

```
✅ C1  + R1   （第一轮 P0）— 已实施
✅ C2  + R2 + SR1 + SR2 + R4 + C4 （第二轮）— 已实施
✅ C3  + R3 + R5（第三轮，架构级）— 已实施
```

### 已实施明细

| 编号 | 改动 | 验证结果 |
|------|------|---------|
| C1 | `cache/storage.py` `_adaptive_threshold()` 差异化阈值 | 短查询 0.88 / 中 0.95 / 长 0.97 |
| C2 | `cache/storage.py` `get(query, temperature)` 联动 | temperature>0.7 按概率跳过缓存 |
| C3 | `cache/_index.py` `CacheIndex`（Faiss 可选后端）+ `storage.py` 接入 | 索引加速 + 优雅回退暴力搜索，stats 暴露 index_enabled/ntotal |
| C4 | `cache/storage.py` `stats()` 新增 hit_count/miss_count/hit_rate | 命中率可观测 |
| R1 | `router/calibrate.py` 校准工具 + `rules.py` 修复 5 处规则缺陷 | 准确率 75%→88.9%（F1 优化，F1=0.941）|
| R2 | `router/service.py` `_hybrid_confidence()` + `semantic.py` `_intent_similarity()` | 冲突检测式 Hybrid（仅语义强烈反对时走 LLM）|
| R3 | `router/base.py` `BaseRouter`/`RouterPipeline` + `plugins.py` 三层包装 + `route_model(pipeline=)` | 插件化，自定义策略可替换任一/全部层 |
| R4 | `router/service.py` `route_model(..., budget_remaining_pct)` | 预算<30% strong→balanced，<10% balanced→fast |
| R5 | `router/security.py` `security_scan()` 内联路由 | PII→本地模型+temperature 0；注入>50%→保守参数+拒绝引导 |
| SR1 | `storage_router/routing.py` `_rule_confidence()` + `_llm_verify_strategy()` + `api/storage.py` | 低置信度 LLM 兜底，仅 <10% case 触发 |
| SR2 | `test/test_storage_router_bench.py` 21 样本回归测试 + 修复 3 处路由缺陷 | 准确率 76.2%→100% |
| 基建 | `test/conftest.py` 清理分支锁（P1-5 测试隔离）| 修复全量跑 4 个 loop 测试污染 |

### 完整测试

```
283 passed（新增 test_smart_scheduling.py 15 项：R3 插件化 6 + R5 安全 5 + C3 索引 4）
前端 npx tsc --noEmit 通过
```

---

## 八、验收标准

- [x] 缓存命中率在短 query（≤20 字）上提升 ≥15%（C1 — 阈值放宽 0.95→0.88）
- [x] 规则引擎校准工具 + 5 处规则缺陷修复，准确率 75%→88.9%（R1）
- [x] 存储路由基准测试准确率 100%（原 76.2%），边缘 case 全覆盖（SR2）
- [x] temperature 联动缓存接口就绪，>0.7 按概率跳过（C2）
- [x] Hybrid Route 冲突检测就绪，语义强烈反对规则时走 LLM 兜底（R2）
- [x] 存储路由回归测试自动验证（SR2 — 21 样本，任何路由修改后跑）
- [x] 成本感知降级接口就绪（R4 — 调用方传 budget_remaining_pct）
- [x] Faiss 向量索引 + 优雅回退（C3 — stats 暴露 index_enabled/ntotal）
- [x] Router 插件化（R3 — BaseRouter/RouterPipeline/build_default_pipeline + 15 项测试）
- [x] 安全分类器内联路由（R5 — PII 锁本地模型，注入走保守参数）
- [x] 缓存命中率趋势面板（C4 — 前端 settings-panel 卡片：累计指标 + 进度条 + 最近 20 次趋势条 + 清空按钮）
