"""Tier 4: FastAPI TestClient HTTP API Contract & Lifespan Tests."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.api
def test_liveness_probe(test_client: TestClient) -> None:
    """Verify GET /health/live returns HTTP 200 and live status."""
    response = test_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


@pytest.mark.api
def test_readiness_probe(test_client: TestClient) -> None:
    """Verify GET /health/ready confirms DB connectivity and WAL mode."""
    response = test_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "journal_mode=wal" in data["database"]


@pytest.mark.api
def test_general_health(test_client: TestClient) -> None:
    """Verify GET /health returns service health status."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.api
def test_post_agent_run(test_client: TestClient) -> None:
    """Verify POST /api/v1/agent/run triggers ReAct agent and returns response schema."""
    payload = {
        "prompt": "Write a python function to check if a number is prime",
        "language": "python",
        "max_iterations": 4,
    }
    response = test_client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "run_id" in data
    assert data["prompt"] == payload["prompt"]
    assert data["is_valid"] is True
    assert "is_prime" in data["code"]
    assert data["iterations"] >= 1
    assert data["status"] == "completed"
    assert len(data["steps"]) >= 3


@pytest.mark.api
def test_get_recent_runs_empty_and_populated(test_client: TestClient) -> None:
    """Verify GET /api/v1/agent/runs lists historical runs."""
    # 1. Trigger a run
    test_client.post("/api/v1/agent/run", json={"prompt": "Compute factorial of 4"})

    # 2. List runs
    response = test_client.get("/api/v1/agent/runs?limit=10")
    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    assert len(runs) >= 1
    assert "run_id" in runs[0]


@pytest.mark.api
def test_get_single_run_by_id(test_client: TestClient) -> None:
    """Verify GET /api/v1/agent/runs/{run_id} returns exact run details."""
    # 1. Create run
    post_res = test_client.post("/api/v1/agent/run", json={"prompt": "Generate reverse string function"})
    run_id = post_res.json()["run_id"]

    # 2. Retrieve by ID
    get_res = test_client.get(f"/api/v1/agent/runs/{run_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["run_id"] == run_id
    assert "reverse_string" in data["code"]


@pytest.mark.api
def test_get_single_run_not_found_rfc7807(test_client: TestClient) -> None:
    """Verify GET non-existent run returns HTTP 404 with RFC 7807 problem details."""
    response = test_client.get("/api/v1/agent/runs/nonexistent_id_999")
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == 404
    assert data["type"] == "urn:agent:error:404"
    assert "not found" in data["detail"].lower()
    assert data["instance"] == "/api/v1/agent/runs/nonexistent_id_999"


@pytest.mark.api
def test_search_runs_endpoint(test_client: TestClient) -> None:
    """Verify GET /api/v1/agent/runs/search performs FTS5 search."""
    # 1. Populate
    test_client.post("/api/v1/agent/run", json={"prompt": "Quicksort algorithm"})

    # 2. Search
    search_res = test_client.get("/api/v1/agent/runs/search?q=Quicksort")
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) >= 1
    assert "Quicksort" in results[0]["snippet"] or "Quicksort" in results[0]["prompt"]


@pytest.mark.api
def test_run_agent_validation_error(test_client: TestClient) -> None:
    """Verify submitting invalid payload triggers HTTP 422 Unprocessable Entity."""
    # Missing required 'prompt' field
    response = test_client.post("/api/v1/agent/run", json={"language": "python"})
    assert response.status_code == 422
