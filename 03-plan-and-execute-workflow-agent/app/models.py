"""Pydantic v2 domain schemas and API contracts."""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    """Healthcheck probe response schema."""

    status: str = Field(..., description="Overall service status")
    version: str = Field(..., description="Application version")
    database: str = Field(..., description="Database connection health")
    environment: str = Field(..., description="Deployment environment")


class ErrorDetail(BaseModel):
    """RFC 7807 problem details schema."""

    type: str = Field(default="about:blank", description="URI reference identifying problem type")
    title: str = Field(..., description="Short, human-readable summary")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Human-readable explanation of error")
    instance: Optional[str] = Field(default=None, description="URI reference identifying occurrence")


class PlanStep(BaseModel):
    """Individual decomposed task step within a plan."""

    id: str = Field(..., description="Unique step identifier")
    plan_id: str = Field(..., description="Foreign key reference to parent plan")
    step_index: int = Field(..., ge=0, description="0-based sequence index")
    title: str = Field(..., min_length=1, max_length=200, description="Step title or action name")
    description: str = Field(..., min_length=1, max_length=2000, description="Detailed instruction or goal")
    tool: str = Field(default="general", description="Specialized tool or engine for execution")
    status: str = Field(
        default="pending",
        description="Current step status (pending, in_progress, completed, failed, skipped, replanned)",
    )
    result: Optional[str] = Field(default=None, description="Outcome or artifact produced by step")
    error: Optional[str] = Field(default=None, description="Error message if step failed")
    created_at: Optional[str] = Field(default=None, description="Creation ISO timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last update ISO timestamp")

    model_config = ConfigDict(extra="forbid")


class PlanCreate(BaseModel):
    """Request payload to create a new decomposed plan."""

    goal: str = Field(..., min_length=3, max_length=1000, description="High-level user objective or goal")
    context: Optional[dict[str, Any]] = Field(default=None, description="Optional metadata or background context")

    @field_validator("goal")
    @classmethod
    def validate_goal_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Goal must not be empty or whitespace only")
        return stripped

    model_config = ConfigDict(extra="forbid")


class PlanResponse(BaseModel):
    """Response containing plan details and step execution state."""

    id: str = Field(..., description="Unique plan ID")
    goal: str = Field(..., description="High-level goal")
    status: str = Field(..., description="Plan status (created, in_progress, completed, failed, replanned)")
    total_steps: int = Field(..., ge=0, description="Total count of steps in plan")
    current_step_index: int = Field(..., ge=0, description="Index of currently active step")
    steps: list[PlanStep] = Field(default_factory=list, description="Ordered list of plan steps")
    final_response: Optional[str] = Field(default=None, description="Consolidated plan deliverable")
    created_at: str = Field(..., description="Creation ISO timestamp")
    updated_at: str = Field(..., description="Last update ISO timestamp")

    model_config = ConfigDict(extra="forbid")


class PlanExecuteRequest(BaseModel):
    """Payload to trigger execution of a plan."""

    plan_id: Optional[str] = Field(default=None, description="ID of plan to execute (optional if in path)")
    max_iterations: Optional[int] = Field(default=None, ge=1, le=50, description="Max execution iterations")
    allow_replanning: bool = Field(default=True, description="Whether to allow adaptive replanning on failure")

    model_config = ConfigDict(extra="forbid")


class StepExecutionResult(BaseModel):
    """Outcome of a single step execution."""

    step_index: int = Field(..., ge=0, description="Step index")
    title: str = Field(..., description="Step title")
    tool: str = Field(..., description="Tool used")
    status: str = Field(..., description="Step outcome status")
    result: Optional[str] = Field(default=None, description="Result output")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    model_config = ConfigDict(extra="forbid")


class PlanExecuteResponse(BaseModel):
    """Response after executing a plan."""

    plan_id: str = Field(..., description="Plan ID")
    goal: str = Field(..., description="Original goal")
    status: str = Field(..., description="Final plan status")
    completed: bool = Field(..., description="Whether all steps completed successfully")
    iterations: int = Field(..., ge=0, description="Total iterations performed")
    steps: list[PlanStep] = Field(default_factory=list, description="Updated steps list")
    response: Optional[str] = Field(default=None, description="Final synthesized summary or response")

    model_config = ConfigDict(extra="forbid")


class PlanSearchResult(BaseModel):
    """Full-text search result for matching plan steps and logs."""

    plan_id: str = Field(..., description="Parent plan ID")
    step_id: str = Field(..., description="Matching step ID")
    step_index: int = Field(..., description="Step index")
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="Step description")
    result: Optional[str] = Field(default=None, description="Execution result")
    score: float = Field(..., description="BM25 rank score (lower is more relevant in SQLite bm25())")
    snippet: str = Field(..., description="Highlighted text snippet from FTS5")

    model_config = ConfigDict(extra="forbid")
