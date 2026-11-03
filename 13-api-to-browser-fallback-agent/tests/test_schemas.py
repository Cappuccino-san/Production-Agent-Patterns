"""Unit tests for Pydantic models, schemas, and enums."""

import pytest
from pydantic import ValidationError
from app.models import (
    ExecutionChannel,
    ExecutionLogEntry,
    RFC7807Error,
    WorkflowActionType,
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
    WorkflowStatus,
)


def test_workflow_enums():
    assert ExecutionChannel.API.value == "API"
    assert ExecutionChannel.BROWSER_FALLBACK.value == "BROWSER_FALLBACK"
    assert WorkflowStatus.COMPLETED_VIA_API.value == "COMPLETED_VIA_API"
    assert WorkflowStatus.COMPLETED_VIA_BROWSER_FALLBACK.value == "COMPLETED_VIA_BROWSER_FALLBACK"


def test_workflow_execution_request_validation():
    # Valid model
    req = WorkflowExecutionRequest(
        action=WorkflowActionType.FETCH_INVOICE,
        target_id="INV-9901",
        simulate_api_failure=True,
        simulated_failure_type="404",
    )
    assert req.target_id == "INV-9901"
    assert req.simulate_api_failure is True

    # Invalid target_id (too short)
    with pytest.raises(ValidationError):
        WorkflowExecutionRequest(target_id="x")


def test_execution_log_entry():
    entry = ExecutionLogEntry(
        log_id="log-123",
        execution_id="exec-456",
        channel=ExecutionChannel.API,
        step_name="DISPATCH",
        message="Request initiated",
    )
    assert entry.log_id == "log-123"
    assert entry.channel == ExecutionChannel.API
    assert "T" in entry.timestamp
