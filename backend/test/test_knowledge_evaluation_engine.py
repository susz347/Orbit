import shutil
from pathlib import Path

from app.knowledge_agent.approval import approve_run
from app.knowledge_agent.evaluation import evaluate_run
from app.knowledge_agent.evaluation_repository import get_evaluation_report
from app.knowledge_agent.evaluation_models import (
    RelevantLocator,
    RetrievalEvaluationCase,
    RetrievedChunk,
)
from app.knowledge_agent.pipeline import plan_folder
from app.knowledge_agent.repository import (
    get_run,
    save_execution_result,
    transition_run,
)
from app.knowledge_agent.staging_store import staging_collection_name


SOURCE_FIXTURES = Path(__file__).resolve().parents[2] / "knowledge" / "fixtures"


class StaticEvaluationStore:
    def __init__(self, results, count=1, exists=True):
        self.results = results
        self.vector_count = count
        self.collection_exists = exists
        self.deleted = []

    def exists(self, *, run_id, user_id):
        return self.collection_exists

    def count(self, *, run_id, user_id):
        return self.vector_count

    def query(self, *, run_id, user_id, question, top_k):
        return self.results.get(question, ())


def _context(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    fixtures = knowledge_root / "fixtures"
    shutil.copytree(SOURCE_FIXTURES, fixtures)
    database = tmp_path / "audit.sqlite3"
    plan = plan_folder(
        fixtures,
        knowledge_root=knowledge_root,
        database_path=database,
        user_id=7,
    )
    approve_run(
        plan.run_id,
        knowledge_root=knowledge_root,
        database_path=database,
        user_id=7,
    )
    assert transition_run(
        plan.run_id,
        target="indexing",
        expected="approved",
        database_path=database,
        user_id=7,
    )
    assert save_execution_result(
        plan.run_id,
        staging_collection=staging_collection_name(plan.run_id, 7),
        chunk_count=1,
        vector_store_writes=1,
        execution_error=None,
        completed=True,
        database_path=database,
        user_id=7,
    )
    assert transition_run(
        plan.run_id,
        target="evaluating",
        expected="indexing",
        database_path=database,
        user_id=7,
    )
    case = RetrievalEvaluationCase(
        schema_version="rag-retrieval.v1",
        id="support",
        question="support target",
        expected_answer="four hours",
        relevant_sources=("clean-policy.md",),
        relevant_locators=(RelevantLocator(heading="Support levels"),),
        critical=True,
    )
    hit = RetrievedChunk(
        rank=1,
        distance=0.1,
        chunk_id="kc_hit",
        text="P1 support target is four hours",
        source_path="clean-policy.md",
        heading_path=("Policy", "Support levels"),
        chunk_index=0,
    )
    return plan.run_id, database, case, hit


def test_all_critical_hits_produce_passed_report(tmp_path):
    run_id, database, case, hit = _context(tmp_path)
    store = StaticEvaluationStore({case.question: (hit,)})

    report = evaluate_run(
        run_id,
        database_path=database,
        user_id=7,
        cases=(case,),
        staging_store=store,
    )

    assert report.status == "passed"
    assert report.source_hit_rate_at_5 == 1.0
    assert get_run(run_id, database_path=database, user_id=7).status == "evaluating"
    assert evaluate_run(
        run_id,
        database_path=database,
        user_id=7,
        cases=(case,),
        staging_store=store,
    ).attempt_id == report.attempt_id
    persisted = get_evaluation_report(
        run_id, database_path=database, user_id=7
    )
    assert persisted == report
    assert hit.text.encode("utf-8") not in database.read_bytes()


def test_quality_miss_rejects_run_without_deleting_staging(tmp_path):
    run_id, database, case, _ = _context(tmp_path)
    store = StaticEvaluationStore({case.question: ()})

    report = evaluate_run(
        run_id,
        database_path=database,
        user_id=7,
        cases=(case,),
        staging_store=store,
    )

    assert report.status == "rejected"
    assert get_run(run_id, database_path=database, user_id=7).status == "rejected"
    assert store.deleted == []


def test_vector_count_mismatch_marks_evaluation_failed(tmp_path):
    run_id, database, case, hit = _context(tmp_path)
    store = StaticEvaluationStore({case.question: (hit,)}, count=2)

    report = evaluate_run(
        run_id,
        database_path=database,
        user_id=7,
        cases=(case,),
        staging_store=store,
    )

    assert report.status == "failed"
    assert report.error_category == "evaluation_input_error"
    assert get_run(run_id, database_path=database, user_id=7).status == "failed"
