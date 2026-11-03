"""Tier 1: Pydantic schemas, validation constraints, and enum serialization tests."""

import pytest
from pydantic import ValidationError

from app.models import (
    ActionSubmitRequest,
    ApprovalRequestResponse,
    ApprovalStatus,
    AuditSearchResponse,
    AuditSearchResultItem,
    DecisionResultResponse,
    DecisionSubmitRequest,
    DecisionType,
    ErrorDetail,
    HealthResponse,
    PendingApprovalsListResponse,
    RiskLevel,
)


class TestRiskLevelEnum:
    """Validate RiskLevel enum definitions."""

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "LOW"
        assert RiskLevel.MEDIUM.value == "MEDIUM"
        assert RiskLevel.HIGH.value == "HIGH"
        assert RiskLevel.CRITICAL.value == "CRITICAL"


class TestApprovalStatusEnum:
    """Validate ApprovalStatus enum values."""

    def test_status_values(self):
        assert ApprovalStatus.PENDING_APPROVAL.value == "pending_approval"
        assert ApprovalStatus.AUTO_APPROVED.value == "auto_approved"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.MODIFIED.value == "modified"
        assert ApprovalStatus.COMPLETED.value == "completed"
        assert ApprovalStatus.FAILED.value == "failed"


class TestDecisionTypeEnum:
    """Validate DecisionType enum values."""

    def test_decision_values(self):
        assert DecisionType.APPROVE.value == "approve"
        assert DecisionType.REJECT.value == "reject"
        assert DecisionType.MODIFY.value == "modify"


class TestActionSubmitRequest:
    """Validate ActionSubmitRequest validation rules."""

    def test_valid_minimal_action_request(self):
        req = ActionSubmitRequest(
            action_type="query_database",
            description="Fetch user account details",
        )
        assert req.action_type == "query_database"
        assert req.description == "Fetch user account details"
        assert req.payload == {}
        assert req.risk_override is None

    def test_valid_full_action_request(self):
        req = ActionSubmitRequest(
            action_type="drop_table",
            description="Remove obsolete temporary cache table",
            payload={"table": "temp_cache", "dry_run": False},
            risk_override=RiskLevel.CRITICAL,
        )
        assert req.risk_override == RiskLevel.CRITICAL
        assert req.payload["table"] == "temp_cache"

    def test_action_type_too_short_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            ActionSubmitRequest(
                action_type="x",
                description="Valid description string here",
            )
        assert "action_type" in str(exc.value)

    def test_description_too_short_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            ActionSubmitRequest(
                action_type="update_user",
                description="tiny",
            )
        assert "description" in str(exc.value)

    def test_missing_required_fields_raises_error(self):
        with pytest.raises(ValidationError):
            ActionSubmitRequest()


class TestDecisionSubmitRequest:
    """Validate DecisionSubmitRequest business logic constraints."""

    def test_valid_approve_decision(self):
        req = DecisionSubmitRequest(
            decision=DecisionType.APPROVE,
            decision_by="admin_alice",
            decision_reason="Verified authorization ticket #1024",
        )
        assert req.decision == DecisionType.APPROVE
        assert req.decision_by == "admin_alice"

    def test_valid_reject_decision_with_reason(self):
        req = DecisionSubmitRequest(
            decision=DecisionType.REJECT,
            decision_by="security_bob",
            decision_reason="Missing secondary sign-off for destructive change",
        )
        assert req.decision == DecisionType.REJECT
        assert req.decision_reason is not None

    def test_reject_decision_without_reason_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            DecisionSubmitRequest(
                decision=DecisionType.REJECT,
                decision_by="security_bob",
                decision_reason=None,
            )
        assert "decision_reason is required when rejecting" in str(exc.value)

    def test_reject_decision_with_empty_whitespace_reason_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            DecisionSubmitRequest(
                decision=DecisionType.REJECT,
                decision_by="security_bob",
                decision_reason="   ",
            )
        assert "decision_reason is required when rejecting" in str(exc.value)

    def test_valid_modify_decision_with_payload(self):
        req = DecisionSubmitRequest(
            decision=DecisionType.MODIFY,
            decision_by="operator_charlie",
            decision_reason="Restricted query limit to prevent memory spike",
            modified_payload={"limit": 50, "dry_run": True},
        )
        assert req.decision == DecisionType.MODIFY
        assert req.modified_payload == {"limit": 50, "dry_run": True}

    def test_modify_decision_without_payload_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            DecisionSubmitRequest(
                decision=DecisionType.MODIFY,
                decision_by="operator_charlie",
                decision_reason="Should fail without modified_payload",
                modified_payload=None,
            )
        assert "modified_payload is required" in str(exc.value)

    def test_modify_decision_with_empty_payload_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            DecisionSubmitRequest(
                decision=DecisionType.MODIFY,
                decision_by="operator_charlie",
                decision_reason="Should fail with empty dict",
                modified_payload={},
            )
        assert "modified_payload is required and cannot be empty" in str(exc.value)


class TestResponseSchemas:
    """Validate response schema serializations."""

    def test_approval_request_response_serialization(self):
        resp = ApprovalRequestResponse(
            id="req_001",
            thread_id="thread_001",
            action_type="resize_disk",
            risk_level=RiskLevel.MEDIUM,
            description="Resize EBS volume from 100GB to 200GB",
            payload={"volume_id": "vol-12345", "size_gb": 200},
            status=ApprovalStatus.PENDING_APPROVAL,
            created_at="2026-11-02T12:00:00Z",
        )
        dump = resp.model_dump()
        assert dump["id"] == "req_001"
        assert dump["risk_level"] == "MEDIUM"
        assert dump["status"] == "pending_approval"
        assert dump["checkpoint_state"] is None

    def test_pending_list_response(self):
        item = ApprovalRequestResponse(
            id="req_002",
            thread_id="thread_002",
            action_type="delete_user",
            risk_level=RiskLevel.HIGH,
            description="Delete inactive user profile",
            payload={"user_id": "u-99"},
            status=ApprovalStatus.PENDING_APPROVAL,
            created_at="2026-11-02T12:05:00Z",
        )
        container = PendingApprovalsListResponse(items=[item], count=1)
        assert container.count == 1
        assert container.items[0].id == "req_002"

    def test_decision_result_response(self):
        res = DecisionResultResponse(
            request_id="req_001",
            thread_id="thread_001",
            status=ApprovalStatus.COMPLETED,
            decision=DecisionType.APPROVE,
            decision_by="admin_alice",
            result="Successfully resized disk to 200GB",
            message="Request processed",
        )
        assert res.status == ApprovalStatus.COMPLETED
        assert res.decision == DecisionType.APPROVE

    def test_audit_search_response(self):
        item = AuditSearchResultItem(
            id="req_001",
            thread_id="thread_001",
            action_type="drop_table",
            risk_level="CRITICAL",
            description="Drop staging table",
            status="completed",
            decision="approve",
            decision_reason="Maintenance ticket approved",
            result="Dropped table staging",
            snippet="<b>drop</b> table staging",
            bm25_score=-1.25,
        )
        sr = AuditSearchResponse(query="drop", count=1, results=[item])
        assert sr.query == "drop"
        assert sr.results[0].bm25_score == -1.25

    def test_health_response(self):
        hr = HealthResponse(
            status="ready",
            database={"status": "connected", "journal_mode": "wal"},
            environment="test",
            version="0.1.0",
        )
        assert hr.status == "ready"
        assert hr.database["journal_mode"] == "wal"

    def test_rfc7807_error_detail(self):
        err = ErrorDetail(
            type="https://example.com/errors/not-found",
            title="Resource Not Found",
            status=404,
            detail="The requested approval request does not exist",
            instance="/api/v1/approvals/req_missing",
        )
        dump = err.model_dump()
        assert dump["status"] == 404
        assert dump["title"] == "Resource Not Found"
        assert dump["instance"] == "/api/v1/approvals/req_missing"
