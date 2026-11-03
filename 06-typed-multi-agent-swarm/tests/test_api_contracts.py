"""Tier 4: FastAPI REST API Contract and RFC 7807 Endpoint Tests."""

import pytest
from fastapi.testclient import TestClient


class TestApiContracts:
    def test_health_live(self, test_client: TestClient):
        response = test_client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_health_ready(self, test_client: TestClient):
        response = test_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_dispatch_task_success(self, test_client: TestClient):
        payload = {
            "task_description": "Build high-throughput sharded key-value store",
            "context": "Needs consistent hashing and replication",
            "max_iterations": 3,
        }
        response = test_client.post("/swarm/dispatch", json=payload)
        assert response.status_code == 201
        data = response.json()

        assert data["task_id"].startswith("task-")
        assert data["status"] == "COMPLETED"
        assert data["iteration"] == 1
        assert data["research"]["topic"] == payload["task_description"]
        assert data["code"]["language"] == "python"
        assert data["review"]["approved"] is True
        assert len(data["history"]) == 3

    def test_dispatch_task_validation_error_returns_rfc7807(self, test_client: TestClient):
        # Invalid body: task_description too short
        payload = {"task_description": "Hi"}
        response = test_client.post("/swarm/dispatch", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert data["status"] == 422
        assert "validation-error" in data["type"]
        assert "task_description" in data["detail"]

    def test_get_task_success(self, test_client: TestClient):
        # First dispatch
        payload = {"task_description": "Build distributed lock with Redis lease"}
        dispatch_resp = test_client.post("/swarm/dispatch", json=payload)
        task_id = dispatch_resp.json()["task_id"]

        # Fetch
        get_resp = test_client.get(f"/swarm/tasks/{task_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["task_id"] == task_id
        assert data["status"] == "COMPLETED"
        assert data["research"] is not None
        assert data["code"] is not None
        assert data["review"] is not None

    def test_get_task_not_found_returns_rfc7807(self, test_client: TestClient):
        response = test_client.get("/swarm/tasks/task-nonexistent-123")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == 404
        assert "http-error" in data["type"]
        assert "not found" in data["detail"].lower()

    def test_search_artifacts_endpoint(self, test_client: TestClient):
        # Dispatch a task to populate artifacts
        payload = {"task_description": "Implement Paxos Distributed Protocol"}
        test_client.post("/swarm/dispatch", json=payload)

        # Search for protocol
        response = test_client.get("/swarm/search?q=Paxos")
        assert response.status_code == 200
        hits = response.json()
        assert isinstance(hits, list)
        assert len(hits) >= 1
        assert any("paxos" in hit["title"].lower() or "paxos" in hit["content_snippet"].lower() for hit in hits)
