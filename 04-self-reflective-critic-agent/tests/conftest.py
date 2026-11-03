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
from app.database import (
    add_reflection_sync,
    create_session_sync,
    init_db_sync,
    update_session_status_sync,
)
from app.main import app
from app.routers.reflections import get_llm_engine


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
def sample_session(temp_db: str) -> dict[str, Any]:
    """Seed a sample reflection session with two iterations into the temporary database."""
    session = create_session_sync(
        task="Write an efficient binary search function with boundary validation",
        threshold=85.0,
        rubric=None,
        session_id="sess_seed_01",
        db_path=temp_db,
    )

    # Iteration 1: Naive draft with defects
    add_reflection_sync(
        session_id="sess_seed_01",
        iteration=1,
        draft="def binary_search(arr, target):\n    for i, x in enumerate(arr):\n        if x == target:\n            return i\n    return -1\n",
        critique="Critique Assessment [NEEDS REVISION]: Composite Score = 60.0/85.0.\nIdentified Shortcomings (2):\n  1. Linear search used instead of binary search O(log N).\n  2. Missing input validation for None.",
        rubric_scores={"correctness": 60.0, "completeness": 55.0, "clarity": 65.0, "efficiency": 60.0},
        composite_score=60.0,
        status="in_progress",
        reflection_id="refl_seed_01",
        db_path=temp_db,
    )

    # Iteration 2: Refined draft meeting threshold
    add_reflection_sync(
        session_id="sess_seed_01",
        iteration=2,
        draft='from typing import Sequence, Optional\n\ndef binary_search(arr: Sequence[int], target: int) -> Optional[int]:\n    """Perform O(log N) binary search on sorted sequence."""\n    if arr is None:\n        raise TypeError("Input array cannot be None")\n    low, high = 0, len(arr) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return None\n',
        critique="Critique Assessment [PASSED]: Composite Score = 90.0/85.0.\nCriteria Breakdown: Correctness: 90.0, Completeness: 90.0, Clarity: 90.0, Efficiency: 90.0.\nSolution satisfies all rigorous quality and correctness standards.",
        rubric_scores={"correctness": 90.0, "completeness": 90.0, "clarity": 90.0, "efficiency": 90.0},
        composite_score=90.0,
        status="completed",
        reflection_id="refl_seed_02",
        db_path=temp_db,
    )

    update_session_status_sync(
        session_id="sess_seed_01",
        status="completed",
        final_score=90.0,
        db_path=temp_db,
    )

    return session


@pytest.fixture
def test_client(temp_db: str) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured with isolated temporary database."""
    def get_test_settings() -> Settings:
        return Settings(
            database_path=temp_db,
            environment="test",
            log_level="DEBUG",
            default_threshold=85.0,
            default_max_iterations=4,
        )

    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_llm_engine] = lambda: DeterministicMockLLM()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
