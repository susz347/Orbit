"""api/performance.py — 性能接口测试 /api/v1/knowledge/cache/*, /api/v1/knowledge/router/*"""
from app.router import MODEL_PRESETS


def test_cache_stats(client):
    r = client.get("/api/v1/knowledge/cache/stats")
    assert r.status_code == 200
    data = r.json()
    # C4: 新增命中率指标 hit_count / miss_count / hit_rate / history
    # C3: 新增索引状态 index_enabled / index_ntotal
    assert set(data.keys()) == {
        "total_entries", "active_entries", "max_size", "ttl_seconds", "threshold",
        "hit_count", "miss_count", "hit_rate",
        "index_enabled", "index_ntotal",
        "history",
    }
    assert data["hit_rate"] >= 0  # 未命中时 hit_rate=0
    assert data["hit_rate"] <= 1
    assert data["index_enabled"] in (True, False)
    assert isinstance(data["history"], list)
    assert len(data["history"]) <= 20  # 趋势采样上限


def test_cache_clear(client):
    r = client.delete("/api/v1/knowledge/cache")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert client.get("/api/v1/knowledge/cache/stats").json()["total_entries"] == 0


def test_router_models(client):
    r = client.get("/api/v1/knowledge/router/models")
    assert r.status_code == 200
    assert r.json() == MODEL_PRESETS


def test_router_predict_simple(client):
    r = client.post("/api/v1/knowledge/router/predict", json={"query": "什么是向量数据库？"})
    assert r.status_code == 200
    data = r.json()
    assert data["intent"] == "simple"
    assert data["tier"] == "fast"
    assert data["model"] == MODEL_PRESETS["fast"]["model"]
    assert "规则匹配" in data["reason"]


def test_router_predict_complex(client):
    r = client.post("/api/v1/knowledge/router/predict", json={"query": "帮我写一个排序算法"})
    data = r.json()
    assert data["intent"] == "complex"
    assert data["tier"] == "strong"


def test_router_predict_out_of_scope(client):
    r = client.post("/api/v1/knowledge/router/predict", json={"query": "今天天气怎么样"})
    data = r.json()
    assert data["tier"] == "out_of_scope"
    assert data["needs_clarification"] is True
    assert data["clarification_question"]


def test_router_predict_empty_query(client):
    r = client.post("/api/v1/knowledge/router/predict", json={"query": ""})
    assert r.status_code == 400
