"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for Fallback Agent."""

import json
import os
import sqlite3
from typing import Optional
from app.models import (
    ExecutionChannel,
    ExecutionLogEntry,
    FallbackSearchHit,
    WorkflowActionType,
    WorkflowExecutionResponse,
    WorkflowStatus,
)


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
            CREATE TABLE IF NOT EXISTS fallback_executions (
                execution_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                target_id TEXT NOT NULL,
                execution_channel TEXT NOT NULL,
                status TEXT NOT NULL,
                api_status_code INTEGER,
                api_error_detail TEXT,
                fallback_triggered INTEGER NOT NULL,
                browser_session_id TEXT,
                extracted_data TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_logs (
                log_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL REFERENCES fallback_executions(execution_id) ON DELETE CASCADE,
                channel TEXT NOT NULL,
                step_name TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fallback_executions_fts USING fts5(
                execution_id UNINDEXED,
                action,
                target_id,
                execution_channel,
                status,
                api_error_detail,
                extracted_data,
                content='fallback_executions',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS fallback_executions_ai AFTER INSERT ON fallback_executions BEGIN
                INSERT INTO fallback_executions_fts(rowid, execution_id, action, target_id, execution_channel, status, api_error_detail, extracted_data)
                VALUES (new.rowid, new.execution_id, new.action, new.target_id, new.execution_channel, new.status, coalesce(new.api_error_detail, ''), new.extracted_data);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS fallback_executions_ad AFTER DELETE ON fallback_executions BEGIN
                INSERT INTO fallback_executions_fts(fallback_executions_fts, rowid, execution_id, action, target_id, execution_channel, status, api_error_detail, extracted_data)
                VALUES('delete', old.rowid, old.execution_id, old.action, old.target_id, old.execution_channel, old.status, coalesce(old.api_error_detail, ''), old.extracted_data);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS fallback_executions_au AFTER UPDATE ON fallback_executions BEGIN
                INSERT INTO fallback_executions_fts(fallback_executions_fts, rowid, execution_id, action, target_id, execution_channel, status, api_error_detail, extracted_data)
                VALUES('delete', old.rowid, old.execution_id, old.action, old.target_id, old.execution_channel, old.status, coalesce(old.api_error_detail, ''), old.extracted_data);
                INSERT INTO fallback_executions_fts(rowid, execution_id, action, target_id, execution_channel, status, api_error_detail, extracted_data)
                VALUES (new.rowid, new.execution_id, new.action, new.target_id, new.execution_channel, new.status, coalesce(new.api_error_detail, ''), new.extracted_data);
            END;
            """)
    finally:
        conn.close()


def save_execution_sync(db_path: str, response: WorkflowExecutionResponse) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO fallback_executions (
                    execution_id, action, target_id, execution_channel,
                    status, api_status_code, api_error_detail, fallback_triggered,
                    browser_session_id, extracted_data, latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    status=excluded.status,
                    execution_channel=excluded.execution_channel,
                    fallback_triggered=excluded.fallback_triggered,
                    extracted_data=excluded.extracted_data;
                """,
                (
                    response.execution_id,
                    response.action.value,
                    response.target_id,
                    response.execution_channel.value,
                    response.status.value,
                    response.api_status_code,
                    response.api_error_detail,
                    1 if response.fallback_triggered else 0,
                    response.browser_session_id,
                    json.dumps(response.extracted_data),
                    response.latency_ms,
                    response.created_at,
                ),
            )

            for log in response.logs:
                conn.execute(
                    """
                    INSERT INTO execution_logs (
                        log_id, execution_id, channel, step_name, message, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(log_id) DO NOTHING;
                    """,
                    (
                        log.log_id,
                        log.execution_id,
                        log.channel.value,
                        log.step_name,
                        log.message,
                        log.timestamp,
                    ),
                )
    finally:
        conn.close()


def get_execution_sync(db_path: str, execution_id: str) -> Optional[dict]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fallback_executions WHERE execution_id = ?", (execution_id,))
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("SELECT * FROM execution_logs WHERE execution_id = ? ORDER BY timestamp ASC", (execution_id,))
        log_rows = cursor.fetchall()

        res = dict(row)
        res["extracted_data"] = json.loads(res["extracted_data"])
        res["fallback_triggered"] = bool(res["fallback_triggered"])
        res["logs"] = [dict(lr) for lr in log_rows]
        return res
    finally:
        conn.close()


def search_executions_fts_sync(db_path: str, query: str, limit: int = 10) -> list[FallbackSearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                execution_id,
                action,
                execution_channel,
                status,
                snippet(fallback_executions_fts, -1, '<b>', '</b>', '...', 12) AS snippet,
                bm25(fallback_executions_fts) AS rank
            FROM fallback_executions_fts
            WHERE fallback_executions_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            FallbackSearchHit(
                record_id=r["execution_id"],
                execution_id=r["execution_id"],
                action=r["action"],
                execution_channel=r["execution_channel"],
                status=r["status"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
