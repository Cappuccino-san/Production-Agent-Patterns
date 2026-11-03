"""Pydantic v2 domain schemas for Trajectory Evaluation and Golden DAG CI Gating."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class EvalVerdict(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class GoldenDAG(BaseModel):
    dag_id: str = Field(..., min_length=3, max_length=100)
    name: str = Field(..., min_length=3, max_length=200)
    allowed_nodes: list[str] = Field(..., min_length=1)
    # Directed edges: list of [source_node, target_node]
    allowed_transitions: list[list[str]] = Field(default_factory=list)
    initial_nodes: list[str] = Field(..., min_length=1)
    terminal_nodes: list[str] = Field(..., min_length=1)
    strict_topology: bool = True


class AgentTrajectory(BaseModel):
    trajectory_id: str
    pr_number: int
    commit_sha: str
    tool_call_sequence: list[str] = Field(..., min_length=1)


class TrajectoryDeviation(BaseModel):
    trajectory_id: str
    step_index: int
    expected_transitions: list[str]
    actual_tool_call: str
    error_reason: str


class EvalRunRequest(BaseModel):
    dag_id: str
    pr_number: int
    commit_sha: str
    trajectories: list[AgentTrajectory] = Field(..., min_length=1)


class EvalRunResponse(BaseModel):
    eval_id: str
    pr_number: int
    commit_sha: str
    dag_id: str
    total_evaluated: int
    passed_count: int
    failed_count: int
    verdict: EvalVerdict
    deviations: list[TrajectoryDeviation] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TrajectorySearchHit(BaseModel):
    log_id: str
    eval_id: str
    trajectory_id: str
    is_match: int
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
