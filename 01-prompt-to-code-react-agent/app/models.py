"""Domain data transfer models and Pydantic v2 schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AgentRunRequest(BaseModel):
    """Request payload to trigger code generation agent run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Natural language instruction for code generation"
    )
    language: str = Field(
        default="python",
        description="Target programming language (defaults to python)"
    )
    max_iterations: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum ReAct thought-action iterations allowed"
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional execution thread / session ID"
    )


class CodeExecutionResult(BaseModel):
    """Result of AST syntax check and isolated execution."""

    is_valid: bool = Field(..., description="Whether syntax parsing succeeded")
    syntax_error: Optional[str] = Field(
        default=None,
        description="Syntax error message if syntax check failed"
    )
    execution_output: Optional[str] = Field(
        default=None,
        description="Captured stdout from sandbox execution"
    )
    execution_error: Optional[str] = Field(
        default=None,
        description="Runtime exception traceback if execution failed"
    )


class AgentRunResponse(BaseModel):
    """Structured response containing generated code, validation status, and execution output."""

    run_id: str = Field(..., description="Unique run identifier")
    prompt: str = Field(..., description="Original user prompt")
    language: str = Field(default="python", description="Target programming language")
    code: str = Field(..., description="Synthesized source code")
    is_valid: bool = Field(..., description="Whether final code is syntactically valid")
    output: Optional[str] = Field(
        default=None,
        description="Execution output or error summary"
    )
    iterations: int = Field(..., description="Total ReAct iterations executed")
    steps: list[str] = Field(
        default_factory=list,
        description="Trace of intermediate reasoning and action steps"
    )
    status: str = Field(default="completed", description="Run status (completed, failed)")
    created_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp of run completion"
    )


class RunSearchResult(BaseModel):
    """Full-text search hit from SQLite FTS5 BM25 search."""

    id: str = Field(..., description="Run ID")
    prompt: str = Field(..., description="Prompt text")
    code: str = Field(..., description="Generated code snippet")
    snippet: str = Field(..., description="FTS5 highlighted matching snippet")
    rank: float = Field(..., description="BM25 relevance score")


class HealthResponse(BaseModel):
    """Service health response."""

    status: str = Field(..., description="Overall service status (ok, healthy)")
    environment: str = Field(..., description="Runtime environment name")
    database: str = Field(..., description="Database connection and journal mode")
