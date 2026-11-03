"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for HITL Slack Gate."""

import json
import os
import sqlite3
from typing import Any, Optional
from app.models import AuditSearchHit, GateActionRecord, GateAuditLog, GateStatus


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Open SQLite connection with WAL mode and enterprise pragmas."""
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
    """Synchronously create tables, FTS5 virtual tables, and triggers."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS hitl_actions (
                action_id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_score REAL NOT NULL,
                description TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approver_id TEXT,
                decision_reason TEXT,
                execution_result_json TEXT
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS hitl_audits (
                audit_id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL REFERENCES hitl_actions(action_id) ON DELETE CASCADE,
                decision TEXT NOT NULL,
                approver_id TEXT NOT NULL,
                note TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS hitl_audits_fts USING fts5(
                audit_id UNINDEXED,
                action_id UNINDEXED,
                decision,
                approver_id,
                note,
                content='hitl_audits',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS hitl_audits_ai AFTER INSERT ON hitl_audits BEGIN
                INSERT INTO hitl_audits_fts(rowid, audit_id, action_id, decision, approver_id, note)
                VALUES (new.rowid, new.audit_id, new.action_id, new.decision, new.approver_id, new.note);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS hitl_audits_ad AFTER DELETE ON hitl_audits BEGIN
                INSERT INTO hitl_audits_fts(hitl_audits_fts, rowid, audit_id, action_id, decision, approver_id, note)
                VALUES('delete', old.rowid, old.audit_id, old.action_id, old.decision, old.approver_id, old.note);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS hitl_audits_au AFTER UPDATE ON hitl_audits BEGIN
                INSERT INTO hitl_audits_fts(hitl_audits_fts, rowid, audit_id, action_id, decision, approver_id, note)
                VALUES('delete', old.rowid, old.audit_id, old.action_id, old.decision, old.approver_id, old.note);
                INSERT INTO hitl_audits_fts(rowid, audit_id, action_id, decision, approver_id, note)
                VALUES (new.rowid, new.audit_id, new.action_id, new.decision, new.approver_id, new.note);
            END;
            """)
    finally:
        conn.close()


def save_gate_action_sync(db_path: str, record: GateActionRecord) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO hitl_actions (
                    action_id, action_type, status, risk_score, description,
                    payload_json, expires_at, created_at, updated_at,
                    approver_id, decision_reason, execution_result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(action_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    approver_id=excluded.approver_id,
                    decision_reason=excluded.decision_reason,
                    execution_result_json=excluded.execution_result_json;
                """,
                (
                    record.action_id,
                    record.action_type.value,
                    record.status.value,
                    record.risk_score,
                    record.description,
                    json.dumps(record.payload),
                    record.expires_at,
                    record.created_at,
                    record.updated_at,
                    record.approver_id,
                    record.decision_reason,
                    json.dumps(record.execution_result) if record.execution_result else None,
                ),
            )
    finally:
        conn.close()


def get_gate_action_sync(db_path: str, action_id: str) -> Optional[GateActionRecord]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hitl_actions WHERE action_id = ?", (action_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return GateActionRecord(
            action_id=row["action_id"],
            action_type=row["action_type"],
            status=GateStatus(row["status"]),
            risk_score=row["risk_score"],
            description=row["description"],
            payload=json.loads(row["payload_json"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approver_id=row["approver_id"],
            decision_reason=row["decision_reason"],
            execution_result=json.loads(row["execution_result_json"]) if row["execution_result_json"] else None,
        )
    finally:
        conn.close()


def claim_gate_action_sync(db_path: str, action_id: str) -> bool:
    """Atomically transition status from PENDING_APPROVAL to PROCESSING to prevent race conditions."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                UPDATE hitl_actions 
                SET status = 'PROCESSING' 
                WHERE action_id = ? AND status = 'PENDING_APPROVAL';
                """,
                (action_id,),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


def save_gate_audit_sync(db_path: str, audit: GateAuditLog) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO hitl_audits (audit_id, action_id, decision, approver_id, note, timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (audit.audit_id, audit.action_id, audit.decision, audit.approver_id, audit.note, audit.timestamp),
            )
    finally:
        conn.close()


def search_gate_audits_fts_sync(db_path: str, query: str, limit: int = 10) -> list[AuditSearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                audit_id,
                action_id,
                decision,
                snippet(hitl_audits_fts, 4, '<b>', '</b>', '...', 10) AS snippet,
                bm25(hitl_audits_fts) AS rank
            FROM hitl_audits_fts
            WHERE hitl_audits_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            AuditSearchHit(
                audit_id=r["audit_id"],
                action_id=r["action_id"],
                decision=r["decision"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
