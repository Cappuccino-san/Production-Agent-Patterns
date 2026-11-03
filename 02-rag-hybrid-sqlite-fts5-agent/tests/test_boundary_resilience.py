"""Tier 5: Boundary conditions, resilience, syntax edge cases, and concurrency tests."""

import asyncio
from typing import Any
import pytest

from app.agent.graph import run_rag_agent
from app.database import (
    get_db_connection,
    save_document,
    search_documents,
)


@pytest.mark.boundary
class TestFTS5BoundaryAndHostileInputs:
    """Validate SQLite FTS5 search resilience against adversarial and malformed inputs."""

    @pytest.mark.parametrize(
        "hostile_query",
        [
            "",
            "   ",
            "***",
            "???",
            ":::;;;<<<>>>",
            '"unclosed quote',
            "' OR 1=1 --",
            "'; DROP TABLE documents; --",
            "AND",
            "OR",
            "NOT",
            "NEAR",
            "AND OR NOT NEAR",
            "caf\u00e9 🚀 \u6f22\u5b57",
            "a" * 1500,
            "nonexistent_term_987654321",
        ],
    )
    @pytest.mark.asyncio
    async def test_search_hostile_input_safety(
        self, temp_db: str, sample_docs: list[dict[str, Any]], hostile_query: str
    ) -> None:
        """Ensure search_documents never crashes or raises OperationalError on hostile inputs."""
        results = await search_documents(hostile_query, db_path=temp_db)
        assert isinstance(results, list)

    def test_rag_agent_empty_whitespace_query_graceful(self, temp_db: str) -> None:
        res = run_rag_agent(
            query="   ",
            db_path=temp_db,
            top_k=3,
            max_iterations=1,
            enable_decomposition=False,
        )
        assert res["completed"] is True
        assert "could not find relevant documentation" in res["answer"].lower()

    def test_rag_agent_zero_match_fallback(
        self, temp_db: str, sample_docs: list[dict[str, Any]]
    ) -> None:
        res = run_rag_agent(
            query="Deep-sea hydro-thermal vent ecosystems on Europa",
            db_path=temp_db,
            top_k=3,
            max_iterations=2,
            enable_decomposition=True,
        )
        assert res["completed"] is True
        assert res["iterations"] >= 2
        assert len(res["citations"]) == 0
        assert "could not find relevant documentation" in res["answer"].lower()


@pytest.mark.boundary
class TestSQLiteWALConcurrency:
    """Validate that WAL mode safely handles concurrent readers and writers."""

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self, temp_db: str) -> None:
        """Execute concurrent asynchronous inserts and searches without busy locking."""
        async def writer(worker_id: int) -> None:
            for i in range(10):
                doc = {
                    "id": f"worker_{worker_id}_doc_{i}",
                    "title": f"Worker {worker_id} Document {i}",
                    "content": f"Concurrency test payload for worker {worker_id} iteration {i}.",
                }
                await save_document(doc, temp_db)
                await asyncio.sleep(0.005)

        async def reader() -> None:
            for _ in range(15):
                results = await search_documents("Concurrency", limit=5, db_path=temp_db)
                assert isinstance(results, list)
                await asyncio.sleep(0.005)

        # Run 4 writers and 2 readers concurrently
        tasks = [
            writer(1),
            writer(2),
            writer(3),
            writer(4),
            reader(),
            reader(),
        ]
        await asyncio.gather(*tasks)

        # Confirm all 40 documents were saved
        async with get_db_connection(temp_db) as conn:
            cursor = await conn.execute(
                "SELECT count(*) FROM documents WHERE id LIKE 'worker_%';"
            )
            count = (await cursor.fetchone())[0]
            assert count == 40
