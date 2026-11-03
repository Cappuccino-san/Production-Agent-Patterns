"""Pydantic v2 schemas for Cost Kill-Switch and Model Fallback Middleware."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class CostStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FALLBACK_ENGAGED = "FALLBACK_ENGAGED"
    HALTED_BUDGET_EXCEEDED = "HALTED_BUDGET_EXCEEDED"
    COMPLETED = "COMPLETED"


class CostLedgerEntry(BaseModel):
    ledger_id: str
    request_id: str
    step_index: int
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    step_cost_usd: float
    cumulative_cost_usd: float
    loop_depth: int
    kill_switch_active: bool
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentTaskRunRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    force_spend_spike: bool = Field(default=False, description="Simulate massive token output to test $0.50 kill switch")
    max_iterations: int = Field(default=5, ge=1, le=10)


class AgentTaskRunResponse(BaseModel):
    request_id: str
    prompt: str
    initial_model: str
    final_model: str
    total_tokens: int
    total_cost_usd: float
    loop_depth: int
    status: CostStatus
    kill_switch_triggered: bool
    fallback_engaged: bool
    final_output: str
    ledger: list[CostLedgerEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CostSearchHit(BaseModel):
    record_id: str
    request_id: str
    final_model: str
    status: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
