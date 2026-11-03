"""Tier 4: FastAPI TestClient HTTP contract tests for all REST endpoints."""

from fastapi.testclient import TestClient


class TestHealthContracts:
    """Validate /health/live and /health/ready endpoints."""

    def test_health_live(self, test_client: TestClient):
        response = test_client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "live"
        assert "service" in data

    def test_health_ready(self, test_client: TestClient):
        response = test_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"]["journal_mode"].lower() == "wal"


class TestApprovalsSubmitContract:
    """Validate POST /api/v1/approvals/submit endpoint."""

    def test_submit_low_risk_auto_completes(self, test_client: TestClient):
        payload = {
            "action_type": "query_database",
            "description": "Fetch current inventory count",
            "payload": {"table": "inventory"},
        }
        response = test_client.post("/api/v1/approvals/submit", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("req_")
        assert data["risk_level"] == "LOW"
        assert data["status"] == "completed"
        assert data["decision"] == "approve"
        assert data["result"] is not None

    def test_submit_high_risk_pauses_for_approval(self, test_client: TestClient):
        payload = {
            "action_type": "drop_database",
            "description": "Drop legacy customer database in prod",
            "payload": {"database": "legacy_customers"},
        }
        response = test_client.post("/api/v1/approvals/submit", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("req_")
        assert data["risk_level"] == "CRITICAL"
        assert data["status"] == "pending_approval"
        assert data["decision"] is None
        assert data["result"] is None
        assert data["checkpoint_state"] is not None
        assert "approval_gate_node" in data["checkpoint_state"]["next_nodes"]

    def test_submit_with_risk_override(self, test_client: TestClient):
        payload = {
            "action_type": "query_database",
            "description": "Sensitive customer PII query",
            "payload": {"query": "SELECT ssn FROM customers"},
            "risk_override": "HIGH",
        }
        response = test_client.post("/api/v1/approvals/submit", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["risk_level"] == "HIGH"
        assert data["status"] == "pending_approval"

    def test_submit_validation_failure_returns_rfc7807(self, test_client: TestClient):
        # Description is too short (< 5 chars)
        payload = {
            "action_type": "query",
            "description": "bad",
        }
        response = test_client.post("/api/v1/approvals/submit", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert data["status"] == 422
        assert data["title"] == "Request Validation Error"


class TestPendingApprovalsContract:
    """Validate GET /api/v1/approvals/pending endpoint."""

    def test_get_pending_approvals_list(self, test_client: TestClient, sample_pending_request: dict):
        response = test_client.get("/api/v1/approvals/pending")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        ids = [item["id"] for item in data["items"]]
        assert sample_pending_request["id"] in ids


class TestGetApprovalByIdContract:
    """Validate GET /api/v1/approvals/{id} endpoint."""

    def test_get_existing_approval_returns_200(self, test_client: TestClient, sample_pending_request: dict):
        req_id = sample_pending_request["id"]
        response = test_client.get(f"/api/v1/approvals/{req_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == req_id
        assert data["status"] == "pending_approval"

    def test_get_non_existent_approval_returns_404(self, test_client: TestClient):
        response = test_client.get("/api/v1/approvals/req_non_existent_999")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == 404
        assert "not found" in data["detail"].lower()


class TestDecisionAndResumeContract:
    """Validate POST /api/v1/approvals/{id}/decision endpoint and LangGraph resumption."""

    def test_approve_decision_resumes_and_completes(self, test_client: TestClient):
        # 1. Submit high-risk action
        submit_res = test_client.post(
            "/api/v1/approvals/submit",
            json={
                "action_type": "delete_user",
                "description": "Purge GDPR deleted account",
                "payload": {"user_id": "usr_999"},
            },
        )
        req_id = submit_res.json()["id"]

        # 2. Submit APPROVE decision
        decision_res = test_client.post(
            f"/api/v1/approvals/{req_id}/decision",
            json={
                "decision": "approve",
                "decision_by": "privacy_officer",
                "decision_reason": "Right to be forgotten request verified",
            },
        )
        assert decision_res.status_code == 200
        data = decision_res.json()
        assert data["request_id"] == req_id
        assert data["status"] == "completed"
        assert data["decision"] == "approve"
        assert "Authorized by privacy_officer" in data["result"]

        # 3. Verify record updated
        get_res = test_client.get(f"/api/v1/approvals/{req_id}")
        assert get_res.json()["status"] == "completed"

    def test_reject_decision_resumes_and_bypasses(self, test_client: TestClient):
        # 1. Submit high-risk action
        submit_res = test_client.post(
            "/api/v1/approvals/submit",
            json={
                "action_type": "terminate_ec2_instances",
                "description": "Terminate primary database host",
                "payload": {"instance_id": "i-db-primary"},
            },
        )
        req_id = submit_res.json()["id"]

        # 2. Submit REJECT decision
        decision_res = test_client.post(
            f"/api/v1/approvals/{req_id}/decision",
            json={
                "decision": "reject",
                "decision_by": "infra_director",
                "decision_reason": "Denying accidental termination of primary node",
            },
        )
        assert decision_res.status_code == 200
        data = decision_res.json()
        assert data["status"] == "rejected"
        assert data["decision"] == "reject"
        assert "cancelled by reviewer infra_director" in data["result"]

    def test_modify_decision_resumes_with_new_parameters(self, test_client: TestClient):
        # 1. Submit medium-risk action
        submit_res = test_client.post(
            "/api/v1/approvals/submit",
            json={
                "action_type": "update_user",
                "description": "Grant elevated billing permission",
                "payload": {"user_id": "usr_55", "role": "super_admin"},
            },
        )
        req_id = submit_res.json()["id"]

        # 2. Submit MODIFY decision
        decision_res = test_client.post(
            f"/api/v1/approvals/{req_id}/decision",
            json={
                "decision": "modify",
                "decision_by": "security_lead",
                "decision_reason": "Downgraded to billing_admin role",
                "modified_payload": {"user_id": "usr_55", "role": "billing_admin"},
            },
        )
        assert decision_res.status_code == 200
        data = decision_res.json()
        assert data["status"] == "completed"
        assert data["decision"] == "modify"

        # Check DB reflects modified payload
        get_res = test_client.get(f"/api/v1/approvals/{req_id}")
        assert get_res.json()["payload"]["role"] == "billing_admin"

    def test_decision_on_already_finalized_request_returns_409(self, test_client: TestClient, sample_completed_request: dict):
        req_id = sample_completed_request["id"]
        response = test_client.post(
            f"/api/v1/approvals/{req_id}/decision",
            json={
                "decision": "approve",
                "decision_by": "admin",
            },
        )
        assert response.status_code == 409
        data = response.json()
        assert data["status"] == 409
        assert "already finalized" in data["detail"].lower()

    def test_decision_on_non_existent_request_returns_404(self, test_client: TestClient):
        response = test_client.post(
            "/api/v1/approvals/req_fake_12345/decision",
            json={
                "decision": "approve",
                "decision_by": "admin",
            },
        )
        assert response.status_code == 404


class TestAuditSearchContract:
    """Validate GET /api/v1/approvals/search endpoint."""

    def test_search_audit_log_match(self, test_client: TestClient):
        # Submit an action to index
        test_client.post(
            "/api/v1/approvals/submit",
            json={
                "action_type": "query_database",
                "description": "Inspect quantum telemetry cluster logs",
                "payload": {"cluster": "quantum_node_1"},
            },
        )

        response = test_client.get("/api/v1/approvals/search?q=quantum")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert any("quantum" in (item["description"] + str(item["snippet"])).lower() for item in data["results"])

    def test_search_audit_log_no_match(self, test_client: TestClient):
        response = test_client.get("/api/v1/approvals/search?q=nonexistentxyz123")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_search_missing_query_parameter_returns_422(self, test_client: TestClient):
        response = test_client.get("/api/v1/approvals/search")
        assert response.status_code == 422
