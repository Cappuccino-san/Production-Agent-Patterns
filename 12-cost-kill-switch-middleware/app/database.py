"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for Cost Control."""

import json
import os
import sqlite3
from typing import Optional
from app.models import AgentTaskRunResponse, CostLedgerEntry, CostSearchHit, CostStatus


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
            CREATE TABLE IF NOT EXISTS cost_summaries (
                request_id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                initial_model TEXT NOT NULL,
                final_model TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                total_cost_usd REAL NOT NULL,
                loop_depth INTEGER NOT NULL,
                status TEXT NOT NULL,
                kill_switch_triggered INTEGER NOT NULL,
                fallback_engaged INTEGER NOT NULL,
                final_output TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cost_ledger (
                ledger_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL REFERENCES cost_summaries(request_id) ON DELETE CASCADE,
                step_index INTEGER NOT NULL,
                model_used TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                step_cost_usd REAL NOT NULL,
                cumulative_cost_usd REAL NOT NULL,
                loop_depth INTEGER NOT NULL,
                kill_switch_active INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cost_summaries_fts USING fts5(
                request_id UNINDEXED,
                prompt,
                initial_model,
                final_model,
                status,
                final_output,
                content='cost_summaries',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cost_summaries_ai AFTER INSERT ON cost_summaries BEGIN
                INSERT INTO cost_summaries_fts(rowid, request_id, prompt, initial_model, final_model, status, final_output)
                VALUES (new.rowid, new.request_id, new.prompt, new.initial_model, new.final_model, new.status, new.final_output);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cost_summaries_ad AFTER DELETE ON cost_summaries BEGIN
                INSERT INTO cost_summaries_fts(cost_summaries_fts, rowid, request_id, prompt, initial_model, final_model, status, final_output)
                VALUES('delete', old.rowid, old.request_id, old.prompt, old.initial_model, old.final_model, old.status, old.final_output);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cost_summaries_au AFTER UPDATE ON cost_summaries BEGIN
                INSERT INTO cost_summaries_fts(cost_summaries_fts, rowid, request_id, prompt, initial_model, final_model, status, final_output)
                VALUES('delete', old.rowid, old.request_id, old.prompt, old.initial_model, old.final_model, old.status, old.final_output);
                INSERT INTO cost_summaries_fts(rowid, request_id, prompt, initial_model, final_model, status, final_output)
                VALUES (new.rowid, new.request_id, new.prompt, new.initial_model, new.final_model, new.status, new.final_output);
            END;
            """)
    finally:
        conn.close()


def save_cost_run_sync(db_path: str, response: AgentTaskRunResponse) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO cost_summaries (
                    request_id, prompt, initial_model, final_model,
                    total_tokens, total_cost_usd, loop_depth, status,
                    kill_switch_triggered, fallback_engaged, final_output, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    total_cost_usd=excluded.total_cost_usd,
                    final_model=excluded.final_model,
                    status=excluded.status;
                """,
                (
                    response.request_id,
                    response.prompt,
                    response.initial_model,
                    response.final_model,
                    response.total_tokens,
                    response.total_cost_usd,
                    response.loop_depth,
                    response.status.value,
                    1 if response.kill_switch_triggered else 0,
                    1 if response.fallback_engaged else 0,
                    response.final_output,
                    response.created_at,
                ),
            )

            for item in response.ledger:
                conn.execute(
                    """
                    INSERT INTO cost_ledger (
                        ledger_id, request_id, step_index, model_used,
                        prompt_tokens, completion_tokens, step_cost_usd,
                        cumulative_cost_usd, loop_depth, kill_switch_active, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ledger_id) DO NOTHING;
                    """,
                    (
                        item.ledger_id,
                        item.request_id,
                        item.step_index,
                        item.model_used,
                        item.prompt_tokens,
                        item.completion_tokens,
                        item.step_cost_usd,
                        item.cumulative_cost_usd,
                        item.loop_depth,
                        1 if item.kill_switch_active else 0,
                        item.timestamp,
                    ),
                )
    finally:
        conn.close()


def get_cost_run_sync(db_path: str, request_id: str) -> Optional[dict]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cost_summaries WHERE request_id = ?", (request_id,))
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("SELECT * FROM cost_ledger WHERE request_id = ? ORDER BY step_index ASC", (request_id,))
        ledger_rows = cursor.fetchall()

        res = dict(row)
        res["ledger"] = [dict(r) for r in ledger_rows]
        return res
    finally:
        conn.close()


def search_cost_summaries_fts_sync(db_path: str, query: str, limit: int = 10) -> list[CostSearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                request_id,
                final_model,
                status,
                snippet(cost_summaries_fts, -1, '<b>', '</b>', '...', 12) AS snippet,
                bm25(cost_summaries_fts) AS rank
            FROM cost_summaries_fts
            WHERE cost_summaries_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            CostSearchHit(
                record_id=r["request_id"],
                request_id=r["request_id"],
                final_model=r["final_model"],
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
