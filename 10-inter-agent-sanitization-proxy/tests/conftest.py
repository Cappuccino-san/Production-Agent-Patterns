"""Shared fixtures for Inter-Agent Sanitization Proxy tests."""

import gc
import os
import tempfile
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_proxy_graph
from app.config import get_settings
from app.database import init_db_sync
from app.main import app
from app.routers.proxy import set_proxy_graph
from app.sanitizer import MessageSanitizer


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
def sanitizer() -> MessageSanitizer:
    return MessageSanitizer(quarantine_threshold=75.0, block_critical=True)


@pytest.fixture
def test_client(temp_db: str, sanitizer: MessageSanitizer) -> Generator[TestClient, None, None]:
    settings = get_settings()
    settings.database_path = temp_db

    graph = create_proxy_graph(temp_db, sanitizer)
    set_proxy_graph(graph)

    with TestClient(app) as client:
        yield client
