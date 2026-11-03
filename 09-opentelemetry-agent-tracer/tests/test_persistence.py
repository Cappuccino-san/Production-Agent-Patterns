"""Tier 3: SQLite WAL Mode, FTS5 Virtual Tables, and Automated Triggers."""

import sqlite3
from app.database import (
    get_agent_trace_sync,
    get_db_connection,
    save_agent_trace_sync,
    search_agent_spans_fts_sync,
)
from app.models import AgentSpan, AgentTrace, SpanAttributes, SpanType


class TestPersistence:
    def test_sqlite_wal_pragmas(self, temp_db: str):
        conn = get_db_connection(temp_db)
        try:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert journal_mode.lower() == "wal"
            assert foreign_keys == 1
        finally:
            conn.close()

    def test_trace_save_and_retrieve(self, temp_db: str):
        span = AgentSpan(
            span_id="sp-1",
            trace_id="trc-persist-1",
            parent_span_id=None,
            span_type=SpanType.LLM_HOP,
            name="LLM-Query-Decomposition",
            start_time="2026-11-02T12:00:00Z",
            end_time="2026-11-02T12:00:01Z",
            duration_ms=1000.0,
            attributes=SpanAttributes(model_name="gpt-4o", prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )

        trace = AgentTrace(
            trace_id="trc-persist-1",
            agent_name="SearchAgent",
            root_span_id="sp-1",
            total_tokens=150,
            total_duration_ms=1000.0,
            sink="LangSmith",
            created_at="2026-11-02T12:00:00Z",
            spans=[span],
        )

        save_agent_trace_sync(temp_db, trace)

        fetched = get_agent_trace_sync(temp_db, "trc-persist-1")
        assert fetched is not None
        assert fetched.trace_id == "trc-persist-1"
        assert len(fetched.spans) == 1
        assert fetched.spans[0].attributes.model_name == "gpt-4o"

    def test_fts5_triggers_insert_and_bm25_search(self, temp_db: str):
        span = AgentSpan(
            span_id="sp-fts-1",
            trace_id="trc-fts-1",
            parent_span_id=None,
            span_type=SpanType.TOOL_LATENCY,
            name="Tool:VectorDatabaseQuery",
            start_time="2026-11-02T12:00:00Z",
            end_time="2026-11-02T12:00:01Z",
            duration_ms=45.0,
            attributes=SpanAttributes(tool_name="VectorDatabaseQuery", extra_metadata={"embedding_dim": 1536}),
        )
        trace = AgentTrace(
            trace_id="trc-fts-1",
            agent_name="RetrieverAgent",
            root_span_id="sp-fts-1",
            total_tokens=0,
            total_duration_ms=45.0,
            sink="LangSmith",
            created_at="2026-11-02T12:00:00Z",
            spans=[span],
        )

        save_agent_trace_sync(temp_db, trace)

        hits = search_agent_spans_fts_sync(temp_db, "VectorDatabaseQuery")
        assert len(hits) == 1
        assert hits[0].span_id == "sp-fts-1"
        assert "VectorDatabaseQuery" in hits[0].name or "VectorDatabaseQuery" in hits[0].snippet
