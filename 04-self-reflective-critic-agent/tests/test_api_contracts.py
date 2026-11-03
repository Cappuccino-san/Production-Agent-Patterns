"""Tier 4: FastAPI TestClient HTTP API contract and status code tests."""

from fastapi.testclient import TestClient


class TestHealthAndMetadataEndpoints:
    """Verifies health and discovery endpoints."""

    def test_root_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Self-Reflective Critic Agent API"
        assert "docs_url" in data

    def test_health_live(self, test_client: TestClient) -> None:
        resp = test_client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_health_ready(self, test_client: TestClient) -> None:
        resp = test_client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["journal_mode"].lower() == "wal"


class TestReflectionsExecuteEndpoint:
    """Verifies POST /api/v1/reflections/execute contract."""

    def test_execute_reflection_success(self, test_client: TestClient) -> None:
        payload = {
            "task": "Write an LRU Cache with O(1) get and put operations",
            "threshold": 85.0,
            "max_iterations": 4,
        }
        resp = test_client.post("/api/v1/reflections/execute", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert "session_id" in data
        assert data["session_id"].startswith("sess_")
        assert data["task"] == payload["task"]
        assert data["status"] in ("completed", "max_iterations_reached")
        assert data["final_score"] >= 85.0
        assert data["iterations_count"] >= 2
        assert len(data["history"]) == data["iterations_count"]

    def test_execute_invalid_payload_validation_error(self, test_client: TestClient) -> None:
        # Task too short (<3 chars)
        payload = {"task": "hi", "threshold": 85.0}
        resp = test_client.post("/api/v1/reflections/execute", json=payload)
        assert resp.status_code == 422
        assert resp.headers["content-type"].startswith("application/problem+json")


class TestReflectionsEvaluateEndpoint:
    """Verifies POST /api/v1/reflections/evaluate standalone evaluation."""

    def test_evaluate_candidate_flawed(self, test_client: TestClient) -> None:
        payload = {
            "task": "Implement string reversal",
            "candidate_text": "def rev(s): return s[::-1]",
            "threshold": 85.0,
        }
        resp = test_client.post("/api/v1/reflections/evaluate", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["task"] == payload["task"]
        assert "evaluation" in data
        eval_data = data["evaluation"]
        assert "composite_score" in eval_data
        assert "critique" in eval_data
        assert len(eval_data["defects"]) > 0

    def test_evaluate_candidate_empty_validation_error(self, test_client: TestClient) -> None:
        payload = {
            "task": "Valid task",
            "candidate_text": "",
        }
        resp = test_client.post("/api/v1/reflections/evaluate", json=payload)
        assert resp.status_code == 422


class TestSessionAndSearchEndpoints:
    """Verifies session retrieval and FTS5 search endpoints."""

    def test_get_session_found(
        self, test_client: TestClient, sample_session: dict
    ) -> None:
        sid = sample_session["id"]
        resp = test_client.get(f"/api/v1/reflections/sessions/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == sid
        assert len(data["iterations"]) == 2
        assert data["final_score"] == 90.0

    def test_get_session_not_found(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/v1/reflections/sessions/non_existent_session_id")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/problem+json")
        data = resp.json()
        assert data["status"] == 404

    def test_search_reflections_success(
        self, test_client: TestClient, sample_session: dict
    ) -> None:
        resp = test_client.get("/api/v1/reflections/search?q=binary&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "binary"
        assert data["total_results"] >= 1
        assert len(data["results"]) >= 1
        assert "binary" in data["results"][0]["snippet"].lower()

    def test_search_missing_query_parameter(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/v1/reflections/search")
        assert resp.status_code == 422

    def test_list_sessions(self, test_client: TestClient, sample_session: dict) -> None:
        resp = test_client.get("/api/v1/reflections/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
