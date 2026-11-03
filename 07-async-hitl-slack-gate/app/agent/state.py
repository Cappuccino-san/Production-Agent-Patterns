"""Typed LangGraph state for Async HITL Slack Gate."""

from typing import Annotated, Any, Optional, TypedDict
from app.models import ActionType, GateStatus


def merge_audit(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return existing + new_items


class HITLGateState(TypedDict):
    action_id: str
    action_type: ActionType
    description: str
    target_system: str
    risk_score: float
    payload: dict[str, Any]
    status: GateStatus
    expires_at: str
    created_at: str
    updated_at: str
    approver_id: Optional[str]
    decision: Optional[str]  # "approve", "reject", "timeout"
    decision_reason: Optional[str]
    execution_result: Optional[dict[str, Any]]
    slack_blocks: Optional[dict[str, Any]]
    audit_trail: Annotated[list[dict[str, Any]], merge_audit]
