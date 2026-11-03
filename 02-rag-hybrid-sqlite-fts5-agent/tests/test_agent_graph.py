"""Tier 2: LangGraph node execution, state transitions, and conditional routing tests."""

from typing import Any
import pytest

from app.agent.graph import run_rag_agent, should_retrieve_or_synthesize
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    decompose_query_node,
    grade_documents_node,
    reformulate_query_node,
    retrieve_fts5_node,
    synthesize_answer_node,
)
from app.agent.state import RAGState


@pytest.mark.graph
class TestLangGraphNodes:
    """Validate individual LangGraph node handlers."""

    def test_decompose_query_compound(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "What is SQLite WAL mode and how do FTS5 triggers work?",
            "enable_decomposition": True,
            "iterations": 0,
        }
        update = decompose_query_node(state, llm=mock_llm)
        assert len(update["subqueries"]) >= 2
        assert any("WAL" in sq for sq in update["subqueries"])
        assert any("FTS5" in sq for sq in update["subqueries"])

    def test_decompose_query_atomic(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "What is Write-Ahead Logging?",
            "enable_decomposition": True,
            "iterations": 0,
        }
        update = decompose_query_node(state, llm=mock_llm)
        assert len(update["subqueries"]) == 1
        assert "Write-Ahead Logging" in update["subqueries"][0]

    def test_decompose_query_disabled(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "What is WAL mode and how do triggers work?",
            "enable_decomposition": False,
            "iterations": 0,
        }
        update = decompose_query_node(state, llm=mock_llm)
        assert len(update["subqueries"]) == 1
        assert update["subqueries"][0] == "What is WAL mode and how do triggers work?"

    def test_retrieve_fts5_node_seeded(
        self, temp_db: str, sample_docs: list[dict[str, Any]]
    ) -> None:
        state: RAGState = {
            "query": "WAL mode",
            "subqueries": ["SQLite WAL mode"],
            "top_k": 3,
            "threshold": 0.0,
            "db_path": temp_db,
        }
        update = retrieve_fts5_node(state)
        docs = update["retrieved_docs"]
        assert len(docs) > 0
        assert docs[0]["id"] == "doc_wal"
        assert "score" in docs[0]
        assert "snippet" in docs[0]

    def test_grade_documents_node_relevant(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "Explain SQLite WAL mode",
            "retrieved_docs": [
                {"title": "SQLite WAL Mode Architecture", "content": "WAL mode provides concurrency."}
            ],
            "threshold": 0.0,
        }
        update = grade_documents_node(state, llm=mock_llm)
        assert update["is_relevant"] is True

    def test_grade_documents_node_irrelevant(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "Quantum computing qubit entanglement",
            "retrieved_docs": [
                {"title": "Docker Setup", "content": "Docker multi-stage builds."}
            ],
            "threshold": 0.0,
        }
        update = grade_documents_node(state, llm=mock_llm)
        assert update["is_relevant"] is False

    def test_grade_documents_node_empty_docs(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "Any query",
            "retrieved_docs": [],
            "threshold": 0.0,
        }
        update = grade_documents_node(state, llm=mock_llm)
        assert update["is_relevant"] is False

    def test_reformulate_query_node(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "How do you configure the SQLite WAL mode in Python?",
            "iterations": 0,
        }
        update = reformulate_query_node(state, llm=mock_llm)
        assert update["iterations"] == 1
        assert len(update["subqueries"]) == 1
        # Conversational stop words removed
        reformulated = update["subqueries"][0]
        assert "configure" in reformulated
        assert "SQLite" in reformulated

    def test_synthesize_answer_node(self, mock_llm: DeterministicMockLLM) -> None:
        state: RAGState = {
            "query": "What are FTS5 triggers?",
            "retrieved_docs": [
                {
                    "id": "doc_fts5",
                    "title": "SQLite FTS5 Triggers and Synchronization",
                    "content": "AFTER INSERT and AFTER DELETE triggers synchronize the FTS5 table.",
                    "snippet": "<b>AFTER INSERT</b> and <b>AFTER DELETE</b> triggers...",
                }
            ],
        }
        update = synthesize_answer_node(state, llm=mock_llm)
        assert "answer" in update
        assert len(update["citations"]) >= 1
        assert "[Doc: SQLite FTS5 Triggers and Synchronization]" in update["citations"]
        assert update["completed"] is True


@pytest.mark.graph
class TestLangGraphRoutingAndExecution:
    """Validate graph routing conditions and complete StateGraph execution."""

    def test_routing_to_synthesize_when_relevant(self) -> None:
        state: RAGState = {"is_relevant": True, "iterations": 0, "max_iterations": 2}
        assert should_retrieve_or_synthesize(state) == "synthesize_answer"

    def test_routing_to_reformulate_when_not_relevant(self) -> None:
        state: RAGState = {"is_relevant": False, "iterations": 0, "max_iterations": 2}
        assert should_retrieve_or_synthesize(state) == "reformulate_query"

    def test_routing_to_synthesize_when_max_iterations_reached(self) -> None:
        state: RAGState = {"is_relevant": False, "iterations": 2, "max_iterations": 2}
        assert should_retrieve_or_synthesize(state) == "synthesize_answer"

    def test_full_rag_workflow_success(
        self, temp_db: str, sample_docs: list[dict[str, Any]]
    ) -> None:
        result = run_rag_agent(
            query="What is SQLite WAL mode?",
            db_path=temp_db,
            top_k=3,
            max_iterations=2,
            enable_decomposition=True,
        )
        assert result["completed"] is True
        assert result["is_relevant"] is True
        assert len(result["retrieved_docs"]) > 0
        assert len(result["citations"]) > 0
        assert "[Doc: SQLite WAL Mode Architecture]" in result["citations"]
        assert "WAL" in result["answer"]

    def test_full_rag_workflow_bounded_loop_on_no_match(
        self, temp_db: str, sample_docs: list[dict[str, Any]]
    ) -> None:
        result = run_rag_agent(
            query="Photosynthesis in Martian atmospheric conditions",
            db_path=temp_db,
            top_k=3,
            max_iterations=2,
            enable_decomposition=False,
        )
        assert result["completed"] is True
        assert result["iterations"] >= 2
        assert "could not find relevant documentation" in result["answer"]
