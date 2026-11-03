"""Tier 3: SQLite WAL Mode, FTS5 Virtual Tables, and Automated Sync Triggers."""

import sqlite3
from app.database import (
    get_db_connection,
    get_gate_action_sync,
    save_gate_action_sync,
    save_gate_audit_sync,
    search_gate_audits_fts_sync,
)
from app.models import ActionType, GateActionRecord, GateAuditLog, GateStatus


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

    def test_gate_action_crud(self, temp_db: str):
        record = GateActionRecord(
            action_id="act-crud-1",
            action_type=ActionType.PRIVILEGED_ACCESS_GRANT,
            status=GateStatus.PENDING_APPROVAL,
            risk_score=70.0,
            description="Grant emergency root IAM role for incident #402",
            payload={"duration_hours": 4},
            expires_at="2026-11-05T12:00:00Z",
            created_at="2026-11-02T12:00:00Z",
            updated_at="2026-11-02T12:00:00Z",
        )
        save_gate_action_sync(temp_db, record)

        fetched = get_gate_action_sync(temp_db, "act-crud-1")
        assert fetched is not None
        assert fetched.action_id == "act-crud-1"
        assert fetched.status == GateStatus.PENDING_APPROVAL

    def test_fts5_triggers_insert_and_bm25_search(self, temp_db: str):
        # Create action first for FK
        record = GateActionRecord(
            action_id="act-fts-1",
            action_type=ActionType.DEPLOY_PRODUCTION,
            status=GateStatus.APPROVED,
            risk_score=60.0,
            description="Deploy payment microservice",
            payload={},
            expires_at="2026-11-05T12:00:00Z",
            created_at="2026-11-02T12:00:00Z",
            updated_at="2026-11-02T12:00:00Z",
        )
        save_gate_action_sync(temp_db, record)

        audit = GateAuditLog(
            audit_id="aud-fts-1",
            action_id="act-fts-1",
            decision="APPROVED_AND_EXECUTED",
            approver_id="U_SECURITY_OFFICER",
            note="Verified zero vulnerabilities in Snyk scan for payment service",
        )
        save_gate_audit_sync(temp_db, audit)

        # Query FTS5 table
        hits = search_gate_audits_fts_sync(temp_db, "vulnerabilities")
        assert len(hits) == 1
        assert hits[0].audit_id == "aud-fts-1"
        assert "vulnerabilities" in hits[0].snippet.lower()
