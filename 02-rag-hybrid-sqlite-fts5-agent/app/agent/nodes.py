"""Discrete LangGraph node handlers for RAG Hybrid SQLite FTS5 agent."""

from typing import Any, Optional

from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import RAGState
from app.config import get_settings
from app.database import search_documents_sync

_DEFAULT_LLM = DeterministicMockLLM()


def decompose_query_node(
    state: RAGState, llm: Optional[DeterministicMockLLM] = None
) -> dict[str, Any]:
    """Decompose complex, compound questions into atomic subqueries."""
    engine = llm or _DEFAULT_LLM
    query = state.get("query", "").strip()
    enable_decomp = state.get("enable_decomposition", True)

    if not query:
        return {"subqueries": [], "iterations": state.get("iterations", 0)}

    if enable_decomp:
        subqueries = engine.decompose_query(query)
        if not subqueries:
            subqueries = [query]
    else:
        subqueries = [query]

    return {
        "subqueries": subqueries,
        "iterations": state.get("iterations", 0),
    }


def retrieve_fts5_node(state: RAGState) -> dict[str, Any]:
    """Execute SQLite FTS5 BM25 search across all decomposed subqueries."""
    subqueries = state.get("subqueries") or ([state.get("query")] if state.get("query") else [])
    top_k = state.get("top_k") or get_settings().default_top_k
    threshold = state.get("threshold", 0.0)
    db_path = state.get("db_path") or get_settings().database_path

    combined_results: dict[str, dict[str, Any]] = {}

    for subq in subqueries:
        if not subq or not subq.strip():
            continue
        hits = search_documents_sync(
            query=subq,
            limit=top_k,
            threshold=threshold,
            db_path=db_path,
        )
        for hit in hits:
            doc_id = hit["id"]
            if doc_id not in combined_results or hit["score"] < combined_results[doc_id]["score"]:
                combined_results[doc_id] = hit

    # Sort deduplicated documents by BM25 rank score (ascending: best matches first)
    sorted_docs = sorted(combined_results.values(), key=lambda d: d.get("score", 0.0))
    top_docs = sorted_docs[:top_k]

    return {"retrieved_docs": top_docs}


def grade_documents_node(
    state: RAGState, llm: Optional[DeterministicMockLLM] = None
) -> dict[str, Any]:
    """Grade whether the retrieved document chunks are relevant to the query."""
    engine = llm or _DEFAULT_LLM
    query = state.get("query", "")
    documents = state.get("retrieved_docs", [])
    threshold = state.get("threshold", 0.0)

    is_relevant = engine.grade_relevance(query, documents, threshold=threshold)
    return {"is_relevant": is_relevant}


def reformulate_query_node(
    state: RAGState, llm: Optional[DeterministicMockLLM] = None
) -> dict[str, Any]:
    """Reformulate the query when initial retrieval yields insufficient relevance."""
    engine = llm or _DEFAULT_LLM
    query = state.get("query", "")
    current_iter = state.get("iterations", 0) + 1

    reformulated = engine.reformulate_query(query, current_iter)
    return {
        "subqueries": [reformulated],
        "iterations": current_iter,
    }


def synthesize_answer_node(
    state: RAGState, llm: Optional[DeterministicMockLLM] = None
) -> dict[str, Any]:
    """Synthesize final grounded answer with verifiable document citations."""
    engine = llm or _DEFAULT_LLM
    query = state.get("query", "")
    is_relevant = state.get("is_relevant", True)
    documents = state.get("retrieved_docs", []) if is_relevant else []

    answer, citations = engine.synthesize_answer(query, documents)
    return {
        "answer": answer,
        "citations": citations,
        "completed": True,
    }
