"""Pydantic v2 domain schemas for Shadow Trajectory Comparator."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class CandidateTopology(str, Enum):
    STANDARD_REACT = "STANDARD_REACT"
    PARALLEL_SPECULATIVE_REACT = "PARALLEL_SPECULATIVE_REACT"
    HIERARCHICAL_DECOMPOSITION = "HIERARCHICAL_DECOMPOSITION"


class ComparisonRecommendation(str, Enum):
    DEPLOY_CANDIDATE = "DEPLOY_CANDIDATE"
    REJECT_REGRESSION = "REJECT_REGRESSION"
    NEUTRAL = "NEUTRAL"


class ToolCallRecord(BaseModel):
    step_index: int
    tool_name: str
    input_arguments: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    status: str = "SUCCESS"


class TrajectorySummary(BaseModel):
    topology_name: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    final_output: str = ""


class AgentTrafficRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    force_shadow: bool = Field(default=False, description="Force shadow comparison regardless of 5% sample rate")


class AgentTrafficResponse(BaseModel):
    request_id: str
    prompt: str
    primary_output: str
    primary_cost_usd: float
    primary_latency_ms: float
    is_shadow_sampled: bool
    shadow_comparison_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ShadowComparisonReport(BaseModel):
    comparison_id: str
    request_id: str
    prompt: str
    primary_trajectory: TrajectorySummary
    candidate_trajectory: TrajectorySummary
    path_similarity_score: float = Field(ge=0.0, le=1.0)
    cost_delta_usd: float
    cost_savings_pct: float
    latency_delta_ms: float
    recommendation: ComparisonRecommendation
    diff_summary: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ComparatorSearchHit(BaseModel):
    record_id: str
    comparison_id: str
    request_id: str
    recommendation: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
