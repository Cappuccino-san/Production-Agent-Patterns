"""Tier 4: FastAPI REST API Contracts and Slack Webhook Tests."""

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

    def test_draft_and_slack_webhook_approval_flow(self, test_client: TestClient):
        # 1. Draft high-stakes action
        draft_payload = {
            "action_type": "DEPLOY_PRODUCTION",
            "description": "Deploy billing engine release v4.2",
            "target_system": "billing-prod",
            "payload": {"version": "v4.2", "traffic_percent": 100},
            "risk_score": 85.0,
        }
        draft_resp = test_client.post("/hitl/draft", json=draft_payload)
        assert draft_resp.status_code == 201
        draft_data = draft_resp.json()
        action_id = draft_data["action_id"]
        assert draft_data["status"] == "PENDING_APPROVAL"
        assert "slack_blocks" in draft_data

        # 2. Simulate human clicking "Approve" button via Slack Webhook
        webhook_payload = {
            "action_id": action_id,
            "user_id": "U_TECH_LEAD",
            "decision": "approve",
            "reason": "QA sign-off received",
        }
        wh_resp = test_client.post("/hitl/slack/webhook", json=webhook_payload)
        assert wh_resp.status_code == 200
        wh_data = wh_resp.json()
        assert wh_data["status"] == "APPROVED"
        assert wh_data["approver_id"] == "U_TECH_LEAD"
        assert wh_data["execution_result"]["status"] == "APPLIED_SUCCESSFULLY"

        # 3. Query finalized state
        get_resp = test_client.get(f"/hitl/actions/{action_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "APPROVED"

    def test_double_approval_returns_conflict_rfc7807(self, test_client: TestClient):
        # Draft
        draft_resp = test_client.post(
            "/hitl/draft",
            json={
                "action_type": "MASS_REFUND",
                "description": "Mass refund test",
                "target_system": "stripe",
                "payload": {"total_usd": 100},
                "risk_score": 60.0,
            },
        )
        action_id = draft_resp.json()["action_id"]

        # First approval
        test_client.post(
            "/hitl/slack/webhook",
            json={"action_id": action_id, "user_id": "U1", "decision": "approve"},
        )

        # Second approval attempt -> 409 Conflict
        second_resp = test_client.post(
            "/hitl/slack/webhook",
            json={"action_id": action_id, "user_id": "U2", "decision": "approve"},
        )
        assert second_resp.status_code == 409
        err = second_resp.json()
        assert err["status"] == 409
        assert "already finalized" in err["detail"]

    def test_search_audits_endpoint(self, test_client: TestClient):
        # Draft and approve
        draft_resp = test_client.post(
            "/hitl/draft",
            json={
                "action_type": "DATABASE_MIGRATION",
                "description": "PostgreSQL vacuum full execution",
                "target_system": "postgres-db",
                "risk_score": 75.0,
            },
        )
        action_id = draft_resp.json()["action_id"]
        test_client.post(
            "/hitl/slack/webhook",
            json={
                "action_id": action_id,
                "user_id": "U_DBA",
                "decision": "approve",
                "reason": "Authorized maintenance vacuum window",
            },
        )

        # FTS5 BM25 search
        resp = test_client.get("/hitl/search?q=vacuum")
        assert resp.status_code == 200
        hits = resp.json()
        assert len(hits) >= 1
        assert any("vacuum" in h["snippet"].lower() for h in hits)
