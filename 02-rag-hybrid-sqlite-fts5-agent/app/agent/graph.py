"""LangGraph StateGraph compilation and conditional routing for RAG agent."""

from typing import Any, Literal, Optional
from langgraph.graph import END, StateGraph

from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    decompose_query_node,
    grade_documents_node,
    reformulate_query_node,
    retrieve_fts5_node,
    synthesize_answer_node,
)
from app.agent.state import RAGState
from app.config import get_settings


def should_retrieve_or_synthesize(
    state: RAGState,
) -> Literal["reformulate_query", "synthesize_answer"]:
    """Conditional routing edge deciding whether to reformulate or synthesize.
    
    Routes to synthesize_answer if:
    - Retrieved documents are graded as relevant, OR
    - Maximum query reformulation iterations have been reached.
    Otherwise routes to reformulate_query for another retrieval attempt.
    """
    is_relevant = state.get("is_relevant", False)
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 2)

    if is_relevant or iterations >= max_iterations:
        return "synthesize_answer"
    return "reformulate_query"


def create_rag_graph(
    llm: Optional[DeterministicMockLLM] = None,
    checkpointer: Any = None,
) -> Any:
    """Build and compile the RAG Hybrid SQLite FTS5 StateGraph."""
    workflow = StateGraph(RAGState)

    # Bind injectable LLM instance to node functions
    def bound_decompose(state: RAGState) -> dict[str, Any]:
        return decompose_query_node(state, llm=llm)

    def bound_grade(state: RAGState) -> dict[str, Any]:
        return grade_documents_node(state, llm=llm)

    def bound_reformulate(state: RAGState) -> dict[str, Any]:
        return reformulate_query_node(state, llm=llm)

    def bound_synthesize(state: RAGState) -> dict[str, Any]:
        return synthesize_answer_node(state, llm=llm)

    # Register Nodes
    workflow.add_node("decompose_query", bound_decompose)
    workflow.add_node("retrieve_fts5", retrieve_fts5_node)
    workflow.add_node("grade_documents", bound_grade)
    workflow.add_node("reformulate_query", bound_reformulate)
    workflow.add_node("synthesize_answer", bound_synthesize)

    # Set Workflow Entry Point
    workflow.set_entry_point("decompose_query")

    # Connect Edges
    workflow.add_edge("decompose_query", "retrieve_fts5")
    workflow.add_edge("retrieve_fts5", "grade_documents")

    # Conditional Branching after Document Relevance Grading
    workflow.add_conditional_edges(
        "grade_documents",
        should_retrieve_or_synthesize,
        {
            "reformulate_query": "reformulate_query",
            "synthesize_answer": "synthesize_answer",
        },
    )

    workflow.add_edge("reformulate_query", "retrieve_fts5")
    workflow.add_edge("synthesize_answer", END)

    return workflow.compile(checkpointer=checkpointer)


def run_rag_agent(
    query: str,
    db_path: Optional[str] = None,
    top_k: int = 5,
    threshold: float = 0.0,
    max_iterations: int = 2,
    enable_decomposition: bool = True,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Execute complete RAG pipeline synchronously."""
    settings = get_settings()
    initial_state: RAGState = {
        "query": query,
        "subqueries": [],
        "retrieved_docs": [],
        "is_relevant": False,
        "answer": "",
        "citations": [],
        "iterations": 0,
        "completed": False,
        "top_k": top_k,
        "threshold": threshold,
        "max_iterations": max_iterations,
        "enable_decomposition": enable_decomposition,
        "db_path": db_path or settings.database_path,
    }

    graph = create_rag_graph(llm=llm)
    return graph.invoke(initial_state)


async def arun_rag_agent(
    query: str,
    db_path: Optional[str] = None,
    top_k: int = 5,
    threshold: float = 0.0,
    max_iterations: int = 2,
    enable_decomposition: bool = True,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Execute complete RAG pipeline asynchronously."""
    settings = get_settings()
    initial_state: RAGState = {
        "query": query,
        "subqueries": [],
        "retrieved_docs": [],
        "is_relevant": False,
        "answer": "",
        "citations": [],
        "iterations": 0,
        "completed": False,
        "top_k": top_k,
        "threshold": threshold,
        "max_iterations": max_iterations,
        "enable_decomposition": enable_decomposition,
        "db_path": db_path or settings.database_path,
    }

    graph = create_rag_graph(llm=llm)
    return await graph.ainvoke(initial_state)
