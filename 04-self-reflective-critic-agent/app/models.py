"""Pydantic v2 schemas for the Reflexion Actor-Critic Agent."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RubricCriterion(BaseModel):
    """Evaluation criterion definition for critic scoring."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Name of the criterion (e.g. correctness, completeness, clarity, efficiency)",
    )
    weight: float = Field(
        default=1.0,
        gt=0.0,
        le=10.0,
        description="Relative weight in composite score calculation",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Explanation or expectation for this criterion",
    )


class EvaluationResult(BaseModel):
    """Structured evaluation output produced by the CriticNode."""

    model_config = ConfigDict(extra="forbid")

    criteria_scores: dict[str, float] = Field(
        ..., description="Calibrated numerical score (0.0 - 100.0) per criterion"
    )
    composite_score: float = Field(
        ..., ge=0.0, le=100.0, description="Weighted composite score (0.0 - 100.0)"
    )
    critique: str = Field(..., description="Actionable critique assessment and reasoning")
    defects: list[str] = Field(
        default_factory=list, description="Concrete identified shortcomings"
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Actionable recommendations for the next revision"
    )
    passed: bool = Field(..., description="Whether composite score met or exceeded threshold")


class ReflectionStep(BaseModel):
    """A single iteration snapshot recorded during the reflexion loop."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = Field(default=None, description="Unique reflection ID")
    session_id: Optional[str] = Field(default=None, description="Parent session identifier")
    iteration: int = Field(..., ge=1, description="Iteration index")
    draft: str = Field(..., description="Draft text or solution at this iteration")
    critique: str = Field(..., description="Critique produced for this draft")
    rubric_scores: dict[str, float] = Field(
        ..., description="Scores breakdown by criterion"
    )
    composite_score: float = Field(
        ..., ge=0.0, le=100.0, description="Composite score for this draft"
    )
    status: str = Field(..., description="Step outcome status")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")



class ReflectionExecuteRequest(BaseModel):
    """Payload to initiate an iterative reflection loop on a task."""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Problem, task, or prompt to solve and refine",
    )
    threshold: float = Field(
        default=85.0,
        ge=0.0,
        le=100.0,
        description="Composite score required for early stopping",
    )
    max_iterations: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum refinement iterations before terminating",
    )
    custom_rubric: Optional[list[RubricCriterion]] = Field(
        default=None,
        description="Optional list of custom criteria and weights",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Optional seed for deterministic generation control",
    )


class ReflectionExecuteResponse(BaseModel):
    """Response returned upon completion of the reflection loop."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Unique session identifier")
    task: str = Field(..., description="Initial task prompt")
    status: str = Field(
        ..., description="Final session status ('completed' or 'max_iterations_reached')"
    )
    iterations_count: int = Field(..., description="Total iterations performed")
    final_score: float = Field(..., description="Final composite score achieved")
    final_draft: str = Field(..., description="Final refined output")
    history: list[ReflectionStep] = Field(
        default_factory=list, description="Chronological revision history"
    )


class StandaloneEvaluateRequest(BaseModel):
    """Payload for standalone evaluation of candidate text without running full loop."""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Task or prompt context against which candidate text is evaluated",
    )
    candidate_text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Candidate text or code to evaluate",
    )
    rubric: Optional[list[RubricCriterion]] = Field(
        default=None,
        description="Optional custom rubric criteria",
    )
    threshold: float = Field(
        default=85.0,
        ge=0.0,
        le=100.0,
        description="Passing score threshold",
    )


class StandaloneEvaluateResponse(BaseModel):
    """Response returned by standalone critic evaluation."""

    model_config = ConfigDict(extra="forbid")

    task: str
    candidate_text: str
    evaluation: EvaluationResult


class SessionDetailResponse(BaseModel):
    """Detailed session view with all iterations and reflections."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Session identifier")
    task: str = Field(..., description="Task prompt")
    rubric: Optional[str] = Field(default=None, description="Serialized rubric details")
    threshold: float = Field(..., description="Passing threshold")
    status: str = Field(..., description="Current session status")
    final_score: Optional[float] = Field(default=None, description="Final composite score")
    iterations: list[ReflectionStep] = Field(
        default_factory=list, description="All recorded revision iterations"
    )
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class SearchResultItem(BaseModel):
    """A single full-text search match from reflections_fts."""

    model_config = ConfigDict(extra="forbid")

    reflection_id: str
    session_id: str
    iteration: int
    draft: str
    critique: str
    rubric_scores: dict[str, float]
    composite_score: float
    score: float = Field(..., description="FTS5 BM25 relevance score (lower is more relevant)")
    snippet: str = Field(..., description="Highlighted text snippet from FTS5")


class SearchReflectionsResponse(BaseModel):
    """Search query response containing ranked reflection results."""

    model_config = ConfigDict(extra="forbid")

    query: str
    total_results: int
    results: list[SearchResultItem]


class LiveResponse(BaseModel):
    """Liveness probe response."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str


class ReadyResponse(BaseModel):
    """Readiness probe response with database diagnostic metrics."""

    model_config = ConfigDict(extra="forbid")

    status: str
    database: str
    journal_mode: str
    sessions_count: int
    reflections_count: int


class ErrorDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs error model."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., description="URI reference identifying the problem type")
    title: str = Field(..., description="Short summary of the problem type")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Human-readable explanation of the error")
    instance: str = Field(..., description="URI reference identifying specific occurrence")

