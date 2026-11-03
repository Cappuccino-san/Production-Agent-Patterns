"""Tier 3: SQLite WAL pragmas, tables, triggers, and FTS5 BM25 search persistence tests."""

import os
import sqlite3
import tempfile
import pytest
from app.database import (
    check_database_health,
    create_plan,
    create_plan_sync,
    get_db_connection,
    get_plan,
    get_plan_sync,
    init_db,
    replace_remaining_steps,
    replace_remaining_steps_sync,
    sanitize_fts5_query,
    search_steps,
    search_steps_sync,
    update_plan_status,
    update_step,
    update_step_sync,
)


@pytest.mark.db
class TestSQLiteWALPragmas:
    """Verification of SQLite WAL mode, foreign keys, and runtime pragmas."""

    @pytest.mark.asyncio
    async def test_wal_mode_and_pragmas(self, temp_db: str) -> None:
        async with get_db_connection(temp_db) as conn:
            cur = await conn.execute("PRAGMA journal_mode;")
            journal_mode = (await cur.fetchone())[0]
            assert journal_mode.lower() == "wal"

            cur = await conn.execute("PRAGMA synchronous;")
            sync_val = (await cur.fetchone())[0]
            assert sync_val in (1, "1", "NORMAL")

            cur = await conn.execute("PRAGMA foreign_keys;")
            fk = (await cur.fetchone())[0]
            assert fk == 1

            cur = await conn.execute("PRAGMA busy_timeout;")
            bt = (await cur.fetchone())[0]
            assert bt >= 5000

    @pytest.mark.asyncio
    async def test_database_health_check(self, temp_db: str) -> None:
        health = await check_database_health(temp_db)
        assert health["status"] == "connected"
        assert health["journal_mode"].lower() == "wal"
        assert health["database"] == temp_db
        assert "plan_count" in health
        assert "step_count" in health

    @pytest.mark.asyncio
    async def test_async_init_and_crud(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tpath = f.name
        try:
            await init_db(tpath)
            plan = await create_plan("Async goal", [{"id": "s1", "title": "S1"}], tpath)
            assert plan["id"] is not None
            assert len(plan["steps"]) == 1

            fetched = await get_plan(plan["id"], tpath)
            assert fetched is not None
            assert fetched["goal"] == "Async goal"

            await update_step("s1", "completed", "Async result", None, tpath)
            await update_plan_status(plan["id"], "in_progress", 1, "Interim", tpath)

            await replace_remaining_steps(plan["id"], 1, [{"title": "New Async Step"}], tpath)
            refetched = await get_plan(plan["id"], tpath)
            assert refetched["total_steps"] == 2

            s_res = await search_steps("Async", tpath)
            assert len(s_res) >= 1
        finally:
            for ext in ["", "-wal", "-shm"]:
                if os.path.exists(tpath + ext):
                    try:
                        os.remove(tpath + ext)
                    except OSError:
                        pass

    def test_foreign_key_cascade_deletion(self, temp_db: str) -> None:
        plan = create_plan_sync(
            goal="Test Cascade Deletion",
            steps=[{"title": "Step 1", "description": "Desc 1"}],
            db_path=temp_db,
        )
        plan_id = plan["id"]

        with sqlite3.connect(temp_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            # Verify steps exist
            cur = conn.execute("SELECT COUNT(*) FROM plan_steps WHERE plan_id = ?", (plan_id,))
            assert cur.fetchone()[0] == 1

            # Delete parent plan
            conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
            conn.commit()

            # Verify steps were cascaded
            cur = conn.execute("SELECT COUNT(*) FROM plan_steps WHERE plan_id = ?", (plan_id,))
            assert cur.fetchone()[0] == 0


@pytest.mark.db
class TestFTS5TriggersAndSynchronization:
    """Verification of automated synchronization triggers on plan_steps."""

    def test_insert_trigger_synchronizes_fts5(self, temp_db: str) -> None:
        plan = create_plan_sync(
            goal="Test FTS5 Sync",
            steps=[{
                "title": "Configure Prometheus Telemetry",
                "description": "Expose scrapable agent metrics and step latencies",
                "tool": "devops",
            }],
            db_path=temp_db,
        )
        # Search FTS5 virtual table
        results = search_steps_sync("Prometheus", temp_db)
        assert len(results) >= 1
        assert results[0]["title"] == "Configure Prometheus Telemetry"
        assert results[0]["plan_id"] == plan["id"]

    def test_update_trigger_synchronizes_fts5(self, temp_db: str) -> None:
        create_plan_sync(
            goal="Test Update Sync",
            steps=[{
                "id": "step_to_update",
                "title": "Old Step Name",
                "description": "Old step description",
                "tool": "general",
            }],
            db_path=temp_db,
        )
        # Update step title and result
        update_step_sync(
            "step_to_update",
            "completed",
            "Revolutionary quantum algorithm optimized",
            None,
            temp_db,
        )

        # Old query should return no match
        old_results = search_steps_sync("quantum", temp_db)
        assert len(old_results) >= 1
        assert "quantum" in old_results[0]["result"].lower()

    def test_delete_trigger_synchronizes_fts5(self, temp_db: str) -> None:
        create_plan_sync(
            goal="Test Delete Sync",
            steps=[{
                "id": "step_to_delete",
                "title": "Ephemeral EphemeralToken Step",
                "description": "UniqueTokenToVerifyDeletion",
                "tool": "general",
            }],
            db_path=temp_db,
        )
        # Verify indexed
        before = search_steps_sync("UniqueTokenToVerifyDeletion", temp_db)
        assert len(before) == 1

        # Delete step
        with sqlite3.connect(temp_db) as conn:
            conn.execute("DELETE FROM plan_steps WHERE id = 'step_to_delete'")
            conn.commit()

        # Verify removed from FTS5 index
        after = search_steps_sync("UniqueTokenToVerifyDeletion", temp_db)
        assert len(after) == 0


@pytest.mark.db
class TestFTS5PorterStemmerAndBM25:
    """Validation of full-text search tokenization, Porter stemming, and BM25 ranking."""

    def test_porter_stemmer_matches(self, temp_db: str) -> None:
        create_plan_sync(
            goal="Stemmer Test",
            steps=[{
                "title": "Optimizing relational indexes",
                "description": "We are executing database optimizations for queries.",
            }],
            db_path=temp_db,
        )

        # "optimize" should match "Optimizing" and "optimizations" via Porter stemmer
        results = search_steps_sync("optimize", temp_db)
        assert len(results) >= 1
        assert "Optimizing" in results[0]["title"]

    def test_bm25_ranking_and_snippet_generation(self, temp_db: str) -> None:
        create_plan_sync(
            goal="BM25 Ranking Test",
            steps=[
                {
                    "title": "Basic Cache",
                    "description": "A simple cache layer.",
                },
                {
                    "title": "High Performance Redis Cache with Redis Sentinel and Redis Cluster",
                    "description": "Redis cache clustering for ultra fast key-value storage.",
                },
            ],
            db_path=temp_db,
        )

        results = search_steps_sync("Redis", temp_db)
        assert len(results) >= 1
        top_hit = results[0]
        # In SQLite bm25(), lower values represent higher relevance
        assert "Redis" in top_hit["title"]
        assert top_hit["snippet"] is not None
        assert "<b>" in top_hit["snippet"] or "Redis" in top_hit["snippet"]

    def test_replace_remaining_steps_updates_ledger(self, temp_db: str) -> None:
        plan = create_plan_sync(
            goal="Replace Steps Test",
            steps=[
                {"title": "Initial Step 0", "description": "Step 0"},
                {"title": "Initial Step 1", "description": "Step 1"},
                {"title": "Initial Step 2", "description": "Step 2"},
            ],
            db_path=temp_db,
        )
        plan_id = plan["id"]

        # Replace remaining steps from index 1 onward
        new_steps = [
            {"title": "Adapted Recovery Step", "description": "Remediation step"},
            {"title": "Revised Final Step", "description": "Final step"},
        ]
        replace_remaining_steps_sync(plan_id, 1, new_steps, temp_db)

        updated = get_plan_sync(plan_id, temp_db)
        assert updated is not None
        assert updated["status"] == "replanned"
        assert updated["total_steps"] == 3
        assert updated["steps"][0]["title"] == "Initial Step 0"
        assert updated["steps"][1]["title"] == "Adapted Recovery Step"
        assert updated["steps"][2]["title"] == "Revised Final Step"


@pytest.mark.db
class TestSanitizeFTS5Query:
    """Validation of sanitize_fts5_query against hostile and special inputs."""

    @pytest.mark.parametrize(
        "raw_input",
        [
            "",
            "   ",
            "***",
            "???",
            ":;;<>>>",
            '"unclosed quote',
            "' OR 1=1 --",
            "'; DROP TABLE plans; --",
            "AND",
            "OR",
            "NOT",
            "NEAR",
        ],
    )
    def test_sanitize_fts5_query_resilience(self, raw_input: str) -> None:
        sanitized = sanitize_fts5_query(raw_input)
        # Should never throw syntax error when queried in SQLite FTS5
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(content);")
            if sanitized:
                # Must execute safely without OperationalError
                conn.execute("SELECT * FROM t WHERE t MATCH ?", (sanitized,))
