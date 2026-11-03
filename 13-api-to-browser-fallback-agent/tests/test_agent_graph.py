"""Tests for LangGraph fallback routing engine."""

import pytest
from app.agent.graph import build_fallback_graph
from app.agent.state import FallbackState
from app.models import (
    ExecutionChannel,
    WorkflowActionType,
    WorkflowStatus,
)


def test_graph_api_success_path():
    graph = build_fallback_graph()
    initial_state = FallbackState(
        execution_id="test-api-success-001",
        action=WorkflowActionType.FETCH_INVOICE,
        target_id="INV-2026-OK",
        api_endpoint="https://api.internal/v1/invoices",
        gui_url="https://portal.internal/invoices",
        simulate_api_failure=False,
    )

    result = graph.invoke(initial_state)

    assert result["fallback_triggered"] is False
    assert result["execution_channel"] == ExecutionChannel.API
    assert result["status"] == WorkflowStatus.COMPLETED_VIA_API
    assert result["api_status_code"] == 200
    assert result["extracted_data"]["source"] == "REST_API_V1"
    assert result.get("browser_session_id") is None
    assert any("Bypassing browser fallback" in log.message for log in result["logs"])


def test_graph_api_404_engages_headless_browser_fallback():
    graph = build_fallback_graph()
    initial_state = FallbackState(
        execution_id="test-api-404-002",
        action=WorkflowActionType.FETCH_INVOICE,
        target_id="INV-2026-404",
        api_endpoint="https://api.internal/v1/invoices",
        gui_url="https://portal.internal/invoices",
        simulate_api_failure=True,
        simulated_failure_type="404",
    )

    result = graph.invoke(initial_state)

    assert result["fallback_triggered"] is True
    assert result["execution_channel"] == ExecutionChannel.BROWSER_FALLBACK
    assert result["status"] == WorkflowStatus.COMPLETED_VIA_BROWSER_FALLBACK
    assert result["api_status_code"] == 404
    assert result["browser_session_id"] is not None
    assert result["extracted_data"]["source"] == "HEADLESS_BROWSER_DOM"
    assert "entity-detail-card" in result["extracted_data"]["dom_selector"]
    assert any("Initiating headless browser GUI fallback" in log.message for log in result["logs"])


def test_graph_api_timeout_engages_headless_browser_fallback():
    graph = build_fallback_graph()
    initial_state = FallbackState(
        execution_id="test-api-timeout-003",
        action=WorkflowActionType.EXPORT_REPORT,
        target_id="REP-2026-TIMEOUT",
        api_endpoint="https://api.internal/v1/reports",
        gui_url="https://portal.internal/reports",
        simulate_api_failure=True,
        simulated_failure_type="timeout",
    )

    result = graph.invoke(initial_state)

    assert result["fallback_triggered"] is True
    assert result["api_status_code"] == 504
    assert result["execution_channel"] == ExecutionChannel.BROWSER_FALLBACK
    assert result["status"] == WorkflowStatus.COMPLETED_VIA_BROWSER_FALLBACK
    assert result["extracted_data"]["source"] == "HEADLESS_BROWSER_DOM"
