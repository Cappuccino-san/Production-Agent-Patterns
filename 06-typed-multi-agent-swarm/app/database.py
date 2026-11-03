"""SQLite database layer configured with native WAL mode and FTS5 full-text search triggers."""

import json
import os
import sqlite3
from typing import Any, Optional
from app.models import ArtifactSearchHit, SwarmStatus, SwarmStepLog


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and enforce enterprise WAL mode pragmas."""
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.isolation_level = None  # Autocommit mode for pragma execution
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.isolation_level = ""  # Standard deferred transactions
    return conn


def init_db_sync(db_path: str) -> None:
    """Initialize schema, relational tables, FTS5 virtual index, and automated sync triggers."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_tasks (
                task_id TEXT PRIMARY KEY,
                task_description TEXT NOT NULL,
                status TEXT NOT NULL,
                iteration INTEGER NOT NULL DEFAULT 0,
                max_iterations INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_artifacts (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES swarm_tasks(task_id) ON DELETE CASCADE,
                artifact_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_steps (
                step_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES swarm_tasks(task_id) ON DELETE CASCADE,
                agent_role TEXT NOT NULL,
                action TEXT NOT NULL,
                packet_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table for BM25 Search
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS swarm_artifacts_fts USING fts5(
                artifact_id UNINDEXED,
                task_id UNINDEXED,
                artifact_type,
                title,
                content,
                content='swarm_artifacts',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS swarm_artifacts_ai AFTER INSERT ON swarm_artifacts BEGIN
                INSERT INTO swarm_artifacts_fts(rowid, artifact_id, task_id, artifact_type, title, content)
                VALUES (new.rowid, new.artifact_id, new.task_id, new.artifact_type, new.title, new.content);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS swarm_artifacts_ad AFTER DELETE ON swarm_artifacts BEGIN
                INSERT INTO swarm_artifacts_fts(swarm_artifacts_fts, rowid, artifact_id, task_id, artifact_type, title, content)
                VALUES('delete', old.rowid, old.artifact_id, old.task_id, old.artifact_type, old.title, old.content);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS swarm_artifacts_au AFTER UPDATE ON swarm_artifacts BEGIN
                INSERT INTO swarm_artifacts_fts(swarm_artifacts_fts, rowid, artifact_id, task_id, artifact_type, title, content)
                VALUES('delete', old.rowid, old.artifact_id, old.task_id, old.artifact_type, old.title, old.content);
                INSERT INTO swarm_artifacts_fts(rowid, artifact_id, task_id, artifact_type, title, content)
                VALUES (new.rowid, new.artifact_id, new.task_id, new.artifact_type, new.title, new.content);
            END;
            """)
    finally:
        conn.close()


def save_swarm_task_sync(
    db_path: str,
    task_id: str,
    task_description: str,
    status: SwarmStatus,
    iteration: int,
    max_iterations: int,
    created_at: str,
    updated_at: str,
) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO swarm_tasks (task_id, task_description, status, iteration, max_iterations, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    iteration=excluded.iteration,
                    updated_at=excluded.updated_at;
                """,
                (task_id, task_description, status.value if hasattr(status, 'value') else status, iteration, max_iterations, created_at, updated_at),
            )
    finally:
        conn.close()


def save_swarm_artifact_sync(
    db_path: str,
    artifact_id: str,
    task_id: str,
    artifact_type: str,
    title: str,
    content: str,
    metadata: dict[str, Any],
    created_at: str,
) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO swarm_artifacts (artifact_id, task_id, artifact_type, title, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    content=excluded.content,
                    metadata_json=excluded.metadata_json;
                """,
                (artifact_id, task_id, artifact_type, title, content, json.dumps(metadata), created_at),
            )
    finally:
        conn.close()


def save_swarm_step_sync(
    db_path: str,
    step_id: str,
    task_id: str,
    agent_role: str,
    action: str,
    packet_type: str,
    payload: dict[str, Any],
    timestamp: str,
) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO swarm_steps (step_id, task_id, agent_role, action, packet_type, payload_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(step_id) DO NOTHING;
                """,
                (step_id, task_id, agent_role, action, packet_type, json.dumps(payload), timestamp),
            )
    finally:
        conn.close()


def get_swarm_task_sync(db_path: str, task_id: str) -> Optional[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM swarm_tasks WHERE task_id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            return None

        cursor.execute("SELECT * FROM swarm_artifacts WHERE task_id = ?", (task_id,))
        artifact_rows = cursor.fetchall()

        cursor.execute("SELECT * FROM swarm_steps WHERE task_id = ? ORDER BY timestamp ASC", (task_id,))
        step_rows = cursor.fetchall()

        artifacts = [dict(r) for r in artifact_rows]
        steps = [
            SwarmStepLog(
                step_id=r["step_id"],
                agent_role=r["agent_role"],
                action=r["action"],
                packet_type=r["packet_type"],
                payload=json.loads(r["payload_json"]),
                timestamp=r["timestamp"],
            )
            for r in step_rows
        ]

        result = dict(task_row)
        result["artifacts"] = artifacts
        result["history"] = steps
        return result
    finally:
        conn.close()


def search_artifacts_fts_sync(db_path: str, query: str, limit: int = 10) -> list[ArtifactSearchHit]:
    """Execute BM25 ranked full-text query across synced FTS5 virtual table."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized_query = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized_query:
            return []

        cursor.execute(
            """
            SELECT 
                artifact_id,
                task_id,
                artifact_type,
                title,
                snippet(swarm_artifacts_fts, 4, '<b>', '</b>', '...', 12) AS snippet,
                bm25(swarm_artifacts_fts) AS rank
            FROM swarm_artifacts_fts
            WHERE swarm_artifacts_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized_query, limit),
        )
        rows = cursor.fetchall()
        return [
            ArtifactSearchHit(
                artifact_id=r["artifact_id"],
                task_id=r["task_id"],
                artifact_type=r["artifact_type"],
                title=r["title"],
                content_snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
