"""Pytest configuration, shared fixtures, and testing harness for approval agent."""

import gc
import os
import tempfile
from collections.abc import Generator
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_approval_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import Settings, get_settings
from app.database import (
    SqliteCheckpointer,
    create_approval_record_sync,
    init_db_sync,
)
from app.main import app
from app.routers.approvals import get_agent_graph


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create an isolated temporary SQLite database file with WAL mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    # Initialize tables, WAL pragmas, and FTS5 triggers
    init_db_sync(path)

    yield path

    # Garbage collection to release file locks on Windows
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
    """Provide an instance of the deterministic mock LLM."""
    return DeterministicMockLLM()


@pytest.fixture
def checkpointer(temp_db: str) -> SqliteCheckpointer:
    """Provide a LangGraph SQLite checkpointer bound to the temp DB."""
    return SqliteCheckpointer(temp_db)


@pytest.fixture
def agent_graph(checkpointer: SqliteCheckpointer):
    """Provide a compiled LangGraph agent graph bound to the test checkpointer."""
    return create_approval_graph(checkpointer=checkpointer)


@pytest.fixture
def sample_pending_request(temp_db: str) -> dict[str, Any]:
    """Seed a sample high-risk approval request in pending state."""
    return create_approval_record_sync(
        thread_id="thread_test_pending_01",
        action_type="drop_table",
        risk_level="CRITICAL",
        description="Drop legacy customer session table in production",
        payload={"table": "customer_sessions", "cascade": True},
        status="pending_approval",
        request_id="req_test_pending_01",
        db_path=temp_db,
    )


@pytest.fixture
def sample_completed_request(temp_db: str) -> dict[str, Any]:
    """Seed a sample low-risk completed request."""
    return create_approval_record_sync(
        thread_id="thread_test_completed_01",
        action_type="query_database",
        risk_level="LOW",
        description="Fetch count of active tenants",
        payload={"query": "SELECT count(*) FROM tenants"},
        status="completed",
        request_id="req_test_completed_01",
        decision="approve",
        decision_by="system",
        decision_reason="Auto-approved low risk query",
        result="Successfully retrieved data from tenants matching 'all'. Returned 3 simulated records. (Auto-approved)",
        execution_logs=["Action 'query_database' assessed as LOW risk. Auto-approved."],
        db_path=temp_db,
    )


@pytest.fixture
def test_client(temp_db: str, agent_graph, checkpointer: SqliteCheckpointer) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured with isolated temp DB and agent graph."""
    def get_test_settings() -> Settings:
        return Settings(
            database_path=temp_db,
            environment="testing",
            log_level="DEBUG",
            api_prefix="/api/v1",
            default_timeout=30,
        )

    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_agent_graph] = lambda: agent_graph
    app.state.graph = agent_graph
    app.state.checkpointer = checkpointer

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
