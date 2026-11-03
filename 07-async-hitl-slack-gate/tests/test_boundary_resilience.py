"""Tier 5: Boundary Conditions, 3-Day SLA Timeout, and Race Condition Resilience."""

import concurrent.futures
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.database import get_gate_action_sync, save_gate_action_sync
from app.models import ActionType, GateActionRecord, GateStatus


class TestBoundaryResilience:
    def test_sla_timeout_expiration(self, test_client: TestClient, temp_db: str):
        """Simulate an action whose 3-day SLA window has passed."""
        past_time = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        record = GateActionRecord(
            action_id="act-expired-1",
            action_type=ActionType.MASS_REFUND,
            status=GateStatus.PENDING_APPROVAL,
            risk_score=95.0,
            description="High value refund pending",
            payload={"total_usd": 50000},
            expires_at=past_time,
            created_at=past_time,
            updated_at=past_time,
        )
        save_gate_action_sync(temp_db, record)

        # Attempt to approve an expired action
        wh_resp = test_client.post(
            "/hitl/slack/webhook",
            json={
                "action_id": "act-expired-1",
                "user_id": "U_LATE_APPROVER",
                "decision": "approve",
                "reason": "Late approval",
            },
        )
        assert wh_resp.status_code == 200
        data = wh_resp.json()
        assert data["status"] == "EXPIRED"
        assert data["execution_result"]["aborted"] is True

    def test_concurrent_webhook_approvals_race(self, test_client: TestClient):
        """Two approvers clicking 'Approve' concurrently: only one succeeds, other gets 409."""
        draft_resp = test_client.post(
            "/hitl/draft",
            json={
                "action_type": "DEPLOY_PRODUCTION",
                "description": "Concurrent race test",
                "target_system": "k8s",
                "risk_score": 70.0,
            },
        )
        action_id = draft_resp.json()["action_id"]

        def click_approve(user_id: str):
            return test_client.post(
                "/hitl/slack/webhook",
                json={"action_id": action_id, "user_id": user_id, "decision": "approve"},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(click_approve, "UserA")
            f2 = executor.submit(click_approve, "UserB")
            r1 = f1.result()
            r2 = f2.result()

        statuses = [r1.status_code, r2.status_code]
        assert 200 in statuses
        assert 409 in statuses
