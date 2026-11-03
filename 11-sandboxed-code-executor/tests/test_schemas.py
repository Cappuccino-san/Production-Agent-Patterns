"""Tier 1: Pydantic Schema Validation Tests for Sandboxed Executor."""

import pytest
from pydantic import ValidationError
from app.models import (
    CodeInterpreterTask,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    RFC7807Error,
)


class TestSchemas:
    def test_execution_request_valid(self):
        req = ExecutionRequest(code="print('Hello World')", timeout_seconds=4.0)
        assert req.code == "print('Hello World')"
        assert req.timeout_seconds == 4.0

    def test_execution_request_invalid_timeout(self):
        with pytest.raises(ValidationError):
            ExecutionRequest(code="x = 1", timeout_seconds=50.0)  # Exceeds 30.0

    def test_execution_result_model(self):
        res = ExecutionResult(
            execution_id="exec-123",
            status=ExecutionStatus.SUCCESS,
            exit_code=0,
            stdout="Output line\n",
            stderr="",
            execution_time_ms=12.5,
            egress_blocked=True,
        )
        assert res.status == ExecutionStatus.SUCCESS
        assert res.egress_blocked is True

    def test_code_interpreter_task_model(self):
        task = CodeInterpreterTask(prompt="Calculate the first 10 Fibonacci numbers")
        assert task.language == "python"

    def test_rfc7807_error_model(self):
        err = RFC7807Error(
            title="Syntax Error",
            status=422,
            detail="Failed to parse Python code",
        )
        assert err.status == 422
