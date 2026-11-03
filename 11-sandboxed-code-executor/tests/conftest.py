"""Shared fixtures for Sandboxed Code Executor tests."""

import gc
import os
import tempfile
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_interpreter_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync
from app.main import app
from app.routers.sandbox import set_agent_graph


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    init_db_sync(path)
    yield path

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
    return DeterministicMockLLM()


@pytest.fixture
def test_client(temp_db: str, mock_llm: DeterministicMockLLM) -> Generator[TestClient, None, None]:
    settings = get_settings()
    settings.database_path = temp_db

    graph = create_interpreter_graph(temp_db, mock_llm)
    set_agent_graph(graph)

    with TestClient(app) as client:
        yield client
