"""Shared fixtures for Trajectory Eval CI Gate tests."""

import gc
import os
import tempfile
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_eval_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync, save_golden_dag_sync
from app.main import app
from app.routers.eval import set_eval_graph


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    init_db_sync(path)
    default_dag = DeterministicMockLLM.get_default_golden_dag()
    save_golden_dag_sync(path, default_dag, "2026-11-02T12:00:00Z")

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
def test_client(temp_db: str) -> Generator[TestClient, None, None]:
    settings = get_settings()
    settings.database_path = temp_db

    graph = create_eval_graph(temp_db)
    set_eval_graph(graph)

    with TestClient(app) as client:
        yield client
