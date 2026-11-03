"""Tier 1: Pydantic Schema Validation Tests for Sanitization Proxy."""

import pytest
from pydantic import ValidationError
from app.models import (
    ActionTaken,
    MessagePacket,
    RFC7807Error,
    RiskLevel,
    SanitizationResult,
)


class TestSchemas:
    def test_message_packet_valid(self):
        packet = MessagePacket(
            sender_agent="ResearcherAgent",
            receiver_agent="CoderAgent",
            content="Please write an async rate limiter.",
        )
        assert packet.sender_agent == "ResearcherAgent"
        assert packet.content == "Please write an async rate limiter."
        assert packet.message_id.startswith("msg-")

    def test_message_packet_empty_content_raises(self):
        with pytest.raises(ValidationError):
            MessagePacket(
                sender_agent="AgentA",
                receiver_agent="AgentB",
                content="",  # min_length=1
            )

    def test_sanitization_result_model(self):
        result = SanitizationResult(
            message_id="msg-101",
            sender_agent="UntrustedAgent",
            receiver_agent="CoreAgent",
            is_clean=False,
            sanitized_content="Scrubbed content",
            risk_score=85.0,
            action_taken=ActionTaken.BLOCKED_QUARANTINE,
            matched_rules=["System Prompt Override Attempt"],
        )
        assert result.action_taken == ActionTaken.BLOCKED_QUARANTINE
        assert result.risk_score == 85.0

    def test_rfc7807_error_model(self):
        err = RFC7807Error(
            title="Validation Error",
            status=422,
            detail="Field missing",
        )
        assert err.status == 422
