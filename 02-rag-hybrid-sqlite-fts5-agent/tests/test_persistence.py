"""Tier 3: SQLite WAL mode, FTS5 triggers, Porter stemmer, and BM25 search persistence tests."""

import sqlite3
import pytest

from app.database import (
    check_database_health,
    delete_document,
    get_db_connection,
    get_document,
    save_document,
    save_document_sync,
    save_documents_batch,
    search_documents,
    search_documents_sync,
)



@pytest.mark.db
class TestSQLiteWALPragmas:
    """Validate SQLite Write-Ahead Logging and database connection pragmas."""

    @pytest.mark.asyncio
    async def test_wal_mode_and_pragmas(self, temp_db: str) -> None:
        async with get_db_connection(temp_db) as conn:
            cursor = await conn.execute("PRAGMA journal_mode;")
            mode = (await cursor.fetchone())[0]
            assert mode.lower() == "wal"

            cursor = await conn.execute("PRAGMA synchronous;")
            sync = (await cursor.fetchone())[0]
            assert sync in (1, "1")

            cursor = await conn.execute("PRAGMA busy_timeout;")
            busy = (await cursor.fetchone())[0]
            assert busy == 5000

            cursor = await conn.execute("PRAGMA foreign_keys;")
            fk = (await cursor.fetchone())[0]
            assert fk == 1

    @pytest.mark.asyncio
    async def test_database_health_check(self, temp_db: str) -> None:
        health = await check_database_health(temp_db)
        assert health["status"] == "connected"
        assert health["journal_mode"].lower() == "wal"
        assert health["document_count"] == 0


@pytest.mark.db
class TestFTS5TriggersAndSynchronization:
    """Validate external content FTS5 triggers on INSERT, UPDATE, and DELETE."""

    @pytest.mark.asyncio
    async def test_insert_trigger_synchronizes_fts5(self, temp_db: str) -> None:
        doc = {
            "id": "doc_trigger_1",
            "title": "Trigger Testing Guide",
            "content": "Automated synchronization prevents data drift in SQLite.",
            "metadata": {"test": True},
        }
        await save_document(doc, temp_db)

        # Query FTS5 table directly
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT rowid, title FROM documents_fts WHERE documents_fts MATCH 'synchronization';"
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["title"] == "Trigger Testing Guide"

    @pytest.mark.asyncio
    async def test_update_trigger_synchronizes_fts5(self, temp_db: str) -> None:
        doc = {
            "id": "doc_update_1",
            "title": "Original Title",
            "content": "Original content with keyword Alpha.",
        }
        await save_document(doc, temp_db)

        # Confirm keyword Alpha is present
        results_before = await search_documents("Alpha", db_path=temp_db)
        assert len(results_before) == 1

        # Update document to replace Alpha with Beta
        updated_doc = {
            "id": "doc_update_1",
            "title": "Updated Title",
            "content": "Updated content with keyword Beta.",
        }
        await save_document(updated_doc, temp_db)

        # Alpha should no longer match
        results_alpha = await search_documents("Alpha", db_path=temp_db)
        assert len(results_alpha) == 0

        # Beta should match
        results_beta = await search_documents("Beta", db_path=temp_db)
        assert len(results_beta) == 1
        assert results_beta[0]["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_delete_trigger_synchronizes_fts5(self, temp_db: str) -> None:
        doc = {
            "id": "doc_del_1",
            "title": "Temporary Document",
            "content": "This document will be deleted immediately.",
        }
        await save_document(doc, temp_db)

        # Verify indexed
        results_before = await search_documents("deleted", db_path=temp_db)
        assert len(results_before) == 1

        # Delete document
        deleted = await delete_document("doc_del_1", temp_db)
        assert deleted is True

        # Verify removed from FTS5 index
        results_after = await search_documents("deleted", db_path=temp_db)
        assert len(results_after) == 0

        # Verify removed from relational table
        retrieved = await get_document("doc_del_1", temp_db)
        assert retrieved is None


@pytest.mark.db
class TestFTS5PorterStemmerAndBM25:
    """Validate Porter stemmer indexing, BM25 ranking, and snippet highlights."""

    @pytest.mark.asyncio
    async def test_porter_stemmer_matches(self, temp_db: str) -> None:
        doc = {
            "id": "doc_stemmer",
            "title": "Indexing Architectures",
            "content": "Engineers are continuously indexing data and optimizing queries.",
        }
        await save_document(doc, temp_db)

        # Search with base stem 'index' should match 'indexing'
        results = await search_documents("index", db_path=temp_db)
        assert len(results) == 1
        assert results[0]["id"] == "doc_stemmer"

        # Search with 'optimizer' should match 'optimizing'
        results_opt = await search_documents("optimize", db_path=temp_db)
        assert len(results_opt) == 1

    @pytest.mark.asyncio
    async def test_bm25_ranking_and_snippet_generation(self, temp_db: str) -> None:
        docs = [
            {
                "id": "doc_high_relevance",
                "title": "WAL Mode Concurrency",
                "content": "WAL mode is essential for high concurrency WAL operations and WAL readers.",
            },
            {
                "id": "doc_low_relevance",
                "title": "General Database Systems",
                "content": "Various storage engines exist, some of which support WAL mode.",
            },
        ]
        await save_documents_batch(docs, temp_db)

        results = await search_documents("WAL", limit=10, db_path=temp_db)
        assert len(results) == 2
        # Highest frequency match should rank first
        assert results[0]["id"] == "doc_high_relevance"
        # Check snippet formatting
        assert "<b>" in results[0]["snippet"]
        assert "</b>" in results[0]["snippet"]

    def test_search_documents_sync_helper(self, temp_db: str) -> None:
        save_document_sync(
            {"id": "doc_sync", "title": "Sync Title", "content": "Sync content for testing."},
            temp_db,
        )
        hits = search_documents_sync("Sync", db_path=temp_db)
        assert len(hits) == 1
        assert hits[0]["id"] == "doc_sync"
