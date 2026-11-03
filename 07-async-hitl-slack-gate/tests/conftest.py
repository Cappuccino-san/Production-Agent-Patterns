"""Shared fixtures for Async HITL Slack Gate tests."""

import gc
import os
import tempfile
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_draft_graph, create_resume_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync
from app.main import app
from app.routers.hitl import set_draft_graph, set_resume_graph


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

    set_draft_graph(create_draft_graph(temp_db, mock_llm, settings.approval_timeout_hours))
    set_resume_graph(create_resume_graph(temp_db, mock_llm))

    with TestClient(app) as client:
        yield client
