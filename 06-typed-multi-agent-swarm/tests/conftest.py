"""Pytest shared fixtures and test client setup."""

import gc
import os
import tempfile
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_swarm_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync
from app.main import app
from app.routers.swarm import set_agent_graph


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create an isolated temporary SQLite database file with WAL mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    init_db_sync(path)
    yield path

    # Explicit garbage collection to release file handles before deletion on Windows
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
    return DeterministicMockLLM(force_approval_on_iteration=1)


@pytest.fixture
def mock_llm_multi_iter() -> DeterministicMockLLM:
    """Mock LLM requiring 2 iterations before approving code."""
    return DeterministicMockLLM(force_approval_on_iteration=2)


@pytest.fixture
def test_client(temp_db: str, mock_llm: DeterministicMockLLM) -> Generator[TestClient, None, None]:
    """Provide a TestClient connected to an isolated test database and graph."""
    settings = get_settings()
    settings.database_path = temp_db

    graph = create_swarm_graph(temp_db, mock_llm)
    set_agent_graph(graph)

    with TestClient(app) as client:
        yield client
