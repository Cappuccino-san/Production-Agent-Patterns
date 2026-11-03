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

    def test_run_traced_agent_flow(self, test_client: TestClient):
        payload = {
            "agent_name": "AutonomousReviewer",
            "prompt": "Audit code security vulnerabilities and report AST anomalies",
            "destination_sink": "LangSmith",
        }
        resp = test_client.post("/traces/run-agent", json=payload)
        assert resp.status_code == 201
        data = resp.json()

        trace_id = data["trace_id"]
        assert trace_id.startswith("trc-")
        assert data["sink"] == "LangSmith"
        assert len(data["spans"]) >= 4

        # Fetch trace by id
        get_resp = test_client.get(f"/traces/{trace_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["trace_id"] == trace_id
        assert get_data["total_tokens"] > 0

    def test_trace_not_found_returns_rfc7807(self, test_client: TestClient):
        resp = test_client.get("/traces/trc-nonexistent-999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_search_spans_endpoint(self, test_client: TestClient):
        # Run agent first
        test_client.post(
            "/traces/run-agent",
            json={"agent_name": "DataAgent", "prompt": "Examine sqlite introspection tables"},
        )

        resp = test_client.get("/traces/search?q=introspection")
        assert resp.status_code == 200
        hits = resp.json()
        assert len(hits) >= 1
        assert any("introspection" in h["name"].lower() or "introspection" in h["snippet"].lower() for h in hits)
