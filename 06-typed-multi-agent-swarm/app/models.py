"""Pydantic v2 domain schemas and data transfer objects for Typed Multi-Agent Swarm."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class SwarmStatus(str, Enum):
    PENDING = "PENDING"
    RESEARCHING = "RESEARCHING"
    CODING = "CODING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ResearchFinding(BaseModel):
    """Strictly typed packet emitted by the Researcher Agent."""
    topic: str = Field(..., min_length=3, max_length=200, description="Core topic researched")
    key_points: list[str] = Field(..., min_length=1, description="Key architectural findings")
    recommendations: list[str] = Field(default_factory=list, description="Implementation suggestions")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of packet emission",
    )


class CodeArtifact(BaseModel):
    """Strictly typed packet emitted by the Coder Agent."""
    filename: str = Field(..., min_length=1, max_length=255, description="Primary output file name")
    language: str = Field(..., min_length=1, max_length=50, description="Programming language")
    code: str = Field(..., min_length=10, description="Executable code content")
    test_cases: str = Field(..., min_length=10, description="Unit test verification code")
    dependencies: list[str] = Field(default_factory=list, description="Required libraries")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of packet emission",
    )


class ReviewAssessment(BaseModel):
    """Strictly typed packet emitted by the Reviewer Agent."""
    approved: bool = Field(..., description="Whether the code artifact meets quality standards")
    score: float = Field(..., ge=0.0, le=100.0, description="Quality score from 0 to 100")
    critiques: list[str] = Field(default_factory=list, description="Specific defect observations")
    suggested_fixes: list[str] = Field(default_factory=list, description="Actionable remediations")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of review emission",
    )


class SwarmStepLog(BaseModel):
    """Audit log item representing a typed packet exchange between swarm nodes."""
    step_id: str
    agent_role: str
    action: str
    packet_type: str
    payload: dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SwarmTaskRequest(BaseModel):
    """Payload for submitting a new multi-agent swarm task."""
    task_description: str = Field(..., min_length=5, max_length=2000, description="Task specification")
    context: Optional[str] = Field(default=None, max_length=5000, description="Additional system context")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max review-fix iterations")


class SwarmTaskResponse(BaseModel):
    """Detailed response containing full task status and typed packets."""
    task_id: str
    task_description: str
    status: SwarmStatus
    iteration: int
    max_iterations: int
    research: Optional[ResearchFinding] = None
    code: Optional[CodeArtifact] = None
    review: Optional[ReviewAssessment] = None
    history: list[SwarmStepLog] = Field(default_factory=list)
    execution_time_ms: float = 0.0


class ArtifactSearchHit(BaseModel):
    """Result item from FTS5 BM25 search across swarm artifacts."""
    artifact_id: str
    task_id: str
    artifact_type: str
    title: str
    content_snippet: str
    rank: float


class RFC7807Error(BaseModel):
    """RFC 7807 problem details specification error model."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
