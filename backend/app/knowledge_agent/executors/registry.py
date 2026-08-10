from app.knowledge_agent.executors.base import StrategyExecutor
from app.knowledge_agent.executors.docx import DocxLayoutAwareExecutor
from app.knowledge_agent.executors.markdown import MarkdownHierarchicalExecutor


def build_executor_registry() -> dict[str, StrategyExecutor]:
    return {
        "markdown_hierarchical_v1": MarkdownHierarchicalExecutor(),
        "docx_layout_aware_v1": DocxLayoutAwareExecutor(),
    }
