"""SQLite WAL database engine with FTS5 virtual tables, sync triggers, and BM25 search."""

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

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    rubric TEXT,
    threshold REAL NOT NULL DEFAULT 85.0,
    status TEXT NOT NULL DEFAULT 'in_progress',
    final_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reflections (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    draft TEXT NOT NULL,
    critique TEXT NOT NULL,
    rubric_scores TEXT NOT NULL,
    composite_score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS reflections_fts USING fts5(
    draft,
    critique,
    rubric_scores,
    content='reflections',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_reflections_ai AFTER INSERT ON reflections
BEGIN
    INSERT INTO reflections_fts(rowid, draft, critique, rubric_scores)
    VALUES (new.rowid, new.draft, new.critique, new.rubric_scores);
END;

CREATE TRIGGER IF NOT EXISTS trg_reflections_ad AFTER DELETE ON reflections
BEGIN
    INSERT INTO reflections_fts(reflections_fts, rowid, draft, critique, rubric_scores)
    VALUES('delete', old.rowid, old.draft, old.critique, old.rubric_scores);
END;

CREATE TRIGGER IF NOT EXISTS trg_reflections_au AFTER UPDATE ON reflections
BEGIN
    INSERT INTO reflections_fts(reflections_fts, rowid, draft, critique, rubric_scores)
    VALUES('delete', old.rowid, old.draft, old.critique, old.rubric_scores);
    INSERT INTO reflections_fts(rowid, draft, critique, rubric_scores)
    VALUES (new.rowid, new.draft, new.critique, new.rubric_scores);
END;
"""


def init_db_sync(db_path: str) -> None:
    """Synchronously initialize SQLite database schemas, pragmas, and FTS5 triggers."""
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


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
    neutralizing SQL injection and FTS5 operator syntax errors.
    """
    if not query:
        return ""
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


def create_session_sync(
    task: str,
    threshold: float = 85.0,
    rubric: Optional[str] = None,
    session_id: Optional[str] = None,
    db_path: str = "data/reflections.db",
) -> dict[str, Any]:
    """Synchronously create a new reflection session."""
    sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO sessions (id, task, rubric, threshold, status, final_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'in_progress', NULL, ?, ?)
            """,
            (sid, task, rubric, threshold, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_session_sync(sid, db_path) or {}


async def create_session(
    task: str,
    threshold: float = 85.0,
    rubric: Optional[str] = None,
    session_id: Optional[str] = None,
    db_path: str = "data/reflections.db",
) -> dict[str, Any]:
    """Asynchronously create a new reflection session."""
    sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO sessions (id, task, rubric, threshold, status, final_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'in_progress', NULL, ?, ?)
            """,
            (sid, task, rubric, threshold, now, now),
        )
        await conn.commit()
    return await get_session(sid, db_path) or {}


def get_session_sync(session_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Synchronously retrieve a session with all its reflections."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        sess = dict(row)
        r_cur = conn.execute(
            "SELECT * FROM reflections WHERE session_id = ? ORDER BY iteration ASC",
            (session_id,),
        )
        reflections = []
        for r in r_cur.fetchall():
            rd = dict(r)
            try:
                rd["rubric_scores"] = json.loads(rd["rubric_scores"])
            except Exception:
                pass
            reflections.append(rd)
        sess["iterations"] = reflections
        return sess
    finally:
        conn.close()


async def get_session(session_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Asynchronously retrieve a session with all its reflections."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            sess = dict(row)
        async with conn.execute(
            "SELECT * FROM reflections WHERE session_id = ? ORDER BY iteration ASC",
            (session_id,),
        ) as cur:
            r_rows = await cur.fetchall()
            reflections = []
            for r in r_rows:
                rd = dict(r)
                try:
                    rd["rubric_scores"] = json.loads(rd["rubric_scores"])
                except Exception:
                    pass
                reflections.append(rd)
            sess["iterations"] = reflections
            return sess


def update_session_status_sync(
    session_id: str,
    status: str,
    final_score: Optional[float],
    db_path: str,
) -> None:
    """Synchronously update session status, final_score, and updated_at."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE sessions
            SET status = ?, final_score = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, final_score, now, session_id),
        )
        conn.commit()
    finally:
        conn.close()


async def update_session_status(
    session_id: str,
    status: str,
    final_score: Optional[float],
    db_path: str,
) -> None:
    """Asynchronously update session status, final_score, and updated_at."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET status = ?, final_score = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, final_score, now, session_id),
        )
        await conn.commit()


def add_reflection_sync(
    session_id: str,
    iteration: int,
    draft: str,
    critique: str,
    rubric_scores: dict[str, float],
    composite_score: float,
    status: str = "completed",
    reflection_id: Optional[str] = None,
    db_path: str = "data/reflections.db",
) -> dict[str, Any]:
    """Synchronously insert a reflection and trigger FTS5 sync."""
    rid = reflection_id or f"refl_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    scores_json = json.dumps(rubric_scores)
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO reflections (id, session_id, iteration, draft, critique, rubric_scores, composite_score, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rid, session_id, iteration, draft, critique, scores_json, composite_score, status, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": rid,
        "session_id": session_id,
        "iteration": iteration,
        "draft": draft,
        "critique": critique,
        "rubric_scores": rubric_scores,
        "composite_score": composite_score,
        "status": status,
        "created_at": now,
    }


async def add_reflection(
    session_id: str,
    iteration: int,
    draft: str,
    critique: str,
    rubric_scores: dict[str, float],
    composite_score: float,
    status: str = "completed",
    reflection_id: Optional[str] = None,
    db_path: str = "data/reflections.db",
) -> dict[str, Any]:
    """Asynchronously insert a reflection and trigger FTS5 sync."""
    rid = reflection_id or f"refl_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    scores_json = json.dumps(rubric_scores)
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO reflections (id, session_id, iteration, draft, critique, rubric_scores, composite_score, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rid, session_id, iteration, draft, critique, scores_json, composite_score, status, now),
        )
        await conn.commit()
    return {
        "id": rid,
        "session_id": session_id,
        "iteration": iteration,
        "draft": draft,
        "critique": critique,
        "rubric_scores": rubric_scores,
        "composite_score": composite_score,
        "status": status,
        "created_at": now,
    }


def search_reflections_sync(
    query_str: str,
    db_path: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Synchronously execute FTS5 BM25 ranked full-text query across reflections."""
    sanitized = sanitize_fts5_query(query_str)
    if not sanitized:
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = """
        SELECT
            r.id AS reflection_id,
            r.session_id,
            r.iteration,
            r.draft,
            r.critique,
            r.rubric_scores,
            r.composite_score,
            bm25(reflections_fts) AS score,
            snippet(reflections_fts, -1, '<b>', '</b>', '...', 12) AS snippet
        FROM reflections_fts fts
        JOIN reflections r ON r.rowid = fts.rowid
        WHERE reflections_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
        """
        cur = conn.execute(sql, (sanitized, limit))
        results = []
        for row in cur.fetchall():
            item = dict(row)
            try:
                item["rubric_scores"] = json.loads(item["rubric_scores"])
            except Exception:
                pass
            results.append(item)
        return results
    finally:
        conn.close()


async def search_reflections(
    query_str: str,
    db_path: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Asynchronously execute FTS5 BM25 ranked full-text query across reflections."""
    sanitized = sanitize_fts5_query(query_str)
    if not sanitized:
        return []
    async with get_db_connection(db_path) as conn:
        sql = """
        SELECT
            r.id AS reflection_id,
            r.session_id,
            r.iteration,
            r.draft,
            r.critique,
            r.rubric_scores,
            r.composite_score,
            bm25(reflections_fts) AS score,
            snippet(reflections_fts, -1, '<b>', '</b>', '...', 12) AS snippet
        FROM reflections_fts fts
        JOIN reflections r ON r.rowid = fts.rowid
        WHERE reflections_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
        """
        async with conn.execute(sql, (sanitized, limit)) as cur:
            rows = await cur.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["rubric_scores"] = json.loads(item["rubric_scores"])
                except Exception:
                    pass
                results.append(item)
            return results


async def list_sessions(
    limit: int = 20, db_path: str = "data/reflections.db"
) -> list[dict[str, Any]]:
    """Asynchronously retrieve recent sessions with their reflections."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            sessions = []
            for r in rows:
                s = dict(r)
                async with conn.execute(
                    "SELECT * FROM reflections WHERE session_id = ? ORDER BY iteration ASC",
                    (s["id"],),
                ) as rcur:
                    rrows = await rcur.fetchall()
                    refls = []
                    for row in rrows:
                        rd = dict(row)
                        try:
                            rd["rubric_scores"] = json.loads(rd["rubric_scores"])
                        except Exception:
                            pass
                        refls.append(rd)
                    s["iterations"] = refls
                sessions.append(s)
            return sessions


async def check_database_health(db_path: str) -> dict[str, Any]:
    """Inspect database connectivity, pragma settings, and count sessions and reflections."""
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        journal_row = await cursor.fetchone()
        journal_mode = journal_row[0] if journal_row else "unknown"

        cursor = await conn.execute("SELECT count(*) FROM sessions;")
        sess_row = await cursor.fetchone()
        sessions_count = sess_row[0] if sess_row else 0

        cursor = await conn.execute("SELECT count(*) FROM reflections;")
        refl_row = await cursor.fetchone()
        reflections_count = refl_row[0] if refl_row else 0

        return {
            "journal_mode": journal_mode,
            "status": "connected",
            "database": db_path,
            "sessions_count": sessions_count,
            "reflections_count": reflections_count,
        }
