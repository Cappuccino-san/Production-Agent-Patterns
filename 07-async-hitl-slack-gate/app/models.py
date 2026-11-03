"""Pydantic v2 schemas for Async HITL Slack Gate."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    DEPLOY_PRODUCTION = "DEPLOY_PRODUCTION"
    DATABASE_MIGRATION = "DATABASE_MIGRATION"
    MASS_REFUND = "MASS_REFUND"
    PRIVILEGED_ACCESS_GRANT = "PRIVILEGED_ACCESS_GRANT"


class GateStatus(str, Enum):
    DRAFTED = "DRAFTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class HighStakesActionDraft(BaseModel):
    action_type: ActionType
    description: str = Field(..., min_length=5, max_length=1000)
    target_system: str = Field(..., min_length=2, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    risk_score: float = Field(..., ge=0.0, le=100.0)


class SlackInteractiveWebhook(BaseModel):
    action_id: str
    user_id: str = Field(..., min_length=2, max_length=50)
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: Optional[str] = Field(default=None, max_length=500)


class GateActionRecord(BaseModel):
    action_id: str
    action_type: ActionType
    status: GateStatus
    risk_score: float
    description: str
    payload: dict[str, Any]
    expires_at: str
    created_at: str
    updated_at: str
    approver_id: Optional[str] = None
    decision_reason: Optional[str] = None
    execution_result: Optional[dict[str, Any]] = None


class GateAuditLog(BaseModel):
    audit_id: str
    action_id: str
    decision: str
    approver_id: str
    note: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditSearchHit(BaseModel):
    audit_id: str
    action_id: str
    decision: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
