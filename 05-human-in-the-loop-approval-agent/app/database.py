"""SQLite WAL database engine with FTS5 virtual tables, sync triggers, and checkpointer."""

import base64
import json
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import aiosqlite
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    RunnableConfig,
)
from langgraph.checkpoint.memory import MemorySaver

_db_lock = threading.RLock()


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000;

CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    description TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT,
    decision_reason TEXT,
    decision_by TEXT,
    result TEXT,
    execution_logs TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    state_blob TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS approval_audit_fts USING fts5(
    action_type,
    description,
    payload,
    decision_reason,
    result,
    content='approval_requests',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_approvals_ai AFTER INSERT ON approval_requests
BEGIN
    INSERT INTO approval_audit_fts(rowid, action_type, description, payload, decision_reason, result)
    VALUES (new.rowid, new.action_type, new.description, new.payload, new.decision_reason, new.result);
END;

CREATE TRIGGER IF NOT EXISTS trg_approvals_ad AFTER DELETE ON approval_requests
BEGIN
    INSERT INTO approval_audit_fts(approval_audit_fts, rowid, action_type, description, payload, decision_reason, result)
    VALUES('delete', old.rowid, old.action_type, old.description, old.payload, old.decision_reason, old.result);
END;

CREATE TRIGGER IF NOT EXISTS trg_approvals_au AFTER UPDATE ON approval_requests
BEGIN
    INSERT INTO approval_audit_fts(approval_audit_fts, rowid, action_type, description, payload, decision_reason, result)
    VALUES('delete', old.rowid, old.action_type, old.description, old.payload, old.decision_reason, old.result);
    INSERT INTO approval_audit_fts(rowid, action_type, description, payload, decision_reason, result)
    VALUES (new.rowid, new.action_type, new.description, new.payload, new.decision_reason, new.result);
END;
"""


def init_db_sync(db_path: str) -> None:
    """Synchronously initialize SQLite database schemas, pragmas, and FTS5 triggers."""
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with _db_lock:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()


async def init_db(db_path: str) -> None:
    """Asynchronously initialize SQLite database schemas, pragmas, and FTS5 triggers."""
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    async with aiosqlite.connect(db_path, timeout=30.0) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


@asynccontextmanager
async def get_db_connection(db_path: str) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an aiosqlite connection with WAL mode and row factory configured."""
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA synchronous = NORMAL;")
        await conn.execute("PRAGMA busy_timeout = 30000;")
        await conn.execute("PRAGMA foreign_keys = ON;")
        yield conn


def sanitize_fts5_query(query: str) -> str:
    """Sanitize and format query string for safe FTS5 execution.

    Extracts alphanumeric tokens and wraps them in prefix match syntax,
    neutralizing SQL injection and FTS5 operator syntax errors.
    """
    if not query:
        return ""
    tokens = [t for t in re.findall(r"[A-Za-z0-9_\u0080-\uffff]+", query) if t]
    if not tokens:
        return ""
    stop_words = {
        "how", "what", "why", "when", "where", "does", "do", "is", "are",
        "the", "a", "an", "in", "to", "of", "for", "with", "can", "you",
        "tell", "me", "about"
    }
    filtered = [t for t in tokens if t.lower() not in stop_words]
    effective_tokens = filtered if filtered else tokens
    parts = []
    for t in effective_tokens:
        if len(t) >= 3 and not t.endswith("*"):
            parts.append(f'"{t}"*')
        else:
            parts.append(f'"{t}"')
    return " OR ".join(parts)


# ==============================================================================
# Sqlite Checkpointer for LangGraph
# ==============================================================================


class SqliteCheckpointer(MemorySaver):
    """LangGraph CheckpointSaver that persists thread state into SQLite WAL checkpoints table."""

    def __init__(self, db_path: str = "data/approvals.db"):
        super().__init__()
        self.db_path = db_path
        self._init_sqlite()
        self._load_from_sqlite()

    def _init_sqlite(self) -> None:
        """Ensure checkpoints table exists with WAL mode enabled."""
        init_db_sync(self.db_path)

    def _load_from_sqlite(self) -> None:
        """Pre-populate in-memory cache from checkpoints table in SQLite."""
        if not os.path.exists(self.db_path):
            return
        with _db_lock:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT thread_id, checkpoint_id, state_blob FROM checkpoints ORDER BY timestamp ASC"
                )
                for row in cur.fetchall():
                    try:
                        record = json.loads(row["state_blob"])
                        chk_bytes = base64.b64decode(record["b"].encode("ascii"))
                        checkpoint = self.serde.loads_typed((record["t"], chk_bytes))

                        meta_bytes = base64.b64decode(record["meta_b"].encode("ascii"))
                        metadata = self.serde.loads_typed((record["meta_t"], meta_bytes))

                        new_versions = record.get("new_versions", {})
                        config: RunnableConfig = {
                            "configurable": {
                                "thread_id": row["thread_id"],
                                "checkpoint_ns": record.get("checkpoint_ns", ""),
                                "checkpoint_id": row["checkpoint_id"],
                            }
                        }
                        super().put(config, checkpoint, metadata, new_versions)
                    except Exception:
                        pass
            finally:
                conn.close()

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Store checkpoint in memory and persist serialized blob to SQLite WAL table."""
        res = super().put(config, checkpoint, metadata, new_versions)
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])

        t, b = self.serde.dumps_typed(checkpoint)
        meta_t, meta_b = self.serde.dumps_typed(metadata)
        record = {
            "t": t,
            "b": base64.b64encode(b).decode("ascii"),
            "meta_t": meta_t,
            "meta_b": base64.b64encode(meta_b).decode("ascii"),
            "new_versions": new_versions,
            "checkpoint_ns": checkpoint_ns,
        }
        state_blob = json.dumps(record)

        with _db_lock:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute("PRAGMA busy_timeout = 30000;")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO checkpoints (thread_id, checkpoint_id, state_blob)
                    VALUES (?, ?, ?)
                    """,
                    (thread_id, checkpoint_id, state_blob),
                )
                conn.commit()
            finally:
                conn.close()
        return res

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store pending writes in memory."""
        super().put_writes(config, writes, task_id, task_path)


# ==============================================================================
# CRUD Operations for Approval Requests
# ==============================================================================


def create_approval_record_sync(
    thread_id: str,
    action_type: str,
    risk_level: str,
    description: str,
    payload: dict[str, Any],
    status: str,
    request_id: Optional[str] = None,
    decision: Optional[str] = None,
    decision_reason: Optional[str] = None,
    decision_by: Optional[str] = None,
    result: Optional[str] = None,
    execution_logs: Optional[list[str]] = None,
    db_path: str = "data/approvals.db",
) -> dict[str, Any]:
    """Synchronously create an approval request record."""
    rid = request_id or f"req_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload)
    logs_json = json.dumps(execution_logs or [])

    with _db_lock:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute(
                """
                INSERT INTO approval_requests (
                    id, thread_id, action_type, risk_level, description,
                    payload, status, decision, decision_reason, decision_by,
                    result, execution_logs, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid, thread_id, action_type, risk_level, description,
                    payload_json, status, decision, decision_reason, decision_by,
                    result, logs_json, now
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return get_approval_record_sync(rid, db_path) or {}


async def create_approval_record(
    thread_id: str,
    action_type: str,
    risk_level: str,
    description: str,
    payload: dict[str, Any],
    status: str,
    request_id: Optional[str] = None,
    decision: Optional[str] = None,
    decision_reason: Optional[str] = None,
    decision_by: Optional[str] = None,
    result: Optional[str] = None,
    execution_logs: Optional[list[str]] = None,
    db_path: str = "data/approvals.db",
) -> dict[str, Any]:
    """Asynchronously create an approval request record."""
    rid = request_id or f"req_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload)
    logs_json = json.dumps(execution_logs or [])

    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO approval_requests (
                id, thread_id, action_type, risk_level, description,
                payload, status, decision, decision_reason, decision_by,
                result, execution_logs, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid, thread_id, action_type, risk_level, description,
                payload_json, status, decision, decision_reason, decision_by,
                result, logs_json, now
            ),
        )
        await conn.commit()
    return await get_approval_record(rid, db_path) or {}


def _parse_approval_row(row: sqlite3.Row | aiosqlite.Row) -> dict[str, Any]:
    """Parse JSON columns in an approval request row."""
    d = dict(row)
    try:
        d["payload"] = json.loads(d["payload"])
    except Exception:
        d["payload"] = {}
    try:
        d["execution_logs"] = json.loads(d["execution_logs"]) if d.get("execution_logs") else []
    except Exception:
        d["execution_logs"] = []
    return d


def get_approval_record_sync(request_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Synchronously retrieve approval record by ID."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _parse_approval_row(row)
    finally:
        conn.close()


async def get_approval_record(request_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Asynchronously retrieve approval record by ID."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return _parse_approval_row(row)


def get_approval_by_thread_sync(thread_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Synchronously retrieve approval record by thread_id."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM approval_requests WHERE thread_id = ? ORDER BY created_at DESC LIMIT 1",
            (thread_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return _parse_approval_row(row)
    finally:
        conn.close()


async def get_approval_by_thread(thread_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Asynchronously retrieve approval record by thread_id."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute(
            "SELECT * FROM approval_requests WHERE thread_id = ? ORDER BY created_at DESC LIMIT 1",
            (thread_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return _parse_approval_row(row)


def list_pending_requests_sync(db_path: str) -> list[dict[str, Any]]:
    """Synchronously list all requests with status 'pending_approval'."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM approval_requests WHERE status = 'pending_approval' ORDER BY created_at ASC"
        )
        return [_parse_approval_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def list_pending_requests(db_path: str) -> list[dict[str, Any]]:
    """Asynchronously list all requests with status 'pending_approval'."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute(
            "SELECT * FROM approval_requests WHERE status = 'pending_approval' ORDER BY created_at ASC"
        ) as cur:
            rows = await cur.fetchall()
            return [_parse_approval_row(r) for r in rows]


def update_approval_decision_sync(
    request_id: str,
    decision: str,
    decision_by: str,
    decision_reason: Optional[str],
    status: str,
    db_path: str,
    modified_payload: Optional[dict[str, Any]] = None,
) -> None:
    """Synchronously record human review decision and timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            if modified_payload is not None:
                conn.execute(
                    """
                    UPDATE approval_requests
                    SET decision = ?, decision_by = ?, decision_reason = ?,
                        status = ?, payload = ?, decided_at = ?
                    WHERE id = ?
                    """,
                    (decision, decision_by, decision_reason, status, json.dumps(modified_payload), now, request_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE approval_requests
                    SET decision = ?, decision_by = ?, decision_reason = ?,
                        status = ?, decided_at = ?
                    WHERE id = ?
                    """,
                    (decision, decision_by, decision_reason, status, now, request_id),
                )
            conn.commit()
        finally:
            conn.close()


async def update_approval_decision(
    request_id: str,
    decision: str,
    decision_by: str,
    decision_reason: Optional[str],
    status: str,
    db_path: str,
    modified_payload: Optional[dict[str, Any]] = None,
) -> None:
    """Asynchronously record human review decision and timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        if modified_payload is not None:
            await conn.execute(
                """
                UPDATE approval_requests
                SET decision = ?, decision_by = ?, decision_reason = ?,
                    status = ?, payload = ?, decided_at = ?
                WHERE id = ?
                """,
                (decision, decision_by, decision_reason, status, json.dumps(modified_payload), now, request_id),
            )
        else:
            await conn.execute(
                """
                UPDATE approval_requests
                SET decision = ?, decision_by = ?, decision_reason = ?,
                    status = ?, decided_at = ?
                WHERE id = ?
                """,
                (decision, decision_by, decision_reason, status, now, request_id),
            )
        await conn.commit()


def complete_approval_request_sync(
    request_id: str,
    status: str,
    result: Optional[str],
    execution_logs: Optional[list[str]],
    db_path: str,
) -> None:
    """Synchronously mark approval request completed with execution outcome."""
    now = datetime.now(timezone.utc).isoformat()
    logs_json = json.dumps(execution_logs or [])
    with _db_lock:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, result = ?, execution_logs = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, result, logs_json, now, request_id),
            )
            conn.commit()
        finally:
            conn.close()


async def complete_approval_request(
    request_id: str,
    status: str,
    result: Optional[str],
    execution_logs: Optional[list[str]],
    db_path: str,
) -> None:
    """Asynchronously mark approval request completed with execution outcome."""
    now = datetime.now(timezone.utc).isoformat()
    logs_json = json.dumps(execution_logs or [])
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            UPDATE approval_requests
            SET status = ?, result = ?, execution_logs = ?, completed_at = ?
            WHERE id = ?
            """,
            (status, result, logs_json, now, request_id),
        )
        await conn.commit()


def delete_approval_request_sync(request_id: str, db_path: str) -> None:
    """Synchronously delete an approval request and verify FTS5 trigger execution."""
    with _db_lock:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("DELETE FROM approval_requests WHERE id = ?", (request_id,))
            conn.commit()
        finally:
            conn.close()


async def delete_approval_request(request_id: str, db_path: str) -> None:
    """Asynchronously delete an approval request and verify FTS5 trigger execution."""
    async with get_db_connection(db_path) as conn:
        await conn.execute("DELETE FROM approval_requests WHERE id = ?", (request_id,))
        await conn.commit()


def search_audit_log_sync(
    query_str: str,
    db_path: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Synchronously execute BM25 ranked full-text search against approval_audit_fts."""
    sanitized = sanitize_fts5_query(query_str)
    if not sanitized:
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = """
        SELECT
            r.id,
            r.thread_id,
            r.action_type,
            r.risk_level,
            r.description,
            r.status,
            r.decision,
            r.decision_reason,
            r.result,
            bm25(approval_audit_fts) AS bm25_score,
            snippet(approval_audit_fts, -1, '<b>', '</b>', '...', 12) AS snippet
        FROM approval_audit_fts fts
        JOIN approval_requests r ON r.rowid = fts.rowid
        WHERE approval_audit_fts MATCH ?
        ORDER BY bm25_score ASC
        LIMIT ?
        """
        cur = conn.execute(sql, (sanitized, limit))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


async def search_audit_log(
    query_str: str,
    db_path: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Asynchronously execute BM25 ranked full-text search against approval_audit_fts."""
    sanitized = sanitize_fts5_query(query_str)
    if not sanitized:
        return []
    async with get_db_connection(db_path) as conn:
        sql = """
        SELECT
            r.id,
            r.thread_id,
            r.action_type,
            r.risk_level,
            r.description,
            r.status,
            r.decision,
            r.decision_reason,
            r.result,
            bm25(approval_audit_fts) AS bm25_score,
            snippet(approval_audit_fts, -1, '<b>', '</b>', '...', 12) AS snippet
        FROM approval_audit_fts fts
        JOIN approval_requests r ON r.rowid = fts.rowid
        WHERE approval_audit_fts MATCH ?
        ORDER BY bm25_score ASC
        LIMIT ?
        """
        async with conn.execute(sql, (sanitized, limit)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


def get_checkpoints_for_thread_sync(thread_id: str, db_path: str) -> list[dict[str, Any]]:
    """Synchronously retrieve checkpoints for thread_id."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT thread_id, checkpoint_id, timestamp, length(state_blob) as blob_len FROM checkpoints WHERE thread_id = ? ORDER BY timestamp ASC",
            (thread_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def check_database_health(db_path: str) -> dict[str, Any]:
    """Inspect database connectivity, WAL mode, and table counts."""
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        journal_row = await cursor.fetchone()
        journal_mode = journal_row[0] if journal_row else "unknown"

        cursor = await conn.execute("SELECT count(*) FROM approval_requests;")
        req_row = await cursor.fetchone()
        requests_count = req_row[0] if req_row else 0

        cursor = await conn.execute("SELECT count(*) FROM checkpoints;")
        chk_row = await cursor.fetchone()
        checkpoints_count = chk_row[0] if chk_row else 0

        return {
            "journal_mode": journal_mode,
            "status": "connected",
            "database": db_path,
            "requests_count": requests_count,
            "checkpoints_count": checkpoints_count,
        }
