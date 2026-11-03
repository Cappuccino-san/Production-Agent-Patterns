"""Pydantic v2 schemas for Sandboxed Code Execution and Code-Interpreter Agent."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    RUNTIME_ERROR = "RUNTIME_ERROR"


class ExecutionRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=20000, description="Python code to execute")
    timeout_seconds: Optional[float] = Field(default=5.0, ge=0.5, le=30.0)


class ExecutionResult(BaseModel):
    execution_id: str
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    egress_blocked: bool = True
    ast_violations: list[str] = Field(default_factory=list)
    executed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CodeInterpreterTask(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=2000)
    language: str = Field(default="python", pattern="^python$")
    timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)


class ExecutionSearchHit(BaseModel):
    execution_id: str
    status: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
