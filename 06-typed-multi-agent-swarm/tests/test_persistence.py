"""Tier 3: SQLite WAL Mode, FTS5 Search, and Automated Trigger Persistence Tests."""

import sqlite3
from app.database import (
    get_db_connection,
    get_swarm_task_sync,
    init_db_sync,
    save_swarm_artifact_sync,
    save_swarm_step_sync,
    save_swarm_task_sync,
    search_artifacts_fts_sync,
)
from app.models import SwarmStatus


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

    def test_task_save_and_retrieve(self, temp_db: str):
        task_id = "task-persist-1"
        save_swarm_task_sync(
            temp_db,
            task_id=task_id,
            task_description="Build event sourcing engine",
            status=SwarmStatus.COMPLETED,
            iteration=1,
            max_iterations=3,
            created_at="2026-11-02T12:00:00Z",
            updated_at="2026-11-02T12:01:00Z",
        )

        save_swarm_artifact_sync(
            temp_db,
            artifact_id="art-1",
            task_id=task_id,
            artifact_type="research",
            title="Event Sourcing Research",
            content="Use append-only immutable logs and snapshot compaction.",
            metadata={"confidence": 0.98},
            created_at="2026-11-02T12:00:10Z",
        )

        record = get_swarm_task_sync(temp_db, task_id)
        assert record is not None
        assert record["task_id"] == task_id
        assert record["status"] == "COMPLETED"
        assert len(record["artifacts"]) == 1
        assert record["artifacts"][0]["title"] == "Event Sourcing Research"

    def test_fts5_triggers_insert_and_bm25_search(self, temp_db: str):
        task_id = "task-search-1"
        save_swarm_task_sync(
            temp_db,
            task_id=task_id,
            task_description="Searchable task",
            status=SwarmStatus.COMPLETED,
            iteration=1,
            max_iterations=3,
            created_at="2026-11-02T12:00:00Z",
            updated_at="2026-11-02T12:01:00Z",
        )

        # Insert artifact into relational table; trigger should populate FTS5 table
        save_swarm_artifact_sync(
            temp_db,
            artifact_id="art-fts-1",
            task_id=task_id,
            artifact_type="code",
            title="Consensus Implementation",
            content="class RaftConsensusModule: def append_entries(self): pass",
            metadata={},
            created_at="2026-11-02T12:00:20Z",
        )

        # Query FTS5 table
        hits = search_artifacts_fts_sync(temp_db, "RaftConsensusModule")
        assert len(hits) == 1
        assert hits[0].artifact_id == "art-fts-1"
        assert "<b>RaftConsensusModule</b>" in hits[0].content_snippet or "RaftConsensusModule" in hits[0].content_snippet

    def test_fts5_delete_trigger(self, temp_db: str):
        task_id = "task-del-1"
        save_swarm_task_sync(
            temp_db,
            task_id=task_id,
            task_description="Task to delete",
            status=SwarmStatus.COMPLETED,
            iteration=1,
            max_iterations=3,
            created_at="2026-11-02T12:00:00Z",
            updated_at="2026-11-02T12:01:00Z",
        )
        save_swarm_artifact_sync(
            temp_db,
            artifact_id="art-del-1",
            task_id=task_id,
            artifact_type="code",
            title="Temporary Code",
            content="Ephemeral artifact to verify delete trigger cleanup.",
            metadata={},
            created_at="2026-11-02T12:00:00Z",
        )

        # Confirm found
        hits = search_artifacts_fts_sync(temp_db, "Ephemeral")
        assert len(hits) == 1

        # Delete from relational table
        conn = get_db_connection(temp_db)
        with conn:
            conn.execute("DELETE FROM swarm_artifacts WHERE artifact_id = 'art-del-1';")
        conn.close()

        # Confirm deleted from FTS5 index via trigger
        hits_after = search_artifacts_fts_sync(temp_db, "Ephemeral")
        assert len(hits_after) == 0
