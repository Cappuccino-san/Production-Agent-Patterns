"""Shared fixtures for OpenTelemetry Agent Tracer tests."""

import gc
import os
import tempfile
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_traced_graph
from app.config import get_settings
from app.database import init_db_sync
from app.main import app
from app.routers.traces import set_traced_graph
from app.tracer import AgentTracer


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
def test_tracer() -> AgentTracer:
    return AgentTracer()


@pytest.fixture
def test_client(temp_db: str, test_tracer: AgentTracer) -> Generator[TestClient, None, None]:
    settings = get_settings()
    settings.database_path = temp_db

    graph = create_traced_graph(temp_db, test_tracer)
    set_traced_graph(graph)

    with TestClient(app) as client:
        yield client
