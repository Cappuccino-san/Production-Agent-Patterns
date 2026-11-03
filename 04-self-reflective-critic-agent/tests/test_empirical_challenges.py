"""Tier 6: Empirical adversarial stress tests for SQLite WAL and FTS5 trigger synchronization."""

import concurrent.futures
import sqlite3
import time
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import create_reflection_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import AgentState
from app.config import get_settings
from app.database import (
    add_reflection_sync,
    create_session_sync,
    get_session_sync,
    init_db_sync,
    search_reflections_sync,
)
from app.main import app


class TestFTS5TriggersAndIntegrity:
    """Empirical verification of FTS5 triggers: ai, au, ad, and virtual table integrity."""

    def test_fts5_triggers_insert_update_delete_integrity(self, temp_db: str) -> None:
        """Verify trg_reflections_ai, trg_reflections_au, trg_reflections_ad, and integrity-check."""
        sid = "sess_trigger_empirical"
        create_session_sync("Empirical trigger test task", 85.0, None, sid, temp_db)

        # 1. Test trg_reflections_ai (Insert Trigger)
        refl = add_reflection_sync(
            session_id=sid,
            iteration=1,
            draft="Draft with AlphaQuantumKeyword logic",
            critique="Critique highlighting BetaQuantumCritique issues",
            rubric_scores={"correctness": 60.0},
            composite_score=60.0,
            db_path=temp_db,
        )

        match_draft = search_reflections_sync("AlphaQuantumKeyword", temp_db)
        match_critique = search_reflections_sync("BetaQuantumCritique", temp_db)
        assert len(match_draft) == 1, "trg_reflections_ai failed to index draft in reflections_fts"
        assert len(match_critique) == 1, "trg_reflections_ai failed to index critique in reflections_fts"

        # 2. Test trg_reflections_au (Update Trigger)
        with sqlite3.connect(temp_db) as conn:
            conn.execute(
                """
                UPDATE reflections
                SET draft = 'Revised draft with GammaHolographicTerm',
                    critique = 'Critique updated to DeltaHolographicCritique'
                WHERE id = ?
                """,
                (refl["id"],),
            )
            conn.commit()

        # Old tokens must be removed from reflections_fts
        assert len(search_reflections_sync("AlphaQuantumKeyword", temp_db)) == 0, (
            "trg_reflections_au failed to remove old draft tokens"
        )
        assert len(search_reflections_sync("BetaQuantumCritique", temp_db)) == 0, (
            "trg_reflections_au failed to remove old critique tokens"
        )

        # New tokens must be indexed
        assert len(search_reflections_sync("GammaHolographicTerm", temp_db)) == 1, (
            "trg_reflections_au failed to index new draft tokens"
        )
        assert len(search_reflections_sync("DeltaHolographicCritique", temp_db)) == 1, (
            "trg_reflections_au failed to index new critique tokens"
        )

        # 3. Test integrity-check on reflections_fts
        with sqlite3.connect(temp_db) as conn:
            conn.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")

        # 4. Test trg_reflections_ad (Delete Trigger)
        with sqlite3.connect(temp_db) as conn:
            conn.execute("DELETE FROM reflections WHERE id = ?", (refl["id"],))
            conn.commit()

        assert len(search_reflections_sync("GammaHolographicTerm", temp_db)) == 0, (
            "trg_reflections_ad failed to remove deleted draft from reflections_fts"
        )
        assert len(search_reflections_sync("DeltaHolographicCritique", temp_db)) == 0, (
            "trg_reflections_ad failed to remove deleted critique from reflections_fts"
        )

        # Final integrity-check
        with sqlite3.connect(temp_db) as conn:
            conn.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")

    def test_fts5_bm25_ranking_and_snippets(self, temp_db: str) -> None:
        """Verify BM25 ranking ordering and snippet extraction with highlight wrappers."""
        sid = "sess_bm25_ranking"
        create_session_sync("BM25 ranking task", 85.0, None, sid, temp_db)

        # Ingest documents with varying frequency of keyword 'dichotomy'
        add_reflection_sync(
            session_id=sid,
            iteration=1,
            draft="DocLow: dichotomy appears once in this implementation.",
            critique="Critique Low",
            rubric_scores={"correctness": 70.0},
            composite_score=70.0,
            reflection_id="refl_low",
            db_path=temp_db,
        )
        add_reflection_sync(
            session_id=sid,
            iteration=2,
            draft="DocMed: dichotomy dichotomy dichotomy appears three times.",
            critique="Critique Med",
            rubric_scores={"correctness": 80.0},
            composite_score=80.0,
            reflection_id="refl_med",
            db_path=temp_db,
        )
        add_reflection_sync(
            session_id=sid,
            iteration=3,
            draft="DocHigh: dichotomy dichotomy dichotomy dichotomy dichotomy quintuple frequency.",
            critique="Critique High",
            rubric_scores={"correctness": 90.0},
            composite_score=90.0,
            reflection_id="refl_high",
            db_path=temp_db,
        )

        results = search_reflections_sync("dichotomy", temp_db, limit=10)
        assert len(results) == 3

        # Highest frequency must have the most negative / best BM25 score (rank 1)
        assert results[0]["reflection_id"] == "refl_high"
        assert results[1]["reflection_id"] == "refl_med"
        assert results[2]["reflection_id"] == "refl_low"

        # Check snippet highlight wrappers
        assert "<b>dichotomy</b>" in results[0]["snippet"]

        # Run integrity check
        with sqlite3.connect(temp_db) as conn:
            conn.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")

    def test_foreign_key_cascade_trigger_cleanup(self, temp_db: str) -> None:
        """Verify that cascading deletion of sessions cleans reflections_fts via trg_reflections_ad."""
        sid = "sess_cascade_trigger"
        create_session_sync("Cascade trigger test", 85.0, None, sid, temp_db)

        add_reflection_sync(
            session_id=sid,
            iteration=1,
            draft="Draft with EphemeralCascadeToken",
            critique="Critique with EphemeralCascadeToken",
            rubric_scores={"correctness": 75.0},
            composite_score=75.0,
            db_path=temp_db,
        )

        assert len(search_reflections_sync("EphemeralCascadeToken", temp_db)) == 1

        # Delete session with foreign_keys enabled
        with sqlite3.connect(temp_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.commit()

        # FTS5 index should no longer contain the token
        assert len(search_reflections_sync("EphemeralCascadeToken", temp_db)) == 0

        # Integrity check
        with sqlite3.connect(temp_db) as conn:
            conn.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")


class TestSQLiteWALConcurrencyHarness:
    """Empirical multi-threaded concurrency stress tests under SQLite WAL mode."""

    def test_multithreaded_wal_concurrency_25_sessions(
        self, temp_db: str, mock_llm: DeterministicMockLLM
    ) -> None:
        """Spawns 25 concurrent worker threads executing full StateGraph loops with zero lock errors."""
        num_sessions = 25
        errors: list[tuple[str, str, str]] = []
        session_results: dict[int, dict[str, Any]] = {}

        def run_agent_session(idx: int) -> dict[str, Any]:
            sid = f"concurrency_wal_sess_{idx:03d}"
            task_desc = f"Concurrent session {idx}: implement self-balancing red-black tree operations"
            try:
                create_session_sync(task=task_desc, threshold=85.0, session_id=sid, db_path=temp_db)
                state: AgentState = {
                    "session_id": sid,
                    "task": task_desc,
                    "threshold": 85.0,
                    "max_iterations": 3,
                    "iteration": 0,
                    "current_draft": "",
                    "critique": "",
                    "defects": [],
                    "suggestions": [],
                    "rubric_scores": {},
                    "composite_score": 0.0,
                    "passed": False,
                    "status": "in_progress",
                    "history": [],
                    "db_path": temp_db,
                    "seed": 500 + idx,
                }
                graph = create_reflection_graph(mock_llm)
                return graph.invoke(state)
            except Exception as exc:
                errors.append((sid, type(exc).__name__, str(exc)))
                raise

        def run_reader_queries(reader_idx: int) -> int:
            hits = 0
            for _ in range(15):
                try:
                    res = search_reflections_sync("balancing", temp_db, limit=10)
                    hits += len(res)
                    time.sleep(0.005)
                except Exception as exc:
                    errors.append((f"reader_{reader_idx}", type(exc).__name__, str(exc)))
            return hits

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_sessions + 5) as executor:
            writer_futs = {executor.submit(run_agent_session, i): i for i in range(num_sessions)}
            reader_futs = [executor.submit(run_reader_queries, r) for r in range(5)]

            for fut in concurrent.futures.as_completed(writer_futs):
                idx = writer_futs[fut]
                session_results[idx] = fut.result()

            total_reader_hits = sum(f.result() for f in reader_futs)

        elapsed = time.time() - start

        # Assert zero exceptions occurred
        assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
        assert len(session_results) == num_sessions
        assert total_reader_hits >= 0
        assert elapsed < 15.0  # Must be fast and responsive

        # Verify database persistence integrity
        with sqlite3.connect(temp_db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM sessions")
            sess_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM reflections")
            refl_count = cur.fetchone()[0]
            cur.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")

        assert sess_count == num_sessions, f"Expected {num_sessions} sessions, got {sess_count}"
        assert refl_count == num_sessions * 3, f"Expected {num_sessions * 3} reflections, got {refl_count}"

        # Verify individual session records
        for i in range(num_sessions):
            sid = f"concurrency_wal_sess_{i:03d}"
            record = get_session_sync(sid, temp_db)
            assert record is not None
            assert record["status"] in ("completed", "max_iterations_reached")
            assert len(record["iterations"]) == 3

    def test_fastapi_concurrent_api_execution_20_sessions(self, temp_db: str) -> None:
        """Spawns 20 concurrent HTTP requests to POST /execute and 10 concurrent FTS5 searches."""
        settings = get_settings()
        original_db = settings.database_path
        settings.database_path = temp_db
        init_db_sync(temp_db)

        client = TestClient(app)
        num_sessions = 20
        errors: list[tuple[str, int, str]] = []
        api_results: list[dict[str, Any]] = []

        def execute_api_call(idx: int) -> dict[str, Any]:
            payload = {
                "task": f"Concurrent API request {idx}: implement LRU cache with doubly linked list",
                "threshold": 85.0,
                "max_iterations": 3,
                "seed": 700 + idx,
            }
            resp = client.post("/api/v1/reflections/execute", json=payload)
            if resp.status_code != 200:
                errors.append((f"writer_{idx}", resp.status_code, resp.text))
                return {}
            return resp.json()

        def search_api_call(idx: int) -> int:
            resp = client.get("/api/v1/reflections/search?q=cache")
            if resp.status_code != 200:
                errors.append((f"search_{idx}", resp.status_code, resp.text))
                return 0
            return resp.json().get("total_results", 0)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_sessions + 5) as executor:
                writer_futs = [executor.submit(execute_api_call, i) for i in range(num_sessions)]
                reader_futs = [executor.submit(search_api_call, r) for r in range(10)]

                api_results = [f.result() for f in writer_futs]
                _ = [f.result() for f in reader_futs]

            assert len(errors) == 0, f"Encountered API errors: {errors}"
            assert len(api_results) == num_sessions

            for r in api_results:
                assert r["status"] in ("completed", "max_iterations_reached")
                assert r["iterations_count"] >= 1
                assert r["final_score"] >= 80.0
                assert "session_id" in r

            # Check database contents
            with sqlite3.connect(temp_db) as conn:
                sess_count = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
                refl_count = conn.execute("SELECT count(*) FROM reflections").fetchone()[0]
                conn.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")

            assert sess_count == num_sessions
            assert refl_count >= num_sessions * 2

        finally:
            settings.database_path = original_db


@pytest.mark.parametrize(
    "query",
    [
        "sqlite",
        "SQLITE",
        "sql*",
        "AND",
        "OR",
        "NOT",
        "NEAR",
        "AND OR NOT",
        '"sqlite wal"',
        '"fts5 triggers"',
        "' OR 1=1 --",
        "'; DROP TABLE reflections; --",
        ":::;;;<<<>>>",
        "caf\u00e9",
        "a" * 200,
        "   ",
        "",
        "***???$$$^^^",
        "reflections_fts MATCH 'corrupt'",
    ],
)
def test_hostile_fts5_query_resilience(temp_db: str, query: str) -> None:
    """Verify that hostile queries, boolean operators, wildcards, and SQL injection execute safely."""
    sid = "sess_hostile_seed"
    create_session_sync("Hostile query seed task", 85.0, None, sid, temp_db)
    add_reflection_sync(
        session_id=sid,
        iteration=1,
        draft="def solve_cafe(arr): return sqlite_wal_mode(arr)",
        critique="Critique: valid solution with cafe and sqlite keywords.",
        rubric_scores={"correctness": 90.0},
        composite_score=90.0,
        db_path=temp_db,
    )

    results = search_reflections_sync(query, temp_db)
    assert isinstance(results, list)
    with sqlite3.connect(temp_db) as conn:
        conn.execute("INSERT INTO reflections_fts(reflections_fts) VALUES('integrity-check')")
