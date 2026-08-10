from app.knowledge_agent.staging_store import StagingStore, staging_collection_name


class QueryCollection:
    def count(self):
        return 2

    def query(self, **kwargs):
        assert kwargs["n_results"] == 2
        return {
            "ids": [["kc_first", "kc_second"]],
            "documents": [["first", "second"]],
            "metadatas": [[
                {
                    "source_path": "clean-policy.md",
                    "heading_path": '["Policy", "Support levels"]',
                    "chunk_index": 0,
                },
                {
                    "source_path": "clean-projects.xlsx",
                    "heading_path": "[]",
                    "sheet": "Projects",
                    "row_number": 2,
                    "chunk_index": 1,
                },
            ]],
            "distances": [[0.1, 0.2]],
        }


class QueryClient:
    def __init__(self):
        self.requested = []
        self.collection = QueryCollection()

    def get_or_create_collection(self, *, name, metadata=None):
        self.requested.append(name)
        return self.collection

    def list_collections(self):
        return [type("CollectionName", (), {"name": "kr_exists"})()]


def test_query_restores_rank_and_source_locators():
    client = QueryClient()
    store = StagingStore(client=client, encoder=lambda texts: [[0.3, 0.4]])

    results = store.query(run_id="run-1", user_id=7, question="support", top_k=5)

    assert client.requested == [staging_collection_name("run-1", 7)]
    assert results[0].rank == 1
    assert results[0].source_path == "clean-policy.md"
    assert results[0].heading_path == ("Policy", "Support levels")
    assert results[1].sheet == "Projects"
    assert results[1].row_number == 2


def test_exists_does_not_create_a_missing_collection():
    client = QueryClient()
    store = StagingStore(client=client, encoder=lambda texts: [[0.3]])

    assert store.exists(run_id="missing", user_id=7) is False
    assert client.requested == []
