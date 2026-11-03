"""Tier 1: Pydantic Schema Validation Tests for HITL Slack Gate."""

import pytest
from pydantic import ValidationError
from app.models import (
    ActionType,
    GateStatus,
    HighStakesActionDraft,
    RFC7807Error,
    SlackInteractiveWebhook,
)


class TestHITLSchemas:
    def test_draft_valid(self):
        draft = HighStakesActionDraft(
            action_type=ActionType.DEPLOY_PRODUCTION,
            description="Deploy v2.4.0 with database schema alterations",
            target_system="production-k8s-cluster",
            payload={"tag": "v2.4.0", "replicas": 12},
            risk_score=85.0,
        )
        assert draft.action_type == ActionType.DEPLOY_PRODUCTION
        assert draft.risk_score == 85.0

    def test_draft_invalid_risk_raises(self):
        with pytest.raises(ValidationError):
            HighStakesActionDraft(
                action_type=ActionType.DEPLOY_PRODUCTION,
                description="Invalid risk",
                target_system="prod",
                risk_score=150.0,  # Exceeds 100
            )

    def test_slack_webhook_valid_decisions(self):
        wh_approve = SlackInteractiveWebhook(
            action_id="act-12345",
            user_id="U12345678",
            decision="approve",
            reason="Verified staging rollout",
        )
        assert wh_approve.decision == "approve"

        wh_reject = SlackInteractiveWebhook(
            action_id="act-12345",
            user_id="U12345678",
            decision="reject",
            reason="Blocked by security team",
        )
        assert wh_reject.decision == "reject"

    def test_slack_webhook_invalid_decision_raises(self):
        with pytest.raises(ValidationError):
            SlackInteractiveWebhook(
                action_id="act-123",
                user_id="U123",
                decision="maybe",  # Must be 'approve' or 'reject'
            )

    def test_rfc7807_error_model(self):
        err = RFC7807Error(
            title="Conflict",
            status=409,
            detail="Action is already approved",
        )
        assert err.status == 409
        assert err.type == "about:blank"
