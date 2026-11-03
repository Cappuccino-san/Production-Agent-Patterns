"""Tests for SQLite WAL mode, FTS5 sync triggers, and audit log persistence."""

import json
import sqlite3
import pytest
from app.database import (
    get_db_connection,
    get_execution_sync,
    save_execution_sync,
    search_executions_fts_sync,
)
from app.models import (
    ExecutionChannel,
    ExecutionLogEntry,
    WorkflowActionType,
    WorkflowExecutionResponse,
    WorkflowStatus,
)


def test_sqlite_wal_pragmas(temp_db_path):
    conn = get_db_connection(temp_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal"

        cursor.execute("PRAGMA foreign_keys;")
        foreign_keys = cursor.fetchone()[0]
        assert foreign_keys == 1
    finally:
        conn.close()


def test_save_and_retrieve_execution(temp_db_path):
    response = WorkflowExecutionResponse(
        execution_id="exec-persist-100",
        action=WorkflowActionType.FETCH_INVOICE,
        target_id="INV-9900",
        execution_channel=ExecutionChannel.BROWSER_FALLBACK,
        status=WorkflowStatus.COMPLETED_VIA_BROWSER_FALLBACK,
        api_status_code=404,
        api_error_detail="HTTP 404 Not Found on v1 API",
        fallback_triggered=True,
        browser_session_id="pw-sess-12345",
        extracted_data={"invoice_id": "INV-9900", "total": 1450.00},
        latency_ms=120.5,
        logs=[
            ExecutionLogEntry(
                log_id="log-p1",
                execution_id="exec-persist-100",
                channel=ExecutionChannel.API,
                step_name="API_CALL",
                message="API returned 404",
            ),
            ExecutionLogEntry(
                log_id="log-p2",
                execution_id="exec-persist-100",
                channel=ExecutionChannel.BROWSER_FALLBACK,
                step_name="BROWSER_FALLBACK",
                message="Extracted from Chromium DOM",
            ),
        ],
    )

    save_execution_sync(temp_db_path, response)
    fetched = get_execution_sync(temp_db_path, "exec-persist-100")

    assert fetched is not None
    assert fetched["execution_id"] == "exec-persist-100"
    assert fetched["fallback_triggered"] is True
    assert fetched["browser_session_id"] == "pw-sess-12345"
    assert fetched["extracted_data"]["invoice_id"] == "INV-9900"
    assert len(fetched["logs"]) == 2


def test_fts5_sync_triggers(temp_db_path):
    response = WorkflowExecutionResponse(
        execution_id="exec-fts-200",
        action=WorkflowActionType.EXTRACT_METRICS,
        target_id="METRIC-TELEMETRY-2026",
        execution_channel=ExecutionChannel.API,
        status=WorkflowStatus.COMPLETED_VIA_API,
        api_status_code=200,
        api_error_detail=None,
        fallback_triggered=False,
        browser_session_id=None,
        extracted_data={"telemetry_rate": "99.98% uptime"},
        latency_ms=25.0,
        logs=[],
    )

    save_execution_sync(temp_db_path, response)

    hits = search_executions_fts_sync(temp_db_path, "telemetry")
    assert len(hits) >= 1
    assert any(h.execution_id == "exec-fts-200" for h in hits)
