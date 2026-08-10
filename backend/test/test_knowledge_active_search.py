from app import search as search_module
from app import cache as cache_module
from app.knowledge_agent.releases import ActiveIndexVersion


class FakeCollection:
    def __init__(self):
        self.name = None

    def count(self):
        return 1

    def query(self, **kwargs):
        return {
            "ids": [["chunk-1"]],
            "documents": [["support target is four hours"]],
            "metadatas": [[{"source_path": "clean-policy.md"}]],
            "distances": [[0.1]],
        }


def test_search_uses_resolved_active_collection(monkeypatch):
    collection = FakeCollection()
    requested = []
    monkeypatch.setattr(
        search_module,
        "get_active_index",
        lambda **kwargs: ActiveIndexVersion(
            run_id="run-1", collection_name="kr_active", generation=2,
            legacy=False,
        ),
    )
    monkeypatch.setattr(
        search_module,
        "get_collection_by_name",
        lambda name: requested.append(name) or collection,
    )
    monkeypatch.setattr(search_module, "encode", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr(search_module, "_knowledge_database_path", lambda: object())

    results = search_module.search("support target", user_id=7)

    assert requested == ["kr_active"]
    assert results[0]["metadata"]["source_path"] == "clean-policy.md"
    assert "clean-policy.md" in search_module.search_formatted(
        "support target", user_id=7
    )


def test_search_preserves_legacy_collection_fallback(monkeypatch):
    requested = []
    monkeypatch.setattr(
        search_module,
        "get_active_index",
        lambda **kwargs: ActiveIndexVersion(
            run_id=None, collection_name="user_7", generation=0, legacy=True,
        ),
    )
    monkeypatch.setattr(
        search_module,
        "get_collection_by_name",
        lambda name: requested.append(name) or FakeCollection(),
    )
    monkeypatch.setattr(search_module, "encode", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr(search_module, "_knowledge_database_path", lambda: object())

    search_module.search("legacy", user_id=7)

    assert requested == ["user_7"]


def test_semantic_answer_cache_is_partitioned_by_active_collection(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, "encode", lambda texts: [[1.0, 0.0]])
    cache_module.put(
        "same question", "old answer", [], "test", namespace="7:kr_old"
    )

    assert cache_module.get("same question", namespace="7:kr_new") is None
    assert cache_module.get("same question", namespace="7:kr_old")["answer"] == "old answer"
