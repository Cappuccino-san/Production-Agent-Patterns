"""Tier 3: SQLite WAL mode, foreign keys, triggers, and FTS5 BM25 persistence tests."""

import sqlite3
import pytest

from app.database import (
    add_reflection,
    add_reflection_sync,
    check_database_health,
    create_session,
    create_session_sync,
    get_session,
    get_session_sync,
    list_sessions,
    sanitize_fts5_query,
    search_reflections,
    search_reflections_sync,
    update_session_status,
)


class TestSQLiteWALAndPragmas:
    """Verifies SQLite WAL configuration and engine pragmas."""

    def test_wal_journal_mode(self, temp_db: str) -> None:
        with sqlite3.connect(temp_db) as conn:
            cur = conn.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0]
            assert mode.lower() == "wal"

    def test_synchronous_and_foreign_keys(self, temp_db: str) -> None:
        with sqlite3.connect(temp_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert fk == 1

            sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
            assert sync in (1, 2)  # NORMAL (1) or FULL (2)

    @pytest.mark.asyncio
    async def test_database_health_check(self, temp_db: str) -> None:
        health = await check_database_health(temp_db)
        assert health["status"] == "connected"
        assert health["journal_mode"].lower() == "wal"
        assert "sessions_count" in health
        assert "reflections_count" in health


class TestForeignKeyCascades:
    """Verifies relational integrity and cascade deletion."""

    def test_session_cascade_delete(self, temp_db: str) -> None:
        # Create session and two reflections
        sid = "sess_cascade_test"
        create_session_sync("Cascade goal", 85.0, None, sid, temp_db)
        add_reflection_sync(sid, 1, "draft 1", "critique 1", {"correctness": 60.0}, 60.0, db_path=temp_db)
        add_reflection_sync(sid, 2, "draft 2", "critique 2", {"correctness": 88.0}, 88.0, db_path=temp_db)

        # Confirm 2 reflections exist
        sess = get_session_sync(sid, temp_db)
        assert sess is not None
        assert len(sess["iterations"]) == 2

        # Delete session
        with sqlite3.connect(temp_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.commit()

        # Session should not exist
        assert get_session_sync(sid, temp_db) is None

        # Child reflections must be automatically deleted by cascade
        with sqlite3.connect(temp_db) as conn:
            cur = conn.execute("SELECT count(*) FROM reflections WHERE session_id = ?", (sid,))
            assert cur.fetchone()[0] == 0


class TestFTS5TriggersAndBM25Search:
    """Verifies FTS5 virtual table sync via triggers and BM25 search."""

    def test_fts5_insert_trigger_and_bm25_search(self, temp_db: str) -> None:
        sid = "sess_fts_test"
        create_session_sync("Searchable task", 85.0, None, sid, temp_db)

        # Insert reflection with distinct keywords
        add_reflection_sync(
            session_id=sid,
            iteration=1,
            draft="def quicksort(arr): return arr",
            critique="Critique: Missing recursive partition logic for quicksort algorithm.",
            rubric_scores={"correctness": 55.0},
            composite_score=55.0,
            db_path=temp_db,
        )

        # FTS5 search for 'quicksort'
        results = search_reflections_sync("quicksort", temp_db)
        assert len(results) >= 1
        top_match = results[0]
        assert "quicksort" in top_match["draft"] or "quicksort" in top_match["critique"]
        assert "score" in top_match
        assert "snippet" in top_match

    def test_fts5_update_trigger(self, temp_db: str) -> None:
        sid = "sess_fts_update"
        create_session_sync("Update task", 85.0, None, sid, temp_db)

        refl = add_reflection_sync(
            session_id=sid,
            iteration=1,
            draft="Initial draft text",
            critique="Initial critique",
            rubric_scores={"correctness": 50.0},
            composite_score=50.0,
            db_path=temp_db,
        )

        # Update draft in reflections
        with sqlite3.connect(temp_db) as conn:
            conn.execute(
                "UPDATE reflections SET draft = 'Updated kaleidoscopic algorithm' WHERE id = ?",
                (refl["id"],),
            )
            conn.commit()

        # FTS5 should match new content
        results = search_reflections_sync("kaleidoscopic", temp_db)
        assert len(results) >= 1
        assert "kaleidoscopic" in results[0]["draft"]

    def test_fts5_delete_trigger(self, temp_db: str) -> None:
        sid = "sess_fts_del"
        create_session_sync("Delete task", 85.0, None, sid, temp_db)

        refl = add_reflection_sync(
            session_id=sid,
            iteration=1,
            draft="UniqueZephyrIdentifier",
            critique="Critique",
            rubric_scores={"correctness": 50.0},
            composite_score=50.0,
            db_path=temp_db,
        )

        # Ensure indexed
        assert len(search_reflections_sync("UniqueZephyrIdentifier", temp_db)) == 1

        # Delete reflection
        with sqlite3.connect(temp_db) as conn:
            conn.execute("DELETE FROM reflections WHERE id = ?", (refl["id"],))
            conn.commit()

        # Ensure removed from FTS5 index
        assert len(search_reflections_sync("UniqueZephyrIdentifier", temp_db)) == 0


class TestFTS5SanitizationAndAsyncPersistence:
    """Verifies query sanitizer resilience and asynchronous persistence methods."""

    def test_sanitize_fts5_query_resilience(self) -> None:
        # Handles special characters and operators safely
        assert sanitize_fts5_query("hello AND world OR (NOT test)") != ""
        assert sanitize_fts5_query("'''\"\"\"-- SELECT * FROM") != ""
        assert sanitize_fts5_query("") == ""
        assert sanitize_fts5_query("   ") == ""

    @pytest.mark.asyncio
    async def test_async_database_lifecycle(self, temp_db: str) -> None:
        sid = "sess_async_01"
        created = await create_session(
            task="Async task evaluation",
            threshold=80.0,
            session_id=sid,
            db_path=temp_db,
        )
        assert created["id"] == sid
        assert created["threshold"] == 80.0

        await add_reflection(
            session_id=sid,
            iteration=1,
            draft="async def handle(): pass",
            critique="Async critique",
            rubric_scores={"clarity": 85.0},
            composite_score=85.0,
            status="completed",
            db_path=temp_db,
        )

        await update_session_status(sid, "completed", 85.0, temp_db)

        fetched = await get_session(sid, temp_db)
        assert fetched is not None
        assert fetched["status"] == "completed"
        assert fetched["final_score"] == 85.0
        assert len(fetched["iterations"]) == 1

        recent = await list_sessions(10, temp_db)
        assert any(s["id"] == sid for s in recent)

        search_res = await search_reflections("async", temp_db)
        assert len(search_res) >= 1
