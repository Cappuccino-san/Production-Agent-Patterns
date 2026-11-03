"""Tests for SQLite WAL mode, FTS5 sync triggers, and persistence."""

import json
import sqlite3
import pytest
from app.database import (
    get_db_connection,
    get_shadow_comparison_sync,
    list_comparisons_sync,
    save_shadow_comparison_sync,
    save_traffic_request_sync,
    search_comparisons_fts_sync,
)
from app.models import (
    AgentTrafficResponse,
    ComparisonRecommendation,
    ShadowComparisonReport,
    ToolCallRecord,
    TrajectorySummary,
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


def test_save_and_retrieve_shadow_comparison(temp_db_path):
    # First save parent traffic request to satisfy FK
    req = AgentTrafficResponse(
        request_id="req-p-01",
        prompt="Compare data warehouse indexing approaches",
        primary_output="Standard summary",
        primary_cost_usd=0.012,
        primary_latency_ms=95.0,
        is_shadow_sampled=True,
        shadow_comparison_id="cmp-p-01",
    )
    save_traffic_request_sync(temp_db_path, req)

    primary = TrajectorySummary(
        topology_name="STANDARD_REACT",
        tool_calls=[ToolCallRecord(step_index=1, tool_name="search")],
        cost_usd=0.012,
        latency_ms=95.0,
    )
    candidate = TrajectorySummary(
        topology_name="PARALLEL_REACT",
        tool_calls=[ToolCallRecord(step_index=1, tool_name="parallel_search")],
        cost_usd=0.006,
        latency_ms=50.0,
    )
    report = ShadowComparisonReport(
        comparison_id="cmp-p-01",
        request_id="req-p-01",
        prompt="Compare data warehouse indexing approaches",
        primary_trajectory=primary,
        candidate_trajectory=candidate,
        path_similarity_score=0.0,
        cost_delta_usd=-0.006,
        cost_savings_pct=50.0,
        latency_delta_ms=-45.0,
        recommendation=ComparisonRecommendation.DEPLOY_CANDIDATE,
        diff_summary="Candidate saves 50% cost and decreases latency by 45ms.",
    )

    save_shadow_comparison_sync(temp_db_path, report)
    fetched = get_shadow_comparison_sync(temp_db_path, "cmp-p-01")

    assert fetched is not None
    assert fetched["comparison_id"] == "cmp-p-01"
    assert fetched["cost_savings_pct"] == 50.0
    assert fetched["recommendation"] == "DEPLOY_CANDIDATE"
    assert fetched["candidate_trajectory"]["topology_name"] == "PARALLEL_REACT"


def test_fts5_sync_triggers(temp_db_path):
    hits = search_comparisons_fts_sync(temp_db_path, "warehouse")
    assert len(hits) >= 1
    assert any(h.comparison_id == "cmp-p-01" for h in hits)
