"""Pytest fixtures for API-to-Browser Fallback Agent."""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from app.config import Settings, get_settings
from app.database import init_db_sync
from app.main import app


@pytest.fixture(scope="session")
def temp_db_path():
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "test_fallback_agent.db")
    init_db_sync(db_file)
    yield db_file


@pytest.fixture
def test_settings(temp_db_path):
    return Settings(
        app_name="Test-Fallback-Agent",
        database_path=temp_db_path,
        api_timeout_seconds=2.0,
        browser_timeout_seconds=5.0,
    )


@pytest.fixture
def client(test_settings):
    def override_settings():
        return test_settings

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
