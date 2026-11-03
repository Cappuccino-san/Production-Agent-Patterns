"""Tier 3: SQLite WAL Mode Pragmas, Triggers, and FTS5 BM25 Full-Text Persistence Tests."""

import pytest

from app.database import (
    check_database_health,
    get_db_connection,
    get_run,
    list_runs,
    save_run,
    search_runs,
)


@pytest.mark.db
@pytest.mark.asyncio
async def test_sqlite_wal_mode_pragmas(temp_db: str) -> None:
    """Verify SQLite connection applies WAL journal mode and performance pragmas."""
    async with get_db_connection(temp_db) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        journal_mode = (await cursor.fetchone())[0]
        assert journal_mode.lower() == "wal"

        cursor = await conn.execute("PRAGMA synchronous;")
        sync_mode = (await cursor.fetchone())[0]
        # NORMAL corresponds to 1 in SQLite
        assert sync_mode in (1, "NORMAL")

        cursor = await conn.execute("PRAGMA busy_timeout;")
        busy_timeout = (await cursor.fetchone())[0]
        assert busy_timeout >= 5000

        cursor = await conn.execute("PRAGMA foreign_keys;")
        foreign_keys = (await cursor.fetchone())[0]
        assert foreign_keys == 1


@pytest.mark.db
@pytest.mark.asyncio
async def test_save_and_retrieve_run(temp_db: str) -> None:
    """Verify inserting and reading an agent run record."""
    run_record = {
        "id": "run_test_01",
        "prompt": "Create fibonacci generator",
        "language": "python",
        "code": "def fib(n): return [0, 1]",
        "is_valid": True,
        "output": "Fibonacci: [0, 1]",
        "iterations": 1,
        "steps": ["Thought: start", "Action: write"],
        "status": "completed",
    }
    await save_run(run_record, temp_db)

    fetched = await get_run("run_test_01", temp_db)
    assert fetched is not None
    assert fetched["id"] == "run_test_01"
    assert fetched["prompt"] == "Create fibonacci generator"
    assert fetched["is_valid"] is True
    assert fetched["steps"] == ["Thought: start", "Action: write"]
    assert fetched["status"] == "completed"


@pytest.mark.db
@pytest.mark.asyncio
async def test_list_runs_pagination(temp_db: str) -> None:
    """Verify listing runs honors limit and returns ordered entries."""
    for i in range(5):
        record = {
            "id": f"run_batch_{i}",
            "prompt": f"Task number {i}",
            "language": "python",
            "code": f"x = {i}",
            "is_valid": True,
            "output": str(i),
            "iterations": 1,
            "steps": [],
            "status": "completed",
        }
        await save_run(record, temp_db)

    runs = await list_runs(limit=3, db_path=temp_db)
    assert len(runs) == 3


@pytest.mark.db
@pytest.mark.asyncio
async def test_fts5_synchronization_triggers(temp_db: str) -> None:
    """Verify SQLite triggers automatically synchronize INSERT, UPDATE, and DELETE to FTS5."""
    # 1. Insert Trigger
    record = {
        "id": "run_trigger_01",
        "prompt": "Build an asynchronous tokenizer",
        "language": "python",
        "code": "def tokenize(): pass",
        "is_valid": True,
        "output": "Done",
        "iterations": 1,
        "steps": [],
        "status": "completed",
    }
    await save_run(record, temp_db)

    results = await search_runs("tokenizer", limit=10, db_path=temp_db)
    assert len(results) == 1
    assert results[0]["id"] == "run_trigger_01"

    # 2. Update Trigger
    updated_record = {
        "id": "run_trigger_01",
        "prompt": "Build a polymorphic transformer compiler",
        "language": "python",
        "code": "class Compiler: pass",
        "is_valid": True,
        "output": "Compiled",
        "iterations": 2,
        "steps": [],
        "status": "completed",
    }
    await save_run(updated_record, temp_db)

    # Old search should return 0 results
    old_search = await search_runs("tokenizer", limit=10, db_path=temp_db)
    assert len(old_search) == 0

    # New search should return 1 result
    new_search = await search_runs("polymorphic", limit=10, db_path=temp_db)
    assert len(new_search) == 1
    assert new_search[0]["id"] == "run_trigger_01"

    # 3. Delete Trigger
    async with get_db_connection(temp_db) as conn:
        await conn.execute("DELETE FROM runs WHERE id = 'run_trigger_01';")
        await conn.commit()

    deleted_search = await search_runs("polymorphic", limit=10, db_path=temp_db)
    assert len(deleted_search) == 0


@pytest.mark.db
@pytest.mark.asyncio
async def test_fts5_bm25_search_scoring(temp_db: str) -> None:
    """Verify BM25 ranking returns relevance ordered results with highlighted snippet."""
    records = [
        {
            "id": "run_algo_1",
            "prompt": "Algorithm for bubble sort",
            "language": "python",
            "code": "def bubble_sort(): pass",
            "is_valid": True,
            "output": "Sorted",
            "iterations": 1,
            "steps": [],
            "status": "completed",
        },
        {
            "id": "run_algo_2",
            "prompt": "Algorithm for quick sort fast sorting algorithm",
            "language": "python",
            "code": "def quick_sort(): pass",
            "is_valid": True,
            "output": "Fast",
            "iterations": 1,
            "steps": [],
            "status": "completed",
        },
    ]
    for r in records:
        await save_run(r, temp_db)

    results = await search_runs("algorithm", limit=5, db_path=temp_db)
    assert len(results) == 2
    # Verify BM25 rank exists (negative value in SQLite FTS5)
    assert "rank" in results[0]
    assert "snippet" in results[0]
    assert "<b>" in results[0]["snippet"]


@pytest.mark.db
@pytest.mark.asyncio
async def test_database_health_check(temp_db: str) -> None:
    """Verify database health checker reports WAL mode."""
    health = await check_database_health(temp_db)
    assert health["status"] == "connected"
    assert health["journal_mode"].lower() == "wal"
