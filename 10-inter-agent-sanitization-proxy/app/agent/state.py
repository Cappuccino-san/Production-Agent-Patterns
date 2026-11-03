"""Typed LangGraph state for Inter-Agent Sanitization Proxy."""

from typing import Annotated, Any, Optional, TypedDict
from app.models import ActionTaken, SanitizationResult


def merge_audit(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return existing + new_items


class ProxyCommunicationState(TypedDict):
    message_id: str
    sender_agent: str
    receiver_agent: str
    raw_content: str
    sanitized_content: str
    action_taken: ActionTaken
    risk_score: float
    matched_rules: list[str]
    delivered: bool
    audit_trail: Annotated[list[dict[str, Any]], merge_audit]
