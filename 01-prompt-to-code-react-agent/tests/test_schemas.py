"""Tier 1: Pydantic Schema Validation & Boundary Tests."""

import pytest
from pydantic import ValidationError

from app.models import (
    AgentRunRequest,
    AgentRunResponse,
    CodeExecutionResult,
    HealthResponse,
    RunSearchResult,
)


@pytest.mark.unit
def test_agent_run_request_valid() -> None:
    """Verify AgentRunRequest parses and validates correct payloads."""
    req = AgentRunRequest(
        prompt="Write a function to compute primes",
        language="python",
        max_iterations=4,
        thread_id="thread-101",
    )
    assert req.prompt == "Write a function to compute primes"
    assert req.language == "python"
    assert req.max_iterations == 4
    assert req.thread_id == "thread-101"


@pytest.mark.unit
def test_agent_run_request_defaults() -> None:
    """Verify default values for language and max_iterations."""
    req = AgentRunRequest(prompt="Synthesize code")
    assert req.language == "python"
    assert req.max_iterations == 5
    assert req.thread_id is None


@pytest.mark.unit
def test_agent_run_request_empty_prompt_raises() -> None:
    """Verify empty prompt raises Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="")


@pytest.mark.unit
def test_agent_run_request_whitespace_stripping() -> None:
    """Verify prompt whitespace is stripped cleanly."""
    req = AgentRunRequest(prompt="   Calculate total   ")
    assert req.prompt == "Calculate total"


@pytest.mark.unit
def test_agent_run_request_bounds() -> None:
    """Verify bounds on max_iterations (1 <= max_iterations <= 20)."""
    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="Test", max_iterations=0)

    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="Test", max_iterations=25)


@pytest.mark.unit
def test_agent_run_request_extra_fields_forbidden() -> None:
    """Verify extra fields are forbidden by model configuration."""
    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="Test", unauthorized_field="malicious")


@pytest.mark.unit
def test_code_execution_result() -> None:
    """Verify CodeExecutionResult schema and optional error fields."""
    res = CodeExecutionResult(
        is_valid=True,
        execution_output="Result: 42",
    )
    assert res.is_valid is True
    assert res.execution_output == "Result: 42"
    assert res.syntax_error is None

    err_res = CodeExecutionResult(
        is_valid=False,
        syntax_error="SyntaxError: unexpected EOF",
    )
    assert err_res.is_valid is False
    assert err_res.syntax_error == "SyntaxError: unexpected EOF"


@pytest.mark.unit
def test_agent_run_response_serialization() -> None:
    """Verify AgentRunResponse serializes to dict and JSON cleanly."""
    resp = AgentRunResponse(
        run_id="run_12345",
        prompt="Write factorial",
        language="python",
        code="def factorial(n): return 1",
        is_valid=True,
        output="1",
        iterations=1,
        steps=["Thought: Simple solution", "Action: Synthesized code"],
        status="completed",
        created_at="2026-11-02T21:40:00",
    )
    dumped = resp.model_dump()
    assert dumped["run_id"] == "run_12345"
    assert len(dumped["steps"]) == 2
    assert "code" in dumped

    json_str = resp.model_dump_json()
    assert "run_12345" in json_str


@pytest.mark.unit
def test_run_search_result() -> None:
    """Verify RunSearchResult schema instantiation."""
    hit = RunSearchResult(
        id="run_abc",
        prompt="Find Fibonacci",
        code="def fib(): ...",
        snippet="<b>Fibonacci</b> function",
        rank=-1.45,
    )
    assert hit.id == "run_abc"
    assert hit.rank == -1.45


@pytest.mark.unit
def test_health_response_schema() -> None:
    """Verify HealthResponse schema."""
    health = HealthResponse(
        status="healthy",
        environment="test",
        database="connected (journal_mode=wal)",
    )
    assert health.status == "healthy"
    assert "journal_mode=wal" in health.database
