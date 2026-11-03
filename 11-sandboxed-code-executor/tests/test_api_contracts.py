"""Tier 4: FastAPI REST API Contracts and Endpoint Verification."""

import pytest
from fastapi.testclient import TestClient


class TestApiContracts:
    def test_health_endpoints(self, test_client: TestClient):
        r_live = test_client.get("/health/live")
        assert r_live.status_code == 200
        assert r_live.json() == {"status": "alive"}

        r_ready = test_client.get("/health/ready")
        assert r_ready.status_code == 200
        assert r_ready.json()["status"] == "ready"

    def test_execute_code_success(self, test_client: TestClient):
        payload = {"code": "print('Hello Sandboxed World')"}
        resp = test_client.post("/sandbox/execute", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert "Hello Sandboxed World" in data["stdout"]
        assert data["egress_blocked"] is True

    def test_execute_forbidden_network_blocked_by_ast(self, test_client: TestClient):
        payload = {"code": "import requests\nresp = requests.get('https://example.com')"}
        resp = test_client.post("/sandbox/execute", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SECURITY_VIOLATION"
        assert "Zero internet egress policy enforced" in data["stderr"]
        assert any("requests" in v for v in data["ast_violations"])

    def test_agent_task_endpoint(self, test_client: TestClient):
        payload = {"prompt": "Calculate Fibonacci sequence up to 10"}
        resp = test_client.post("/sandbox/agent-task", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert "Fibonacci(10) = 55" in data["stdout"]

    def test_search_executions_endpoint(self, test_client: TestClient):
        test_client.post(
            "/sandbox/execute",
            json={"code": "print('Matrix multiplication benchmark execution')"},
        )

        resp = test_client.get("/sandbox/search?q=multiplication")
        assert resp.status_code == 200
        hits = resp.json()
        assert len(hits) >= 1
        assert any("multiplication" in h["snippet"].lower() for h in hits)
