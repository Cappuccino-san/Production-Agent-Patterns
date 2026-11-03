"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for OpenTelemetry Traces."""

import json
import os
import sqlite3
from typing import Any, Optional
from app.models import AgentSpan, AgentTrace, SpanSearchHit, SpanType


def get_db_connection(db_path: str) -> sqlite3.Connection:
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.isolation_level = None  # Autocommit for PRAGMAs
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.isolation_level = ""
    return conn


def init_db_sync(db_path: str) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_traces (
                trace_id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                root_span_id TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                total_duration_ms REAL NOT NULL,
                sink TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES agent_traces(trace_id) ON DELETE CASCADE,
                parent_span_id TEXT,
                span_type TEXT NOT NULL,
                name TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                attributes_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS agent_spans_fts USING fts5(
                span_id UNINDEXED,
                trace_id UNINDEXED,
                parent_span_id UNINDEXED,
                span_type,
                name,
                attributes_json,
                content='agent_spans',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS agent_spans_ai AFTER INSERT ON agent_spans BEGIN
                INSERT INTO agent_spans_fts(rowid, span_id, trace_id, parent_span_id, span_type, name, attributes_json)
                VALUES (new.rowid, new.span_id, new.trace_id, new.parent_span_id, new.span_type, new.name, new.attributes_json);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS agent_spans_ad AFTER DELETE ON agent_spans BEGIN
                INSERT INTO agent_spans_fts(agent_spans_fts, rowid, span_id, trace_id, parent_span_id, span_type, name, attributes_json)
                VALUES('delete', old.rowid, old.span_id, old.trace_id, old.parent_span_id, old.span_type, old.name, old.attributes_json);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS agent_spans_au AFTER UPDATE ON agent_spans BEGIN
                INSERT INTO agent_spans_fts(agent_spans_fts, rowid, span_id, trace_id, parent_span_id, span_type, name, attributes_json)
                VALUES('delete', old.rowid, old.span_id, old.trace_id, old.parent_span_id, old.span_type, old.name, old.attributes_json);
                INSERT INTO agent_spans_fts(rowid, span_id, trace_id, parent_span_id, span_type, name, attributes_json)
                VALUES (new.rowid, new.span_id, new.trace_id, new.parent_span_id, new.span_type, new.name, new.attributes_json);
            END;
            """)
    finally:
        conn.close()


def save_agent_trace_sync(db_path: str, trace: AgentTrace) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO agent_traces (trace_id, agent_name, root_span_id, total_tokens, total_duration_ms, sink, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    total_tokens=excluded.total_tokens,
                    total_duration_ms=excluded.total_duration_ms;
                """,
                (
                    trace.trace_id,
                    trace.agent_name,
                    trace.root_span_id,
                    trace.total_tokens,
                    trace.total_duration_ms,
                    trace.sink,
                    trace.created_at,
                ),
            )

            for span in trace.spans:
                conn.execute(
                    """
                    INSERT INTO agent_spans (span_id, trace_id, parent_span_id, span_type, name, duration_ms, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(span_id) DO NOTHING;
                    """,
                    (
                        span.span_id,
                        span.trace_id,
                        span.parent_span_id,
                        span.span_type.value,
                        span.name,
                        span.duration_ms,
                        span.attributes.model_dump_json(),
                        span.start_time,
                    ),
                )
    finally:
        conn.close()


def get_agent_trace_sync(db_path: str, trace_id: str) -> Optional[AgentTrace]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agent_traces WHERE trace_id = ?", (trace_id,))
        trace_row = cursor.fetchone()
        if not trace_row:
            return None

        cursor.execute("SELECT * FROM agent_spans WHERE trace_id = ? ORDER BY created_at ASC", (trace_id,))
        span_rows = cursor.fetchall()

        spans = []
        for r in span_rows:
            from app.models import SpanAttributes
            attrs = SpanAttributes.model_validate_json(r["attributes_json"])
            spans.append(
                AgentSpan(
                    span_id=r["span_id"],
                    trace_id=r["trace_id"],
                    parent_span_id=r["parent_span_id"],
                    span_type=SpanType(r["span_type"]),
                    name=r["name"],
                    start_time=r["created_at"],
                    end_time=r["created_at"],
                    duration_ms=r["duration_ms"],
                    attributes=attrs,
                )
            )

        return AgentTrace(
            trace_id=trace_row["trace_id"],
            agent_name=trace_row["agent_name"],
            root_span_id=trace_row["root_span_id"],
            total_tokens=trace_row["total_tokens"],
            total_duration_ms=trace_row["total_duration_ms"],
            sink=trace_row["sink"],
            created_at=trace_row["created_at"],
            spans=spans,
        )
    finally:
        conn.close()


def search_agent_spans_fts_sync(db_path: str, query: str, limit: int = 10) -> list[SpanSearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                span_id,
                trace_id,
                span_type,
                name,
                snippet(agent_spans_fts, 5, '<b>', '</b>', '...', 12) AS snippet,
                bm25(agent_spans_fts) AS rank
            FROM agent_spans_fts
            WHERE agent_spans_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            SpanSearchHit(
                span_id=r["span_id"],
                trace_id=r["trace_id"],
                span_type=r["span_type"],
                name=r["name"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
