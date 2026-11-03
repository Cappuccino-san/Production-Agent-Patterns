"""Tier 3: SQLite WAL mode, triggers, FTS5 BM25 search, and checkpointer persistence tests."""

import sqlite3
import pytest

from app.database import (
    check_database_health,
    complete_approval_request,
    complete_approval_request_sync,
    create_approval_record,
    create_approval_record_sync,
    delete_approval_request,
    delete_approval_request_sync,
    get_approval_by_thread,
    get_approval_by_thread_sync,
    get_approval_record,
    get_approval_record_sync,
    get_checkpoints_for_thread_sync,
    list_pending_requests,
    list_pending_requests_sync,
    sanitize_fts5_query,
    search_audit_log,
    search_audit_log_sync,
    update_approval_decision,
    update_approval_decision_sync,
)


class TestSQLiteWALConfiguration:
    """Validate SQLite WAL pragmas and table structures."""

    def test_wal_pragmas_enabled(self, temp_db: str):
        conn = sqlite3.connect(temp_db)
        try:
            cur = conn.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0]
            assert journal_mode.lower() == "wal"

            cur = conn.execute("PRAGMA synchronous;")
            sync_mode = cur.fetchone()[0]
            # synchronous = NORMAL (1) or FULL (2)
            assert sync_mode in (1, 2, "1", "2", "NORMAL")

            cur = conn.execute("PRAGMA foreign_keys;")
            fk_mode = cur.fetchone()[0]
            assert fk_mode in (0, 1)

            cur = conn.execute("PRAGMA busy_timeout;")
            timeout = cur.fetchone()[0]
            assert timeout >= 0
        finally:
            conn.close()

    def test_tables_created(self, temp_db: str):
        conn = sqlite3.connect(temp_db)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall()]
            assert "approval_requests" in tables
            assert "checkpoints" in tables
            assert "approval_audit_fts" in tables
        finally:
            conn.close()


class TestApprovalRecordCRUD:
    """Validate CRUD operations for approval requests in SQLite."""

    def test_sync_crud_lifecycle(self, temp_db: str):
        # Create
        rec = create_approval_record_sync(
            thread_id="th_crud_1",
            action_type="drop_table",
            risk_level="CRITICAL",
            description="Drop analytics staging table",
            payload={"table": "analytics_staging"},
            status="pending_approval",
            request_id="req_crud_1",
            db_path=temp_db,
        )
        assert rec["id"] == "req_crud_1"
        assert rec["status"] == "pending_approval"

        # Read by ID
        fetched = get_approval_record_sync("req_crud_1", temp_db)
        assert fetched is not None
        assert fetched["action_type"] == "drop_table"

        # Read by thread
        by_thread = get_approval_by_thread_sync("th_crud_1", temp_db)
        assert by_thread is not None
        assert by_thread["id"] == "req_crud_1"

        # Pending list
        pending = list_pending_requests_sync(temp_db)
        assert any(p["id"] == "req_crud_1" for p in pending)

        # Update decision
        update_approval_decision_sync(
            request_id="req_crud_1",
            decision="approve",
            decision_by="admin_alice",
            decision_reason="Signed off",
            status="approved",
            db_path=temp_db,
        )
        decided = get_approval_record_sync("req_crud_1", temp_db)
        assert decided["decision"] == "approve"
        assert decided["decided_at"] is not None

        # Complete
        complete_approval_request_sync(
            request_id="req_crud_1",
            status="completed",
            result="Table analytics_staging dropped",
            execution_logs=["Executed drop"],
            db_path=temp_db,
        )
        completed = get_approval_record_sync("req_crud_1", temp_db)
        assert completed["status"] == "completed"
        assert completed["completed_at"] is not None

        # Delete
        delete_approval_request_sync("req_crud_1", temp_db)
        assert get_approval_record_sync("req_crud_1", temp_db) is None

    @pytest.mark.asyncio
    async def test_async_crud_lifecycle(self, temp_db: str):
        # Create
        rec = await create_approval_record(
            thread_id="th_crud_async",
            action_type="delete_user",
            risk_level="HIGH",
            description="Delete account for user 99",
            payload={"user_id": "99"},
            status="pending_approval",
            request_id="req_crud_async",
            db_path=temp_db,
        )
        assert rec["id"] == "req_crud_async"

        # Read
        fetched = await get_approval_record("req_crud_async", temp_db)
        assert fetched is not None
        assert fetched["payload"]["user_id"] == "99"

        # Thread lookup
        by_thread = await get_approval_by_thread("th_crud_async", temp_db)
        assert by_thread["id"] == "req_crud_async"

        # Pending
        pending = await list_pending_requests(temp_db)
        assert any(p["id"] == "req_crud_async" for p in pending)

        # Update decision with modification
        await update_approval_decision(
            request_id="req_crud_async",
            decision="modify",
            decision_by="manager_bob",
            decision_reason="Soft delete only",
            status="modified",
            db_path=temp_db,
            modified_payload={"user_id": "99", "soft_delete": True},
        )
        decided = await get_approval_record("req_crud_async", temp_db)
        assert decided["payload"]["soft_delete"] is True

        # Complete
        await complete_approval_request(
            request_id="req_crud_async",
            status="completed",
            result="User 99 soft deleted",
            execution_logs=["Applied soft delete"],
            db_path=temp_db,
        )

        # Delete
        await delete_approval_request("req_crud_async", temp_db)
        assert await get_approval_record("req_crud_async", temp_db) is None


class TestFTS5SynchronizationTriggers:
    """Validate FTS5 virtual table sync triggers on insert, update, and delete."""

    def test_triggers_insert_update_delete_sync(self, temp_db: str):
        # 1. Insert triggers trg_approvals_ai
        create_approval_record_sync(
            thread_id="th_fts_1",
            action_type="terminate_ec2_instances",
            risk_level="CRITICAL",
            description="Terminate rogue crypto mining worker nodes",
            payload={"instance_ids": ["i-rogue123"]},
            status="pending_approval",
            request_id="req_fts_1",
            db_path=temp_db,
        )

        res_insert = search_audit_log_sync("crypto mining", temp_db)
        assert len(res_insert) >= 1
        assert res_insert[0]["id"] == "req_fts_1"
        assert res_insert[0]["snippet"] is not None

        # 2. Update triggers trg_approvals_au
        complete_approval_request_sync(
            request_id="req_fts_1",
            status="completed",
            result="Successfully terminated instance i-rogue123 with quarantine tag",
            execution_logs=["Instance terminated"],
            db_path=temp_db,
        )

        res_update = search_audit_log_sync("quarantine tag", temp_db)
        assert len(res_update) >= 1
        assert res_update[0]["id"] == "req_fts_1"

        # 3. Delete triggers trg_approvals_ad
        delete_approval_request_sync("req_fts_1", temp_db)
        res_delete = search_audit_log_sync("crypto mining", temp_db)
        assert len(res_delete) == 0

    @pytest.mark.asyncio
    async def test_async_search_audit_log(self, temp_db: str):
        await create_approval_record(
            thread_id="th_fts_async",
            action_type="patch_security_group",
            risk_level="MEDIUM",
            description="Restrict inbound port 22 to bastion IP",
            payload={"port": 22, "cidr": "10.0.0.1/32"},
            status="completed",
            request_id="req_fts_async",
            result="Port 22 restricted to bastion successfully",
            db_path=temp_db,
        )

        results = await search_audit_log("bastion security", temp_db)
        assert len(results) >= 1
        assert results[0]["id"] == "req_fts_async"
        assert results[0]["bm25_score"] <= 0.0  # SQLite BM25 scores are typically negative or zero


class TestFTS5QuerySanitization:
    """Validate query sanitization prevents syntax errors and SQL injection."""

    def test_sanitize_clean_query(self):
        assert '"database"*' in sanitize_fts5_query("database")
        assert '"backup"*' in sanitize_fts5_query("backup")

    def test_sanitize_special_characters(self):
        # Characters like ', ", *, (, ), OR, AND should be neutralized
        res = sanitize_fts5_query("drop table; -- ' OR 1=1")
        assert "drop" in res
        assert "table" in res
        assert "--" not in res
        assert ";" not in res

    def test_sanitize_empty_or_whitespace(self):
        assert sanitize_fts5_query("") == ""
        assert sanitize_fts5_query("   ") == ""
        assert sanitize_fts5_query("!@#$%^&*()") == ""


class TestDatabaseHealthAndCheckpoints:
    """Validate checkpointer persistence and system health check."""

    def test_checkpoints_table_persistence(self, temp_db: str, agent_graph):
        from app.agent.graph import submit_action_to_graph

        submit_action_to_graph(
            graph=agent_graph,
            thread_id="th_chk_test_01",
            request_id="req_chk_test_01",
            action_type="drop_database",
            description="Drop analytics db",
            payload={"db": "analytics"},
        )

        checkpoints = get_checkpoints_for_thread_sync("th_chk_test_01", temp_db)
        assert len(checkpoints) >= 1
        assert checkpoints[0]["thread_id"] == "th_chk_test_01"
        assert checkpoints[0]["blob_len"] > 0

    @pytest.mark.asyncio
    async def test_database_health_reporting(self, temp_db: str):
        health = await check_database_health(temp_db)
        assert health["status"] == "connected"
        assert health["journal_mode"].lower() == "wal"
        assert health["requests_count"] >= 0
        assert health["checkpoints_count"] >= 0
