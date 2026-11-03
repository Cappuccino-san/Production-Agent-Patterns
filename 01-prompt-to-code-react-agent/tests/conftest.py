"""Shared Pytest fixtures for multi-tier verification."""

import os
import tempfile
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Specify asyncio backend for pytest-asyncio."""
    return "asyncio"


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Provide an isolated temporary SQLite database path, cleaning WAL files on teardown."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path

    # Clean up SQLite database and auxiliary WAL/SHM files
    for ext in ["", "-wal", "-shm"]:
        target = path + ext
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass


@pytest_asyncio.fixture
async def temp_db(temp_db_path: str) -> AsyncGenerator[str, None]:
    """Initialize schema, WAL pragmas, and FTS5 triggers in temporary SQLite database."""
    await init_db(temp_db_path)
    yield temp_db_path


@pytest.fixture
def mock_llm() -> DeterministicMockLLM:
    """Instantiate a clean deterministic mock LLM for testing."""
    return DeterministicMockLLM()


@pytest.fixture
def test_client(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """Synchronous FastAPI TestClient with isolated test database and cleared settings cache."""
    monkeypatch.setenv("DATABASE_PATH", temp_db)
    get_settings.cache_clear()

    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


@pytest_asyncio.fixture
async def async_client(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous httpx client for testing async FastAPI endpoints."""
    monkeypatch.setenv("DATABASE_PATH", temp_db)
    get_settings.cache_clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    get_settings.cache_clear()
