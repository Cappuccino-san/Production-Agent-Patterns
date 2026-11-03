"""Pytest fixtures and test environment configuration."""

import gc
import os
import tempfile
from collections.abc import Generator
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.agent.mock_llm import DeterministicMockLLM
from app.config import Settings, get_settings
from app.database import init_db_sync, save_document_sync
from app.main import app


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create an isolated temporary SQLite database file in WAL mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    # Initialize schema, pragmas, and FTS5 triggers
    init_db_sync(path)

    yield path

    # Garbage collect to release open handles on Windows
    gc.collect()

    for ext in ["", "-wal", "-shm"]:
        target = path + ext
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass


@pytest.fixture
def mock_llm() -> DeterministicMockLLM:
    """Provide a deterministic mock LLM instance."""
    return DeterministicMockLLM()


@pytest.fixture
def sample_docs(temp_db: str) -> list[dict[str, Any]]:
    """Seed sample technical documents into the temporary database."""
    docs = [
        {
            "id": "doc_wal",
            "title": "SQLite WAL Mode Architecture",
            "content": (
                "Write-Ahead Logging (WAL) provides massive concurrent read and write throughput in SQLite. "
                "When WAL is enabled with PRAGMA journal_mode = WAL, readers do not block writers and "
                "writers do not block readers. Synchronous NORMAL ensures performance and data durability."
            ),
            "metadata": {"category": "database", "priority": "high"},
        },
        {
            "id": "doc_fts5",
            "title": "SQLite FTS5 Triggers and Synchronization",
            "content": (
                "Full-Text Search 5 (FTS5) external content tables synchronize automatically with the parent table "
                "using AFTER INSERT, AFTER DELETE, and AFTER UPDATE triggers, avoiding data drift and enabling "
                "BM25 ranking and fast snippet generation."
            ),
            "metadata": {"category": "search", "priority": "high"},
        },
        {
            "id": "doc_langgraph",
            "title": "LangGraph StateGraph and Cyclic Workflows",
            "content": (
                "LangGraph provides stateful cyclic graph execution for agentic workflows with TypedDict state, "
                "conditional edges, and query decomposition loops for robust Corrective RAG."
            ),
            "metadata": {"category": "agent", "priority": "medium"},
        },
        {
            "id": "doc_fastapi",
            "title": "FastAPI Lifespan Context Manager",
            "content": (
                "FastAPI lifespan handlers manage application startup and shutdown events asynchronously "
                "using asynccontextmanager, handling SQLite connections and table initialization gracefully."
            ),
            "metadata": {"category": "backend", "priority": "medium"},
        },
        {
            "id": "doc_docker",
            "title": "Docker Multi-Stage Production Deployment",
            "content": (
                "Docker multi-stage builds ensure minimal image attack surfaces, running unprivileged appuser "
                "with healthchecks on port 8000 for EC2 and container orchestration."
            ),
            "metadata": {"category": "devops", "priority": "low"},
        },
    ]

    for d in docs:
        save_document_sync(d, temp_db)

    return docs


@pytest.fixture
def test_client(temp_db: str) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured with isolated temporary database."""
    def get_test_settings() -> Settings:
        return Settings(
            database_path=temp_db,
            environment="test",
            log_level="DEBUG",
            default_top_k=5,
            relevance_threshold=0.0,
            max_iterations=2,
            enable_query_decomposition=True,
        )

    app.dependency_overrides[get_settings] = get_test_settings

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
