"""Domain models, Pydantic schemas, and RFC 7807 error structures."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class RiskLevel(str, Enum):
    """Categorical risk classification for requested actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(str, Enum):
    """Lifecycle status of an approval request."""

    PENDING_APPROVAL = "pending_approval"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    COMPLETED = "completed"
    FAILED = "failed"


class DecisionType(str, Enum):
    """Human review decision."""

    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"


# ==============================================================================
# Request DTOs
# ==============================================================================


class ActionSubmitRequest(BaseModel):
    """Payload to submit a new agent action request."""

    action_type: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Type or name of the action to execute (e.g. query_database, drop_table)",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Detailed description or user intent for the action",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters, query strings, or payload objects for the action",
    )
    risk_override: Optional[RiskLevel] = Field(
        default=None,
        description="Explicit risk level override bypassing automated classification",
    )


class DecisionSubmitRequest(BaseModel):
    """Payload for human reviewer decision."""

    decision: DecisionType = Field(
        ...,
        description="Review decision: approve, reject, or modify",
    )
    decision_by: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Username or identifier of the human reviewer",
    )
    decision_reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Justification, rejection rationale, or note from the reviewer",
    )
    modified_payload: Optional[dict[str, Any]] = Field(
        default=None,
        description="Updated parameters required when decision is 'modify'",
    )

    @model_validator(mode="after")
    def validate_decision_rules(self) -> "DecisionSubmitRequest":
        """Enforce business rules for modify and reject decisions."""
        if self.decision == DecisionType.MODIFY:
            if not self.modified_payload:
                raise ValueError("modified_payload is required and cannot be empty when decision is 'modify'")
        if self.decision == DecisionType.REJECT:
            if not self.decision_reason or not self.decision_reason.strip():
                raise ValueError("decision_reason is required when rejecting an action request")
        return self


# ==============================================================================
# Response DTOs
# ==============================================================================


class ApprovalRequestResponse(BaseModel):
    """Complete detail view of an approval request."""

    id: str = Field(..., description="Unique approval request ID")
    thread_id: str = Field(..., description="LangGraph execution thread ID")
    action_type: str = Field(..., description="Action type")
    risk_level: RiskLevel = Field(..., description="Assessed risk level")
    description: str = Field(..., description="Action description")
    payload: dict[str, Any] = Field(..., description="Action parameters")
    status: ApprovalStatus = Field(..., description="Current lifecycle status")
    decision: Optional[DecisionType] = Field(default=None, description="Human decision rendered")
    decision_reason: Optional[str] = Field(default=None, description="Review reason or note")
    decision_by: Optional[str] = Field(default=None, description="Reviewer name")
    result: Optional[str] = Field(default=None, description="Execution outcome or rejection notice")
    execution_logs: list[str] = Field(default_factory=list, description="Execution audit log trail")
    created_at: str = Field(..., description="Timestamp of request submission")
    decided_at: Optional[str] = Field(default=None, description="Timestamp of review decision")
    completed_at: Optional[str] = Field(default=None, description="Timestamp of action completion")
    checkpoint_state: Optional[dict[str, Any]] = Field(
        default=None,
        description="Current LangGraph thread checkpoint details if present",
    )


class PendingApprovalsListResponse(BaseModel):
    """Collection response of approval requests pending human review."""

    items: list[ApprovalRequestResponse]
    count: int


class DecisionResultResponse(BaseModel):
    """Response returned upon submitting a review decision."""

    request_id: str
    thread_id: str
    status: ApprovalStatus
    decision: DecisionType
    decision_by: str
    result: Optional[str] = None
    message: str


class AuditSearchResultItem(BaseModel):
    """Single item matched in full-text search audit query."""

    id: str
    thread_id: str
    action_type: str
    risk_level: str
    description: str
    status: str
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    result: Optional[str] = None
    snippet: Optional[str] = None
    bm25_score: float


class AuditSearchResponse(BaseModel):
    """Results of BM25 full-text search over audit log."""

    query: str
    count: int
    results: list[AuditSearchResultItem]


class HealthResponse(BaseModel):
    """Service health and database readiness information."""

    status: str
    database: dict[str, Any]
    environment: str
    version: str


class ErrorDetail(BaseModel):
    """RFC 7807 compliant Problem Details error model."""

    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type",
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the problem type",
    )
    status: int = Field(
        ...,
        description="HTTP status code generated by the origin server",
    )
    detail: str = Field(
        ...,
        description="Human-readable explanation specific to this occurrence",
    )
    instance: Optional[str] = Field(
        default=None,
        description="URI reference identifying the specific occurrence of the problem",
    )
