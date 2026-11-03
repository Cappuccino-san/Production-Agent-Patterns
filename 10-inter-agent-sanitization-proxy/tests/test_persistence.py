"""Tier 3: SQLite WAL Mode, FTS5 Virtual Tables, and Automated Triggers."""

import sqlite3
from app.database import (
    get_db_connection,
    get_intercepted_message_sync,
    save_intercepted_message_sync,
    search_intercepted_messages_fts_sync,
)
from app.models import ActionTaken, SanitizationResult


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

    def test_save_and_retrieve_intercepted_message(self, temp_db: str):
        result = SanitizationResult(
            message_id="msg-persist-1",
            sender_agent="Agent1",
            receiver_agent="Agent2",
            is_clean=False,
            sanitized_content="Scrubbed payload",
            risk_score=75.0,
            action_taken=ActionTaken.SANITIZED,
            matched_rules=["Delimiter Escape / Tag Injection"],
        )
        save_intercepted_message_sync(temp_db, "Raw dangerous content", result)

        fetched = get_intercepted_message_sync(temp_db, "msg-persist-1")
        assert fetched is not None
        assert fetched["message_id"] == "msg-persist-1"
        assert fetched["action_taken"] == "SANITIZED"
        assert "Delimiter Escape / Tag Injection" in fetched["matched_rules"]

    def test_fts5_triggers_insert_and_bm25_search(self, temp_db: str):
        result = SanitizationResult(
            message_id="msg-fts-1",
            sender_agent="PenTestAgent",
            receiver_agent="ProductionAgent",
            is_clean=False,
            sanitized_content="[BLOCKED]",
            risk_score=90.0,
            action_taken=ActionTaken.BLOCKED_QUARANTINE,
            matched_rules=["System Prompt Override Attempt"],
        )
        raw_content = "Attempting to circumvent safety rails using exfiltration protocol."
        save_intercepted_message_sync(temp_db, raw_content, result)

        hits = search_intercepted_messages_fts_sync(temp_db, "exfiltration")
        assert len(hits) == 1
        assert hits[0].message_id == "msg-fts-1"
        assert "exfiltration" in hits[0].snippet.lower()
