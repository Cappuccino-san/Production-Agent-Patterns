"""SQLite WAL mode database engine with FTS5 triggers and BM25 search."""

import json
import os
import re
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional

import aiosqlite

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    language TEXT NOT NULL,
    code TEXT NOT NULL,
    is_valid INTEGER NOT NULL,
    output TEXT,
    iterations INTEGER NOT NULL,
    steps TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(
    prompt,
    code,
    output,
    content='runs',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_runs_ai AFTER INSERT ON runs
BEGIN
    INSERT INTO runs_fts(rowid, prompt, code, output)
    VALUES (new.rowid, new.prompt, new.code, coalesce(new.output, ''));
END;

CREATE TRIGGER IF NOT EXISTS trg_runs_ad AFTER DELETE ON runs
BEGIN
    INSERT INTO runs_fts(runs_fts, rowid, prompt, code, output)
    VALUES('delete', old.rowid, old.prompt, old.code, coalesce(old.output, ''));
END;

CREATE TRIGGER IF NOT EXISTS trg_runs_au AFTER UPDATE ON runs
BEGIN
    INSERT INTO runs_fts(runs_fts, rowid, prompt, code, output)
    VALUES('delete', old.rowid, old.prompt, old.code, coalesce(old.output, ''));
    INSERT INTO runs_fts(rowid, prompt, code, output)
    VALUES (new.rowid, new.prompt, new.code, coalesce(new.output, ''));
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


async def save_run(run_data: dict[str, Any], db_path: str) -> None:
    """Insert or replace an agent run record in the database."""
    query = """
    INSERT INTO runs (id, prompt, language, code, is_valid, output, iterations, steps, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        prompt = excluded.prompt,
        language = excluded.language,
        code = excluded.code,
        is_valid = excluded.is_valid,
        output = excluded.output,
        iterations = excluded.iterations,
        steps = excluded.steps,
        status = excluded.status;
    """
    steps_json = (
        json.dumps(run_data.get("steps", []))
        if isinstance(run_data.get("steps"), list)
        else str(run_data.get("steps", "[]"))
    )

    async with get_db_connection(db_path) as conn:
        await conn.execute(
            query,
            (
                run_data["id"],
                run_data["prompt"],
                run_data.get("language", "python"),
                run_data["code"],
                1 if run_data.get("is_valid") else 0,
                run_data.get("output"),
                run_data.get("iterations", 1),
                steps_json,
                run_data.get("status", "completed"),
            ),
        )
        await conn.commit()


async def get_run(run_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Retrieve a single agent run by its unique identifier."""
    query = """
    SELECT id, prompt, language, code, is_valid, output, iterations, steps, status, created_at
    FROM runs
    WHERE id = ?;
    """
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute(query, (run_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["is_valid"] = bool(res["is_valid"])
        try:
            res["steps"] = json.loads(res["steps"])
        except Exception:
            res["steps"] = []
        return res


async def list_runs(limit: int = 50, db_path: str = "") -> list[dict[str, Any]]:
    """List recent agent runs ordered by creation timestamp descending."""
    query = """
    SELECT id, prompt, language, code, is_valid, output, iterations, steps, status, created_at
    FROM runs
    ORDER BY created_at DESC
    LIMIT ?;
    """
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute(query, (limit,))
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["is_valid"] = bool(item["is_valid"])
            try:
                item["steps"] = json.loads(item["steps"])
            except Exception:
                item["steps"] = []
            results.append(item)
        return results


async def search_runs(query: str, limit: int = 20, db_path: str = "") -> list[dict[str, Any]]:
    """Execute ranked BM25 search over FTS5 virtual table with snippet generation."""
    # Extract only word characters to guarantee FTS5 syntax safety
    tokens = [w for w in re.findall(r"\w+", query) if w]
    if not tokens:
        return []

    match_expr = " ".join(f"{t}*" for t in tokens)

    fts_sql = """
    SELECT 
        r.id,
        r.prompt,
        r.code,
        snippet(runs_fts, -1, '<b>', '</b>', '...', 16) AS snippet,
        bm25(runs_fts) AS rank
    FROM runs_fts
    JOIN runs r ON runs_fts.rowid = r.rowid
    WHERE runs_fts MATCH ?
    ORDER BY rank ASC
    LIMIT ?;
    """
    try:
        async with get_db_connection(db_path) as conn:
            cursor = await conn.execute(fts_sql, (match_expr, limit))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        return []


async def check_database_health(db_path: str) -> dict[str, str]:
    """Inspect database connectivity and verify WAL journal mode."""
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        row = await cursor.fetchone()
        journal_mode = row[0] if row else "unknown"
        return {"journal_mode": journal_mode, "status": "connected"}
