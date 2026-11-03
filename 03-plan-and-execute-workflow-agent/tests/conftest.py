"""Pytest fixtures and test environment harness."""

import gc
import os
import tempfile
from collections.abc import Generator
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.agent.mock_llm import DeterministicMockLLM
from app.config import Settings, get_settings
from app.database import create_plan_sync, init_db_sync, update_plan_status_sync, update_step_sync
from app.main import app
from app.routers.plans import get_llm_engine


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create an isolated temporary SQLite database file in WAL mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    # Initialize schemas, WAL pragmas, and FTS5 triggers
    init_db_sync(path)

    yield path

    # Garbage collect to release SQLite file locks on Windows
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
def sample_seeded_plan(temp_db: str) -> dict[str, Any]:
    """Seed a sample multi-step plan with executed steps into the temporary database."""
    steps = [
        {
            "id": "step_seed_01",
            "title": "Initialize SQLite Database with WAL Pragmas",
            "description": "Configure journal_mode=WAL, synchronous=NORMAL, and busy_timeout=5000.",
            "tool": "database",
            "status": "completed",
            "result": "Database initialized with Write-Ahead Logging and FTS5 external virtual tables.",
        },
        {
            "id": "step_seed_02",
            "title": "Implement LangGraph StateGraph Workflow",
            "description": "Construct cyclic StateGraph with planner, executor, replanner, and synthesizer nodes.",
            "tool": "code",
            "status": "completed",
            "result": "StateGraph compiled with conditional replanning edges and cycle bounds.",
        },
        {
            "id": "step_seed_03",
            "title": "Verify Multi-Tier Pytest Suite",
            "description": "Execute comprehensive tests verifying 100% pass rate with zero external API calls.",
            "tool": "eval",
            "status": "pending",
            "result": None,
        },
    ]

    plan = create_plan_sync(
        goal="Build high-performance SQLite WAL agent workflow with LangGraph",
        steps=steps,
        db_path=temp_db,
    )

    # Mark first two steps as completed in DB
    update_step_sync(
        "step_seed_01",
        "completed",
        "Database initialized with Write-Ahead Logging and FTS5 external virtual tables.",
        None,
        temp_db,
    )
    update_step_sync(
        "step_seed_02",
        "completed",
        "StateGraph compiled with conditional replanning edges and cycle bounds.",
        None,
        temp_db,
    )
    update_plan_status_sync(plan["id"], "in_progress", 2, None, temp_db)

    return plan


@pytest.fixture
def test_client(temp_db: str) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured with isolated temporary database."""
    def get_test_settings() -> Settings:
        return Settings(
            database_path=temp_db,
            environment="test",
            log_level="DEBUG",
            max_steps=10,
            max_iterations=15,
            replan_threshold=0.7,
            enable_adaptive_replanning=True,
        )

    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_llm_engine] = lambda: DeterministicMockLLM()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
