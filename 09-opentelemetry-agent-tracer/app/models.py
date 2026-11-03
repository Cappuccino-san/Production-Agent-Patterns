"""Pydantic v2 domain schemas for OpenTelemetry Agent Telemetry and Tracing."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class SpanType(str, Enum):
    LLM_HOP = "LLM_HOP"
    TOOL_LATENCY = "TOOL_LATENCY"
    STATE_MUTATION = "STATE_MUTATION"
    CHAIN_RUN = "CHAIN_RUN"


class SpanAttributes(BaseModel):
    model_name: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    tool_name: Optional[str] = None
    state_delta: Optional[dict[str, Any]] = None
    status_code: int = 200
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSpan(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    span_type: SpanType
    name: str = Field(..., min_length=2, max_length=150)
    start_time: str
    end_time: str
    duration_ms: float
    attributes: SpanAttributes


class AgentTrace(BaseModel):
    trace_id: str
    agent_name: str
    root_span_id: str
    total_tokens: int
    total_duration_ms: float
    sink: str = "LangSmith"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spans: list[AgentSpan] = Field(default_factory=list)


class TraceRunRequest(BaseModel):
    agent_name: str = Field(default="ResearchPlannerAgent", min_length=2)
    prompt: str = Field(..., min_length=5, max_length=2000)
    destination_sink: str = Field(default="LangSmith", pattern="^(LangSmith|Arize|OTLP)$")


class SpanSearchHit(BaseModel):
    span_id: str
    trace_id: str
    span_type: str
    name: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
