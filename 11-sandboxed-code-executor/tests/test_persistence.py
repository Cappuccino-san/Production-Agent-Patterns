"""Tier 3: SQLite WAL Mode, FTS5 Virtual Tables, and Automated Triggers."""

import sqlite3
from app.database import (
    get_db_connection,
    get_execution_result_sync,
    save_execution_result_sync,
    search_executions_fts_sync,
)
from app.models import ExecutionResult, ExecutionStatus


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

    def test_execution_result_crud(self, temp_db: str):
        res = ExecutionResult(
            execution_id="exec-crud-1",
            status=ExecutionStatus.SUCCESS,
            exit_code=0,
            stdout="42\n",
            stderr="",
            execution_time_ms=15.0,
            egress_blocked=True,
            ast_violations=[],
        )
        save_execution_result_sync(temp_db, "print(6 * 7)", res)

        fetched = get_execution_result_sync(temp_db, "exec-crud-1")
        assert fetched is not None
        assert fetched["execution_id"] == "exec-crud-1"
        assert fetched["status"] == "SUCCESS"
        assert fetched["stdout"] == "42\n"

    def test_fts5_triggers_insert_and_bm25_search(self, temp_db: str):
        res = ExecutionResult(
            execution_id="exec-fts-1",
            status=ExecutionStatus.RUNTIME_ERROR,
            exit_code=1,
            stdout="",
            stderr="ZeroDivisionError: division by zero encountered in calculation",
            execution_time_ms=8.0,
            egress_blocked=True,
        )
        code = "result = 100 / 0"
        save_execution_result_sync(temp_db, code, res)

        hits = search_executions_fts_sync(temp_db, "ZeroDivisionError")
        assert len(hits) == 1
        assert hits[0].execution_id == "exec-fts-1"
        assert "ZeroDivisionError" in hits[0].snippet
