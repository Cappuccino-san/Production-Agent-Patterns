"""Empirical adversarial challenge suite mirroring the Forensic Auditor harness."""

import asyncio
import pytest

from app.database import (
    delete_document,
    list_documents,
    save_document,
    search_documents,
)


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
        "'; DROP TABLE documents; --",
        ":::;;;<<<>>>",
        "caf\u00e9",
        "\U0001f680",
        "a" * 500,
        "   ",
        "",
        "***",
        "wal AND triggers",
        "nonexistent_term_12345",
    ],
)
@pytest.mark.asyncio
async def test_fts5_hostile_and_special_character_resilience(temp_db: str, query: str) -> None:
    """Empirically challenge FTS5 search with boolean operators, wildcards, and SQL injection."""
    await save_document(
        {
            "id": "doc_fts_seed",
            "title": "Adversarial Seed Document with café 🚀",
            "content": "This is a document about SQLite WAL mode and FTS5 triggers.",
            "metadata": {"test": "empirical"},
        },
        temp_db,
    )

    results = await search_documents(query=query, limit=10, db_path=temp_db)
    assert isinstance(results, list)
    for hit in results:
        assert "id" in hit
        assert "title" in hit
        assert "snippet" in hit
        assert "score" in hit


@pytest.mark.asyncio
async def test_empirical_concurrency_stress(temp_db: str) -> None:
    """Challenge SQLite busy timeouts under high write pressure."""
    async def fast_writer(batch_id: int) -> None:
        for i in range(15):
            await save_document(
                {
                    "id": f"stress_{batch_id}_{i}",
                    "title": f"Stress {batch_id}-{i}",
                    "content": f"High frequency write payload {i} for batch {batch_id}.",
                },
                temp_db,
            )

    async def fast_searcher() -> None:
        for _ in range(20):
            res = await search_documents("payload", limit=5, db_path=temp_db)
            assert isinstance(res, list)

    tasks = [fast_writer(1), fast_writer(2), fast_writer(3), fast_searcher(), fast_searcher()]
    await asyncio.gather(*tasks)

    # Verify all records saved intact
    all_docs = await list_documents(limit=100, db_path=temp_db)
    assert len(all_docs) == 45


@pytest.mark.asyncio
async def test_empirical_trigger_consistency(temp_db: str) -> None:
    """Empirically verify FTS5 table exact sync across repeated updates and deletes."""
    doc_id = "doc_sync_lifecycle"

    # 1. Insert
    await save_document({"id": doc_id, "title": "Version 1", "content": "Pineapple apple"}, temp_db)
    hits = await search_documents("Pineapple", db_path=temp_db)
    assert len(hits) == 1

    # 2. Update to Banana
    await save_document({"id": doc_id, "title": "Version 2", "content": "Banana orange"}, temp_db)
    hits_old = await search_documents("Pineapple", db_path=temp_db)
    assert len(hits_old) == 0
    hits_new = await search_documents("Banana", db_path=temp_db)
    assert len(hits_new) == 1

    # 3. Delete
    await delete_document(doc_id, temp_db)
    hits_del = await search_documents("Banana", db_path=temp_db)
    assert len(hits_del) == 0
