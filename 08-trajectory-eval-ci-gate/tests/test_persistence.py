"""Tier 3: SQLite WAL Mode, FTS5 Virtual Tables, and Automated Triggers."""

import sqlite3
from app.database import (
    get_db_connection,
    get_eval_run_sync,
    get_golden_dag_sync,
    save_eval_run_sync,
    save_golden_dag_sync,
    search_trajectory_logs_fts_sync,
)
from app.models import EvalRunResponse, EvalVerdict, GoldenDAG


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

    def test_golden_dag_crud(self, temp_db: str):
        dag = GoldenDAG(
            dag_id="dag-test-crud",
            name="Test CRUD DAG",
            allowed_nodes=["start", "finish"],
            allowed_transitions=[["start", "finish"]],
            initial_nodes=["start"],
            terminal_nodes=["finish"],
        )
        save_golden_dag_sync(temp_db, dag, "2026-11-02T12:00:00Z")

        fetched = get_golden_dag_sync(temp_db, "dag-test-crud")
        assert fetched is not None
        assert fetched.dag_id == "dag-test-crud"
        assert fetched.allowed_nodes == ["start", "finish"]

    def test_fts5_triggers_insert_and_bm25_search(self, temp_db: str):
        eval_resp = EvalRunResponse(
            eval_id="eval-fts-1",
            pr_number=12,
            commit_sha="c0ffee",
            dag_id="golden-default",
            total_evaluated=1,
            passed_count=0,
            failed_count=1,
            verdict=EvalVerdict.BLOCK,
        )
        logs = [{
            "log_id": "log-fts-1",
            "trajectory_id": "traj-corrupt-9",
            "tool_sequence": ["checkout_branch", "unauthorized_delete_database"],
            "is_match": False,
            "deviation_reason": "Severe anomaly: unauthorized database manipulation detected in trajectory",
        }]

        save_eval_run_sync(temp_db, eval_resp, logs)

        hits = search_trajectory_logs_fts_sync(temp_db, "manipulation")
        assert len(hits) == 1
        assert hits[0].log_id == "log-fts-1"
        assert "manipulation" in hits[0].snippet.lower()
