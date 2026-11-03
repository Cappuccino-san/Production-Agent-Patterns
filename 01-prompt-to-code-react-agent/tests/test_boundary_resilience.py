"""Tier 5: Boundary Conditions, Malformed Inputs, Concurrency, and Error Resilience Tests."""

import asyncio
import pytest
from fastapi.testclient import TestClient

from app.agent.nodes import execute_tool_node, validate_ast_node
from app.agent.state import AgentState
from app.database import save_run, search_runs


@pytest.mark.boundary
def test_extremely_large_prompt_resilience(test_client: TestClient) -> None:
    """Verify system handles long prompt payloads without crashing."""
    large_prompt = "Write a data pipeline function " + ("and validate fields " * 200)
    response = test_client.post("/api/v1/agent/run", json={"prompt": large_prompt})
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["status"] == "completed"


@pytest.mark.boundary
@pytest.mark.asyncio
async def test_sql_injection_resilience_in_fts5_search(temp_db: str) -> None:
    """Verify search endpoint sanitizes hostile SQL injection and special characters."""
    hostile_queries = [
        "'; DROP TABLE runs; --",
        "' OR '1'='1",
        "***???)))(((",
        "UNION SELECT * FROM sqlite_master",
        '"""""',
        "   ",
    ]
    for q in hostile_queries:
        # Should not raise exception or execute arbitrary SQL
        results = await search_runs(query=q, limit=10, db_path=temp_db)
        assert isinstance(results, list)


@pytest.mark.boundary
def test_ast_validation_empty_and_corrupt_payloads() -> None:
    """Verify AST validator handles empty and malformed string states."""
    empty_state: AgentState = {
        "prompt": "Test",
        "language": "python",
        "code": "   ",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    # Empty string is valid AST in Python (module with 0 statements), but produces zero statements
    res = validate_ast_node(empty_state)
    assert res["is_valid"] is True


@pytest.mark.boundary
def test_sandbox_runtime_error_resilience() -> None:
    """Verify sandbox isolates code that raises ZeroDivisionError or IndexError."""
    error_state: AgentState = {
        "prompt": "Test division",
        "language": "python",
        "code": "x = 10 / 0",
        "is_valid": True,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    res = execute_tool_node(error_state)
    assert res["output"] is None
    assert "division by zero" in res["error"]


@pytest.mark.boundary
@pytest.mark.asyncio
async def test_concurrent_wal_writes(temp_db: str) -> None:
    """Verify SQLite WAL mode accommodates concurrent writes without database lock contention."""
    async def insert_worker(worker_id: int) -> None:
        for i in range(10):
            record = {
                "id": f"worker_{worker_id}_run_{i}",
                "prompt": f"Concurrent task from worker {worker_id}",
                "language": "python",
                "code": "x = 1",
                "is_valid": True,
                "output": "1",
                "iterations": 1,
                "steps": [],
                "status": "completed",
            }
            await save_run(record, temp_db)

    # Spawn 5 concurrent write tasks (50 total writes)
    tasks = [insert_worker(w) for w in range(5)]
    await asyncio.gather(*tasks)

    # Verify all records saved
    results = await search_runs("Concurrent", limit=100, db_path=temp_db)
    assert len(results) == 50
