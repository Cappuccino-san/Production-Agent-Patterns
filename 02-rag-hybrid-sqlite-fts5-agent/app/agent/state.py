"""LangGraph TypedDict state schema for RAG Hybrid SQLite FTS5 agent."""

from typing import Any, Optional
from typing_extensions import TypedDict


class RAGState(TypedDict, total=False):
    """Strongly-typed execution state for RAG workflow graph.
    
    Attributes:
        query: Original input user question.
        subqueries: List of decomposed search queries.
        retrieved_docs: List of documents retrieved from SQLite FTS5.
        is_relevant: Evaluation flag indicating whether retrieved docs satisfy query.
        answer: Synthesized final answer string.
        citations: List of source document citations.
        iterations: Number of query reformulation cycles executed.
        completed: Flag marking workflow completion.
        top_k: Number of documents to retrieve per subquery.
        threshold: Score threshold for relevance.
        max_iterations: Limit on query reformulation iterations.
        enable_decomposition: Flag to enable query decomposition.
        db_path: Target SQLite database file path.
        error: Optional error description if any stage failed.
    """

    query: str
    subqueries: list[str]
    retrieved_docs: list[dict[str, Any]]
    is_relevant: bool
    answer: str
    citations: list[str]
    iterations: int
    completed: bool
    top_k: int
    threshold: float
    max_iterations: int
    enable_decomposition: bool
    db_path: str
    error: Optional[str]
