"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for Sanitization Proxy."""

import json
import os
import sqlite3
from typing import Optional
from app.models import ActionTaken, ProxySearchHit, SanitizationResult


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
            CREATE TABLE IF NOT EXISTS intercepted_messages (
                message_id TEXT PRIMARY KEY,
                sender_agent TEXT NOT NULL,
                receiver_agent TEXT NOT NULL,
                raw_content TEXT NOT NULL,
                sanitized_content TEXT NOT NULL,
                risk_score REAL NOT NULL,
                action_taken TEXT NOT NULL,
                matched_rules_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """)

            # FTS5 Virtual Table
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS intercepted_messages_fts USING fts5(
                message_id UNINDEXED,
                sender_agent,
                receiver_agent,
                action_taken,
                raw_content,
                sanitized_content,
                content='intercepted_messages',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            # Automated Sync Triggers
            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS intercepted_messages_ai AFTER INSERT ON intercepted_messages BEGIN
                INSERT INTO intercepted_messages_fts(rowid, message_id, sender_agent, receiver_agent, action_taken, raw_content, sanitized_content)
                VALUES (new.rowid, new.message_id, new.sender_agent, new.receiver_agent, new.action_taken, new.raw_content, new.sanitized_content);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS intercepted_messages_ad AFTER DELETE ON intercepted_messages BEGIN
                INSERT INTO intercepted_messages_fts(intercepted_messages_fts, rowid, message_id, sender_agent, receiver_agent, action_taken, raw_content, sanitized_content)
                VALUES('delete', old.rowid, old.message_id, old.sender_agent, old.receiver_agent, old.action_taken, old.raw_content, old.sanitized_content);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS intercepted_messages_au AFTER UPDATE ON intercepted_messages BEGIN
                INSERT INTO intercepted_messages_fts(intercepted_messages_fts, rowid, message_id, sender_agent, receiver_agent, action_taken, raw_content, sanitized_content)
                VALUES('delete', old.rowid, old.message_id, old.sender_agent, old.receiver_agent, old.action_taken, old.raw_content, old.sanitized_content);
                INSERT INTO intercepted_messages_fts(rowid, message_id, sender_agent, receiver_agent, action_taken, raw_content, sanitized_content)
                VALUES (new.rowid, new.message_id, new.sender_agent, new.receiver_agent, new.action_taken, new.raw_content, new.sanitized_content);
            END;
            """)
    finally:
        conn.close()


def save_intercepted_message_sync(db_path: str, raw_content: str, result: SanitizationResult) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO intercepted_messages (
                    message_id, sender_agent, receiver_agent,
                    raw_content, sanitized_content, risk_score,
                    action_taken, matched_rules_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    sanitized_content=excluded.sanitized_content,
                    risk_score=excluded.risk_score,
                    action_taken=excluded.action_taken;
                """,
                (
                    result.message_id,
                    result.sender_agent,
                    result.receiver_agent,
                    raw_content,
                    result.sanitized_content,
                    result.risk_score,
                    result.action_taken.value,
                    json.dumps(result.matched_rules),
                    result.processed_at,
                ),
            )
    finally:
        conn.close()


def get_intercepted_message_sync(db_path: str, message_id: str) -> Optional[dict]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM intercepted_messages WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["matched_rules"] = json.loads(res["matched_rules_json"])
        return res
    finally:
        conn.close()


def search_intercepted_messages_fts_sync(db_path: str, query: str, limit: int = 10) -> list[ProxySearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                message_id,
                sender_agent,
                receiver_agent,
                action_taken,
                snippet(intercepted_messages_fts, 4, '<b>', '</b>', '...', 12) AS snippet,
                bm25(intercepted_messages_fts) AS rank
            FROM intercepted_messages_fts
            WHERE intercepted_messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            ProxySearchHit(
                message_id=r["message_id"],
                sender_agent=r["sender_agent"],
                receiver_agent=r["receiver_agent"],
                action_taken=r["action_taken"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
