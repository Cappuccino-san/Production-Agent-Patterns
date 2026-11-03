"""Tests for SQLite WAL mode, FTS5 sync triggers, and persistence."""

import os
import sqlite3
import pytest
from app.database import (
    get_cost_run_sync,
    get_db_connection,
    init_db_sync,
    save_cost_run_sync,
    search_cost_summaries_fts_sync,
)
from app.models import AgentTaskRunResponse, CostLedgerEntry, CostStatus


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


def test_save_and_retrieve_cost_run(temp_db_path):
    response = AgentTaskRunResponse(
        request_id="req-persist-100",
        prompt="Perform sentiment classification on product reviews",
        initial_model="gpt-4o",
        final_model="gpt-4o",
        total_tokens=1200,
        total_cost_usd=0.015,
        loop_depth=2,
        status=CostStatus.COMPLETED,
        kill_switch_triggered=False,
        fallback_engaged=False,
        final_output="Sentiment analysis completed successfully.",
        ledger=[
            CostLedgerEntry(
                ledger_id="led-1",
                request_id="req-persist-100",
                step_index=1,
                model_used="gpt-4o",
                prompt_tokens=400,
                completion_tokens=200,
                step_cost_usd=0.005,
                cumulative_cost_usd=0.005,
                loop_depth=1,
                kill_switch_active=False,
            )
        ],
    )

    save_cost_run_sync(temp_db_path, response)
    fetched = get_cost_run_sync(temp_db_path, "req-persist-100")

    assert fetched is not None
    assert fetched["request_id"] == "req-persist-100"
    assert fetched["total_tokens"] == 1200
    assert len(fetched["ledger"]) == 1
    assert fetched["ledger"][0]["model_used"] == "gpt-4o"


def test_fts5_search_sync_triggers(temp_db_path):
    response = AgentTaskRunResponse(
        request_id="req-fts-200",
        prompt="Synthesize biomedical gene interaction pathway findings",
        initial_model="gpt-4o",
        final_model="gpt-4o-mini",
        total_tokens=45000,
        total_cost_usd=0.52,
        loop_depth=3,
        status=CostStatus.FALLBACK_ENGAGED,
        kill_switch_triggered=True,
        fallback_engaged=True,
        final_output="Biomedical gene interaction pathway synthesized under fallback budget.",
        ledger=[],
    )

    save_cost_run_sync(temp_db_path, response)

    # Search by keyword in prompt/output
    hits = search_cost_summaries_fts_sync(temp_db_path, "biomedical")
    assert len(hits) >= 1
    assert any(h.request_id == "req-fts-200" for h in hits)
