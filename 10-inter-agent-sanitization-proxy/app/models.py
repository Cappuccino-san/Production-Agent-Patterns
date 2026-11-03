"""Pydantic v2 domain schemas for Inter-Agent Sanitization Proxy."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionTaken(str, Enum):
    PASSED = "PASSED"
    SANITIZED = "SANITIZED"
    BLOCKED_QUARANTINE = "BLOCKED_QUARANTINE"


class MessagePacket(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:17]}")
    sender_agent: str = Field(..., min_length=2, max_length=100)
    receiver_agent: str = Field(..., min_length=2, max_length=100)
    content: str = Field(..., min_length=1, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SanitizationResult(BaseModel):
    message_id: str
    sender_agent: str
    receiver_agent: str
    is_clean: bool
    sanitized_content: str
    risk_score: float
    action_taken: ActionTaken
    matched_rules: list[str] = Field(default_factory=list)
    processed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProxySearchHit(BaseModel):
    message_id: str
    sender_agent: str
    receiver_agent: str
    action_taken: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
