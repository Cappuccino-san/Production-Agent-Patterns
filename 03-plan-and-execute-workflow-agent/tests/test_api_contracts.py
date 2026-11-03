"""Tier 4: FastAPI HTTP REST API contract and lifespan validation tests."""

from typing import Any
import pytest
from fastapi.testclient import TestClient


@pytest.mark.api
class TestHealthEndpoints:
    """Contract tests for health and probe endpoints."""

    def test_liveness_endpoint(self, test_client: TestClient) -> None:
        response = test_client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_readiness_endpoint(self, test_client: TestClient) -> None:
        response = test_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "database": "connected"}

    def test_consolidated_health_endpoint(self, test_client: TestClient) -> None:
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "version" in data
        assert "environment" in data

    def test_root_endpoint(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Plan-and-Execute Workflow Agent API"
        assert data["docs_url"] == "/docs"

    def test_readiness_failure_when_database_unreachable(self) -> None:
        from app.main import app
        from app.config import Settings, get_settings
        app.dependency_overrides[get_settings] = lambda: Settings(database_path="Z:/invalid/path/test.db")
        with TestClient(app) as client:
            resp = client.get("/health/ready")
            assert resp.status_code == 503
            resp_h = client.get("/health")
            assert resp_h.status_code == 200
            assert resp_h.json()["status"] == "degraded"
        app.dependency_overrides.clear()


@pytest.mark.api
class TestPlanEndpoints:
    """Contract tests for Plan CRUD, execution, and search endpoints."""

    def test_create_plan_success(self, test_client: TestClient) -> None:
        payload = {"goal": "Build distributed task worker queue on AWS EC2"}
        response = test_client.post("/api/v1/plans", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["goal"] == payload["goal"]
        assert data["status"] == "created"
        assert len(data["steps"]) >= 3
        assert "id" in data

    def test_create_plan_alias_route(self, test_client: TestClient) -> None:
        payload = {"goal": "Analyze market trends and customer churn"}
        response = test_client.post("/api/v1/plans/create", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["goal"] == payload["goal"]

    def test_create_plan_validation_error_rfc7807(self, test_client: TestClient) -> None:
        # Empty goal should fail validation
        response = test_client.post("/api/v1/plans", json={"goal": ""})
        assert response.status_code == 422
        assert response.headers.get("content-type") == "application/problem+json"
        data = response.json()
        assert data["status"] == 422
        assert data["title"] == "Request Validation Error"

    def test_create_plan_extra_field_rejected(self, test_client: TestClient) -> None:
        response = test_client.post(
            "/api/v1/plans",
            json={"goal": "Valid goal", "unexpected_field": "disallowed"},
        )
        assert response.status_code == 422

    def test_get_plan_by_id(self, test_client: TestClient, sample_seeded_plan: dict[str, Any]) -> None:
        plan_id = sample_seeded_plan["id"]
        response = test_client.get(f"/api/v1/plans/{plan_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == plan_id
        assert len(data["steps"]) == 3

    def test_get_nonexistent_plan_returns_404_rfc7807(self, test_client: TestClient) -> None:
        response = test_client.get("/api/v1/plans/nonexistent_plan_999")
        assert response.status_code == 404
        assert response.headers.get("content-type") == "application/problem+json"
        data = response.json()
        assert data["status"] == 404
        assert "not found" in data["detail"].lower()

    def test_list_plans(self, test_client: TestClient, sample_seeded_plan: dict[str, Any]) -> None:
        response = test_client.get("/api/v1/plans?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(p["id"] == sample_seeded_plan["id"] for p in data)

    def test_execute_plan_success(self, test_client: TestClient) -> None:
        # Create plan first
        create_resp = test_client.post(
            "/api/v1/plans",
            json={"goal": "Implement automated SQLite backup strategy"},
        )
        plan_id = create_resp.json()["id"]

        # Trigger execution
        exec_resp = test_client.post(
            f"/api/v1/plans/{plan_id}/execute",
            json={"max_iterations": 10, "allow_replanning": True},
        )
        assert exec_resp.status_code == 200
        data = exec_resp.json()
        assert data["plan_id"] == plan_id
        assert data["completed"] is True
        assert data["status"] == "completed"
        assert data["response"] is not None
        assert "Workflow Summary" in data["response"]

    def test_execute_nonexistent_plan_returns_404(self, test_client: TestClient) -> None:
        response = test_client.post("/api/v1/plans/nonexistent_999/execute", json={})
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == 404

    def test_search_plans_fts5(self, test_client: TestClient, sample_seeded_plan: dict[str, Any]) -> None:
        response = test_client.get("/api/v1/plans/search?q=StateGraph")
        assert response.status_code == 200
        results = response.json()
        assert len(results) >= 1
        assert results[0]["plan_id"] == sample_seeded_plan["id"]
        assert "StateGraph" in results[0]["title"] or "StateGraph" in results[0]["result"]

    def test_search_plans_missing_query_parameter_fails(self, test_client: TestClient) -> None:
        response = test_client.get("/api/v1/plans/search")
        assert response.status_code == 422
