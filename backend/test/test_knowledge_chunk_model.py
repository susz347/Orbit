import pytest
from pydantic import ValidationError

from app.knowledge_agent.chunk_ids import make_chunk_id
from app.knowledge_agent.models import KnowledgeChunk


def test_chunk_id_is_stable_and_changes_with_locator():
    arguments = {
        "run_id": "run-1",
        "source_hash": "a" * 64,
        "strategy_id": "markdown_hierarchical_v1",
        "chunk_index": 0,
        "locator": "heading:Support",
    }

    first = make_chunk_id(**arguments)

    assert first == make_chunk_id(**arguments)
    assert first != make_chunk_id(
        **{**arguments, "locator": "heading:Deletion"}
    )


def test_knowledge_chunk_rejects_empty_text():
    with pytest.raises(ValidationError):
        KnowledgeChunk(
            chunk_id="kc_123",
            text="",
            run_id="run-1",
            source_path="policy.md",
            source_hash="a" * 64,
            strategy_id="markdown_hierarchical_v1",
            chunk_index=0,
        )
