"""Tests for SQLite WAL mode, FTS5 sync triggers, and persistence."""

import sqlite3
import pytest
from app.database import (
    get_benchmarks_sync,
    get_db_connection,
    get_teardown_by_slug_sync,
    get_teardowns_sync,
    search_teardowns_fts_sync,
)


def test_sqlite_wal_pragmas(temp_db_path):
    conn = get_db_connection(temp_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal"

        cursor.execute("PRAGMA foreign_keys;")
        foreign_keys = cursor.fetchone()[0]
        assert foreign_keys == 1
    finally:
        conn.close()


def test_seeded_deep_dives_and_benchmarks(temp_db_path):
    teardowns = get_teardowns_sync(temp_db_path)
    assert len(teardowns) == 3

    benchmarks = get_benchmarks_sync(temp_db_path)
    assert len(benchmarks) == 15
    assert benchmarks[0].repository_id == "01"
    assert benchmarks[-1].repository_id == "15"


def test_get_teardown_by_slug(temp_db_path):
    article = get_teardown_by_slug_sync(temp_db_path, "swarm-topology-state-machine-design")
    assert article is not None
    assert article.category == "Architecture & Orchestration"
    assert len(article.key_findings) >= 3


def test_fts5_search_sync(temp_db_path):
    hits = search_teardowns_fts_sync(temp_db_path, "sanitization")
    assert len(hits) >= 1
    assert any("Deep Dive 2" in h.title for h in hits)
