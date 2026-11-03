"""SQLite WAL database layer with FTS5 virtual tables and sync triggers for Sandbox Executions."""

import json
import os
import sqlite3
from typing import Optional
from app.models import ExecutionResult, ExecutionSearchHit, ExecutionStatus


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
            CREATE TABLE IF NOT EXISTS sandbox_executions (
                execution_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                exit_code INTEGER NOT NULL,
                stdout TEXT NOT NULL,
                stderr TEXT NOT NULL,
                execution_time_ms REAL NOT NULL,
                code TEXT NOT NULL,
                egress_blocked INTEGER NOT NULL DEFAULT 1,
                ast_violations_json TEXT NOT NULL DEFAULT '[]',
                executed_at TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sandbox_executions_fts USING fts5(
                execution_id UNINDEXED,
                status,
                code,
                stdout,
                stderr,
                content='sandbox_executions',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS sandbox_executions_ai AFTER INSERT ON sandbox_executions BEGIN
                INSERT INTO sandbox_executions_fts(rowid, execution_id, status, code, stdout, stderr)
                VALUES (new.rowid, new.execution_id, new.status, new.code, new.stdout, new.stderr);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS sandbox_executions_ad AFTER DELETE ON sandbox_executions BEGIN
                INSERT INTO sandbox_executions_fts(sandbox_executions_fts, rowid, execution_id, status, code, stdout, stderr)
                VALUES('delete', old.rowid, old.execution_id, old.status, old.code, old.stdout, old.stderr);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS sandbox_executions_au AFTER UPDATE ON sandbox_executions BEGIN
                INSERT INTO sandbox_executions_fts(sandbox_executions_fts, rowid, execution_id, status, code, stdout, stderr)
                VALUES('delete', old.rowid, old.execution_id, old.status, old.code, old.stdout, old.stderr);
                INSERT INTO sandbox_executions_fts(rowid, execution_id, status, code, stdout, stderr)
                VALUES (new.rowid, new.execution_id, new.status, new.code, new.stdout, new.stderr);
            END;
            """)
    finally:
        conn.close()


def save_execution_result_sync(db_path: str, code: str, result: ExecutionResult) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO sandbox_executions (
                    execution_id, status, exit_code, stdout, stderr,
                    execution_time_ms, code, egress_blocked, ast_violations_json, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    status=excluded.status,
                    stdout=excluded.stdout,
                    stderr=excluded.stderr;
                """,
                (
                    result.execution_id,
                    result.status.value,
                    result.exit_code,
                    result.stdout,
                    result.stderr,
                    result.execution_time_ms,
                    code,
                    1 if result.egress_blocked else 0,
                    json.dumps(result.ast_violations),
                    result.executed_at,
                ),
            )
    finally:
        conn.close()


def get_execution_result_sync(db_path: str, execution_id: str) -> Optional[dict]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sandbox_executions WHERE execution_id = ?", (execution_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["ast_violations"] = json.loads(res["ast_violations_json"])
        return res
    finally:
        conn.close()


def search_executions_fts_sync(db_path: str, query: str, limit: int = 10) -> list[ExecutionSearchHit]:
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
                status,
                snippet(sandbox_executions_fts, -1, '<b>', '</b>', '...', 12) AS snippet,
                bm25(sandbox_executions_fts) AS rank
            FROM sandbox_executions_fts
            WHERE sandbox_executions_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            ExecutionSearchHit(
                execution_id=r["execution_id"],
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
