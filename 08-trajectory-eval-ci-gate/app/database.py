"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for Trajectory CI Gate."""

import json
import os
import sqlite3
from typing import Any, Optional
from app.models import (
    AgentTrajectory,
    EvalRunResponse,
    EvalVerdict,
    GoldenDAG,
    TrajectoryDeviation,
    TrajectorySearchHit,
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
            CREATE TABLE IF NOT EXISTS golden_dags (
                dag_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                dag_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS trajectory_evals (
                eval_id TEXT PRIMARY KEY,
                dag_id TEXT NOT NULL REFERENCES golden_dags(dag_id) ON DELETE CASCADE,
                pr_number INTEGER NOT NULL,
                commit_sha TEXT NOT NULL,
                total_evaluated INTEGER NOT NULL,
                passed_count INTEGER NOT NULL,
                failed_count INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS trajectory_logs (
                log_id TEXT PRIMARY KEY,
                eval_id TEXT NOT NULL REFERENCES trajectory_evals(eval_id) ON DELETE CASCADE,
                trajectory_id TEXT NOT NULL,
                tool_sequence_json TEXT NOT NULL,
                is_match INTEGER NOT NULL,
                deviation_reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS trajectory_logs_fts USING fts5(
                log_id UNINDEXED,
                eval_id UNINDEXED,
                trajectory_id UNINDEXED,
                deviation_reason,
                tool_sequence_json,
                content='trajectory_logs',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trajectory_logs_ai AFTER INSERT ON trajectory_logs BEGIN
                INSERT INTO trajectory_logs_fts(rowid, log_id, eval_id, trajectory_id, deviation_reason, tool_sequence_json)
                VALUES (new.rowid, new.log_id, new.eval_id, new.trajectory_id, new.deviation_reason, new.tool_sequence_json);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trajectory_logs_ad AFTER DELETE ON trajectory_logs BEGIN
                INSERT INTO trajectory_logs_fts(trajectory_logs_fts, rowid, log_id, eval_id, trajectory_id, deviation_reason, tool_sequence_json)
                VALUES('delete', old.rowid, old.log_id, old.eval_id, old.trajectory_id, old.deviation_reason, old.tool_sequence_json);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trajectory_logs_au AFTER UPDATE ON trajectory_logs BEGIN
                INSERT INTO trajectory_logs_fts(trajectory_logs_fts, rowid, log_id, eval_id, trajectory_id, deviation_reason, tool_sequence_json)
                VALUES('delete', old.rowid, old.log_id, old.eval_id, old.trajectory_id, old.deviation_reason, old.tool_sequence_json);
                INSERT INTO trajectory_logs_fts(rowid, log_id, eval_id, trajectory_id, deviation_reason, tool_sequence_json)
                VALUES (new.rowid, new.log_id, new.eval_id, new.trajectory_id, new.deviation_reason, new.tool_sequence_json);
            END;
            """)
    finally:
        conn.close()


def save_golden_dag_sync(db_path: str, dag: GoldenDAG, created_at: str) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO golden_dags (dag_id, name, dag_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(dag_id) DO UPDATE SET
                    name=excluded.name,
                    dag_json=excluded.dag_json;
                """,
                (dag.dag_id, dag.name, dag.model_dump_json(), created_at),
            )
    finally:
        conn.close()


def get_golden_dag_sync(db_path: str, dag_id: str) -> Optional[GoldenDAG]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT dag_json FROM golden_dags WHERE dag_id = ?", (dag_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return GoldenDAG.model_validate_json(row["dag_json"])
    finally:
        conn.close()


def save_eval_run_sync(
    db_path: str,
    eval_resp: EvalRunResponse,
    logs: list[dict[str, Any]],
) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO trajectory_evals (
                    eval_id, dag_id, pr_number, commit_sha,
                    total_evaluated, passed_count, failed_count, verdict, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    eval_resp.eval_id,
                    eval_resp.dag_id,
                    eval_resp.pr_number,
                    eval_resp.commit_sha,
                    eval_resp.total_evaluated,
                    eval_resp.passed_count,
                    eval_resp.failed_count,
                    eval_resp.verdict.value,
                    eval_resp.created_at,
                ),
            )

            for log in logs:
                conn.execute(
                    """
                    INSERT INTO trajectory_logs (
                        log_id, eval_id, trajectory_id, tool_sequence_json,
                        is_match, deviation_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        log["log_id"],
                        eval_resp.eval_id,
                        log["trajectory_id"],
                        json.dumps(log["tool_sequence"]),
                        1 if log["is_match"] else 0,
                        log["deviation_reason"],
                        eval_resp.created_at,
                    ),
                )
    finally:
        conn.close()


def get_eval_run_sync(db_path: str, eval_id: str) -> Optional[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trajectory_evals WHERE eval_id = ?", (eval_id,))
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("SELECT * FROM trajectory_logs WHERE eval_id = ? ORDER BY is_match ASC", (eval_id,))
        log_rows = cursor.fetchall()

        result = dict(row)
        result["logs"] = [dict(r) for r in log_rows]
        return result
    finally:
        conn.close()


def search_trajectory_logs_fts_sync(db_path: str, query: str, limit: int = 10) -> list[TrajectorySearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                t.log_id,
                t.eval_id,
                t.trajectory_id,
                t.is_match,
                snippet(trajectory_logs_fts, 3, '<b>', '</b>', '...', 10) AS snippet,
                bm25(trajectory_logs_fts) AS rank
            FROM trajectory_logs_fts
            JOIN trajectory_logs t ON t.rowid = trajectory_logs_fts.rowid
            WHERE trajectory_logs_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            TrajectorySearchHit(
                log_id=r["log_id"],
                eval_id=r["eval_id"],
                trajectory_id=r["trajectory_id"],
                is_match=r["is_match"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
