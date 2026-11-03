"""SQLite WAL mode database engine with FTS5 triggers and BM25 search."""

import json
import os
import re
import sqlite3
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    content,
    content='documents',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_documents_ai AFTER INSERT ON documents
BEGIN
    INSERT INTO documents_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_ad AFTER DELETE ON documents
BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
    VALUES('delete', old.rowid, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_au AFTER UPDATE ON documents
BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
    VALUES('delete', old.rowid, old.title, old.content);
    INSERT INTO documents_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;
"""


def init_db_sync(db_path: str) -> None:
    """Synchronously initialize SQLite database schemas, pragmas, and FTS5 triggers."""
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


async def init_db(db_path: str) -> None:
    """Asynchronously initialize SQLite database schemas, pragmas, and FTS5 triggers."""
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


@asynccontextmanager
async def get_db_connection(db_path: str) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an aiosqlite connection with WAL mode and row factory configured."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA synchronous = NORMAL;")
        await conn.execute("PRAGMA busy_timeout = 5000;")
        await conn.execute("PRAGMA foreign_keys = ON;")
        yield conn


def sanitize_fts5_query(query: str) -> str:
    """Sanitize and format query string for safe FTS5 execution.
    
    Extracts alphanumeric tokens and wraps them in prefix match syntax,
    neutralizing SQL injection and FTS5 operator syntax errors. Filters
    conversational stop words and joins with OR to allow BM25 to rank
    the most salient matching documents highest.
    """
    if not query:
        return ""
    # Extract words/tokens including hyphenated terms
    tokens = [t for t in re.findall(r"[A-Za-z0-9_\u0080-\uffff]+", query) if t]
    if not tokens:
        return ""
    stop_words = {
        "how", "what", "why", "when", "where", "does", "do", "is", "are",
        "the", "a", "an", "in", "to", "of", "for", "with", "can", "you",
        "tell", "me", "about"
    }
    filtered = [t for t in tokens if t.lower() not in stop_words]
    effective_tokens = filtered if filtered else tokens
    parts = []
    for t in effective_tokens:
        if len(t) >= 4 and not t.endswith("*"):
            parts.append(f'"{t}"*')
        else:
            parts.append(f'"{t}"')
    return " OR ".join(parts)




async def save_document(doc_data: dict[str, Any], db_path: str) -> dict[str, Any]:
    """Insert or replace a document in the database."""
    doc_id = doc_data.get("id") or f"doc_{uuid.uuid4().hex[:12]}"
    title = doc_data.get("title", "").strip()
    content = doc_data.get("content", "").strip()
    raw_metadata = doc_data.get("metadata", {})
    metadata_json = (
        json.dumps(raw_metadata)
        if isinstance(raw_metadata, dict)
        else str(raw_metadata or "{}")
    )
    now = datetime.now(timezone.utc).isoformat()

    query = """
    INSERT INTO documents (id, title, content, metadata, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        content = excluded.content,
        metadata = excluded.metadata,
        updated_at = excluded.updated_at;
    """

    async with get_db_connection(db_path) as conn:
        await conn.execute(
            query,
            (doc_id, title, content, metadata_json, now, now),
        )
        await conn.commit()

    return await get_document(doc_id, db_path) or {
        "id": doc_id,
        "title": title,
        "content": content,
        "metadata": raw_metadata if isinstance(raw_metadata, dict) else {},
        "created_at": now,
        "updated_at": now,
    }


async def save_documents_batch(
    docs: list[dict[str, Any]], db_path: str
) -> list[dict[str, Any]]:
    """Insert or update a batch of documents within a single transaction."""
    results = []
    for doc in docs:
        saved = await save_document(doc, db_path)
        results.append(saved)
    return results


async def get_document(doc_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Retrieve a single document by its ID."""
    query = """
    SELECT id, title, content, metadata, created_at, updated_at
    FROM documents
    WHERE id = ?;
    """
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute(query, (doc_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        try:
            res["metadata"] = json.loads(res["metadata"])
        except Exception:
            res["metadata"] = {}
        return res


async def list_documents(
    limit: int = 50, offset: int = 0, db_path: str = ""
) -> list[dict[str, Any]]:
    """List documents ordered by creation time descending."""
    query = """
    SELECT id, title, content, metadata, created_at, updated_at
    FROM documents
    ORDER BY created_at DESC
    LIMIT ? OFFSET ?;
    """
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute(query, (limit, offset))
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item["metadata"])
            except Exception:
                item["metadata"] = {}
            results.append(item)
        return results


async def delete_document(doc_id: str, db_path: str) -> bool:
    """Delete a document by its ID, triggering automated FTS5 index deletion."""
    query = "DELETE FROM documents WHERE id = ?;"
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute(query, (doc_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def search_documents(
    query: str, limit: int = 10, threshold: float = 0.0, db_path: str = ""
) -> list[dict[str, Any]]:
    """Execute ranked BM25 search over FTS5 virtual table with snippet generation.
    
    Returns matching chunks ordered by BM25 rank score.
    """
    clean_expr = sanitize_fts5_query(query)
    if not clean_expr:
        return []

    fts_sql = """
    SELECT 
        d.id,
        d.title,
        d.content,
        d.metadata,
        snippet(documents_fts, -1, '<b>', '</b>', '...', 16) AS snippet,
        bm25(documents_fts) AS rank
    FROM documents_fts
    JOIN documents d ON documents_fts.rowid = d.rowid
    WHERE documents_fts MATCH ?
    ORDER BY rank ASC
    LIMIT ?;
    """
    try:
        async with get_db_connection(db_path) as conn:
            cursor = await conn.execute(fts_sql, (clean_expr, limit))
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except Exception:
                    item["metadata"] = {}
                # Calculate normalized score (in SQLite bm25, lower/more negative is better match)
                rank_score = float(item["rank"])
                item["score"] = rank_score
                # Ensure snippet fallback if snippet is empty
                if not item.get("snippet"):
                    content_str = item.get("content", "")
                    item["snippet"] = (
                        content_str[:160] + "..."
                        if len(content_str) > 160
                        else content_str
                    )
                results.append(item)
            return results
    except sqlite3.OperationalError:
        return []


async def check_database_health(db_path: str) -> dict[str, Any]:
    """Inspect database connectivity, pragma settings, and count documents."""
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        journal_row = await cursor.fetchone()
        journal_mode = journal_row[0] if journal_row else "unknown"

        cursor = await conn.execute("SELECT count(*) FROM documents;")
        count_row = await cursor.fetchone()
        doc_count = count_row[0] if count_row else 0

        return {
            "journal_mode": journal_mode,
            "status": "connected",
            "database": db_path,
            "document_count": doc_count,
        }


def search_documents_sync(
    query: str, limit: int = 10, threshold: float = 0.0, db_path: str = ""
) -> list[dict[str, Any]]:
    """Synchronous ranked BM25 search over FTS5 virtual table."""
    clean_expr = sanitize_fts5_query(query)
    if not clean_expr:
        return []

    fts_sql = """
    SELECT 
        d.id,
        d.title,
        d.content,
        d.metadata,
        snippet(documents_fts, -1, '<b>', '</b>', '...', 16) AS snippet,
        bm25(documents_fts) AS rank
    FROM documents_fts
    JOIN documents d ON documents_fts.rowid = d.rowid
    WHERE documents_fts MATCH ?
    ORDER BY rank ASC
    LIMIT ?;
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(fts_sql, (clean_expr, limit))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except Exception:
                    item["metadata"] = {}
                item["score"] = float(item["rank"])
                if not item.get("snippet"):
                    content_str = item.get("content", "")
                    item["snippet"] = (
                        content_str[:160] + "..."
                        if len(content_str) > 160
                        else content_str
                    )
                results.append(item)
            return results
    except sqlite3.OperationalError:
        return []


def save_document_sync(doc_data: dict[str, Any], db_path: str) -> dict[str, Any]:
    """Synchronous document insertion/update for tests and fixtures."""
    doc_id = doc_data.get("id") or f"doc_{uuid.uuid4().hex[:12]}"
    title = doc_data.get("title", "").strip()
    content = doc_data.get("content", "").strip()
    raw_metadata = doc_data.get("metadata", {})
    metadata_json = (
        json.dumps(raw_metadata)
        if isinstance(raw_metadata, dict)
        else str(raw_metadata or "{}")
    )
    now = datetime.now(timezone.utc).isoformat()

    query = """
    INSERT INTO documents (id, title, content, metadata, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        content = excluded.content,
        metadata = excluded.metadata,
        updated_at = excluded.updated_at;
    """

    with sqlite3.connect(db_path) as conn:
        conn.execute(query, (doc_id, title, content, metadata_json, now, now))
        conn.commit()

    return {
        "id": doc_id,
        "title": title,
        "content": content,
        "metadata": raw_metadata if isinstance(raw_metadata, dict) else {},
        "created_at": now,
        "updated_at": now,
    }

