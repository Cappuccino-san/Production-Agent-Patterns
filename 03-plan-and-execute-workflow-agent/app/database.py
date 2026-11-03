"""SQLite WAL database engine with FTS5 virtual tables, triggers, and BM25 search."""

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

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    total_steps INTEGER NOT NULL DEFAULT 0,
    current_step_index INTEGER NOT NULL DEFAULT 0,
    final_response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_steps (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    tool TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS plan_steps_fts USING fts5(
    title,
    description,
    result,
    content='plan_steps',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_plan_steps_ai AFTER INSERT ON plan_steps
BEGIN
    INSERT INTO plan_steps_fts(rowid, title, description, result)
    VALUES (new.rowid, new.title, new.description, coalesce(new.result, ''));
END;

CREATE TRIGGER IF NOT EXISTS trg_plan_steps_ad AFTER DELETE ON plan_steps
BEGIN
    INSERT INTO plan_steps_fts(plan_steps_fts, rowid, title, description, result)
    VALUES('delete', old.rowid, old.title, old.description, coalesce(old.result, ''));
END;

CREATE TRIGGER IF NOT EXISTS trg_plan_steps_au AFTER UPDATE ON plan_steps
BEGIN
    INSERT INTO plan_steps_fts(plan_steps_fts, rowid, title, description, result)
    VALUES('delete', old.rowid, old.title, old.description, coalesce(old.result, ''));
    INSERT INTO plan_steps_fts(rowid, title, description, result)
    VALUES (new.rowid, new.title, new.description, coalesce(new.result, ''));
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


def create_plan_sync(goal: str, steps: list[dict[str, Any]], db_path: str) -> dict[str, Any]:
    """Synchronously create a plan and its initial steps."""
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO plans (id, goal, status, total_steps, current_step_index, created_at, updated_at)
            VALUES (?, ?, 'created', ?, 0, ?, ?)
            """,
            (plan_id, goal, len(steps), now, now),
        )
        for idx, step in enumerate(steps):
            step_id = step.get("id") or f"step_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO plan_steps (id, plan_id, step_index, title, description, tool, status, result, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    plan_id,
                    idx,
                    step.get("title", f"Step {idx + 1}"),
                    step.get("description", ""),
                    step.get("tool", "general"),
                    step.get("status", "pending"),
                    step.get("result"),
                    step.get("error"),
                    now,
                    now,
                ),
            )
        conn.commit()
    return get_plan_sync(plan_id, db_path) or {}


async def create_plan(goal: str, steps: list[dict[str, Any]], db_path: str) -> dict[str, Any]:
    """Asynchronously create a plan and its initial steps."""
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO plans (id, goal, status, total_steps, current_step_index, created_at, updated_at)
            VALUES (?, ?, 'created', ?, 0, ?, ?)
            """,
            (plan_id, goal, len(steps), now, now),
        )
        for idx, step in enumerate(steps):
            step_id = step.get("id") or f"step_{uuid.uuid4().hex[:12]}"
            await conn.execute(
                """
                INSERT INTO plan_steps (id, plan_id, step_index, title, description, tool, status, result, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    plan_id,
                    idx,
                    step.get("title", f"Step {idx + 1}"),
                    step.get("description", ""),
                    step.get("tool", "general"),
                    step.get("status", "pending"),
                    step.get("result"),
                    step.get("error"),
                    now,
                    now,
                ),
            )
        await conn.commit()
    return await get_plan(plan_id, db_path) or {}


def get_plan_sync(plan_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Synchronously retrieve a plan with its steps."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        plan_row = cur.fetchone()
        if not plan_row:
            return None
        steps_cur = conn.execute(
            "SELECT * FROM plan_steps WHERE plan_id = ? ORDER BY step_index ASC",
            (plan_id,),
        )
        step_rows = steps_cur.fetchall()
        steps = [dict(s) for s in step_rows]
        res = dict(plan_row)
        res["steps"] = steps
        return res


async def get_plan(plan_id: str, db_path: str) -> Optional[dict[str, Any]]:
    """Asynchronously retrieve a plan with its steps."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)) as cur:
            plan_row = await cur.fetchone()
            if not plan_row:
                return None
            plan_dict = dict(plan_row)
        async with conn.execute(
            "SELECT * FROM plan_steps WHERE plan_id = ? ORDER BY step_index ASC",
            (plan_id,),
        ) as cur:
            step_rows = await cur.fetchall()
            plan_dict["steps"] = [dict(s) for s in step_rows]
            return plan_dict


def update_plan_status_sync(
    plan_id: str,
    status: str,
    current_step_index: int,
    final_response: Optional[str],
    db_path: str,
) -> None:
    """Synchronously update plan status and current step index."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE plans
            SET status = ?, current_step_index = ?, final_response = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, current_step_index, final_response, now, plan_id),
        )
        conn.commit()


async def update_plan_status(
    plan_id: str,
    status: str,
    current_step_index: int,
    final_response: Optional[str],
    db_path: str,
) -> None:
    """Asynchronously update plan status and current step index."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            UPDATE plans
            SET status = ?, current_step_index = ?, final_response = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, current_step_index, final_response, now, plan_id),
        )
        await conn.commit()


def update_step_sync(
    step_id: str,
    status: str,
    result: Optional[str],
    error: Optional[str],
    db_path: str,
) -> None:
    """Synchronously update a single step's execution result."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE plan_steps
            SET status = ?, result = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, result, error, now, step_id),
        )
        conn.commit()


async def update_step(
    step_id: str,
    status: str,
    result: Optional[str],
    error: Optional[str],
    db_path: str,
) -> None:
    """Asynchronously update a single step's execution result."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            """
            UPDATE plan_steps
            SET status = ?, result = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, result, error, now, step_id),
        )
        await conn.commit()


def replace_remaining_steps_sync(
    plan_id: str,
    from_index: int,
    new_steps: list[dict[str, Any]],
    db_path: str,
) -> None:
    """Synchronously replace remaining steps starting at from_index with new steps."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM plan_steps WHERE plan_id = ? AND step_index >= ?",
            (plan_id, from_index),
        )
        for offset, step in enumerate(new_steps):
            idx = from_index + offset
            step_id = step.get("id") or f"step_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO plan_steps (id, plan_id, step_index, title, description, tool, status, result, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    plan_id,
                    idx,
                    step.get("title", f"Step {idx + 1}"),
                    step.get("description", ""),
                    step.get("tool", "general"),
                    step.get("status", "pending"),
                    step.get("result"),
                    step.get("error"),
                    now,
                    now,
                ),
            )
        # Recount total steps
        cur = conn.execute("SELECT COUNT(*) FROM plan_steps WHERE plan_id = ?", (plan_id,))
        count = cur.fetchone()[0]
        conn.execute(
            "UPDATE plans SET total_steps = ?, status = 'replanned', updated_at = ? WHERE id = ?",
            (count, now, plan_id),
        )
        conn.commit()


async def replace_remaining_steps(
    plan_id: str,
    from_index: int,
    new_steps: list[dict[str, Any]],
    db_path: str,
) -> None:
    """Asynchronously replace remaining steps starting at from_index with new steps."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db_connection(db_path) as conn:
        await conn.execute(
            "DELETE FROM plan_steps WHERE plan_id = ? AND step_index >= ?",
            (plan_id, from_index),
        )
        for offset, step in enumerate(new_steps):
            idx = from_index + offset
            step_id = step.get("id") or f"step_{uuid.uuid4().hex[:12]}"
            await conn.execute(
                """
                INSERT INTO plan_steps (id, plan_id, step_index, title, description, tool, status, result, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    plan_id,
                    idx,
                    step.get("title", f"Step {idx + 1}"),
                    step.get("description", ""),
                    step.get("tool", "general"),
                    step.get("status", "pending"),
                    step.get("result"),
                    step.get("error"),
                    now,
                    now,
                ),
            )
        async with conn.execute("SELECT COUNT(*) FROM plan_steps WHERE plan_id = ?", (plan_id,)) as cur:
            row = await cur.fetchone()
            count = row[0] if row else from_index + len(new_steps)
        await conn.execute(
            "UPDATE plans SET total_steps = ?, status = 'replanned', updated_at = ? WHERE id = ?",
            (count, now, plan_id),
        )
        await conn.commit()


def search_steps_sync(
    query_str: str,
    db_path: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Synchronously execute FTS5 BM25 ranked full-text query across plan steps."""
    sanitized = sanitize_fts5_query(query_str)
    if not sanitized:
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        sql = """
        SELECT
            s.id AS step_id,
            s.plan_id,
            s.step_index,
            s.title,
            s.description,
            s.result,
            bm25(plan_steps_fts) AS score,
            snippet(plan_steps_fts, -1, '<b>', '</b>', '...', 10) AS snippet
        FROM plan_steps_fts fts
        JOIN plan_steps s ON s.rowid = fts.rowid
        WHERE plan_steps_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
        """
        cur = conn.execute(sql, (sanitized, limit))
        rows = cur.fetchall()
        return [dict(r) for r in rows]


async def search_steps(
    query_str: str,
    db_path: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Asynchronously execute FTS5 BM25 ranked full-text query across plan steps."""
    sanitized = sanitize_fts5_query(query_str)
    if not sanitized:
        return []
    async with get_db_connection(db_path) as conn:
        sql = """
        SELECT
            s.id AS step_id,
            s.plan_id,
            s.step_index,
            s.title,
            s.description,
            s.result,
            bm25(plan_steps_fts) AS score,
            snippet(plan_steps_fts, -1, '<b>', '</b>', '...', 10) AS snippet
        FROM plan_steps_fts fts
        JOIN plan_steps s ON s.rowid = fts.rowid
        WHERE plan_steps_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
        """
        async with conn.execute(sql, (sanitized, limit)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def list_plans(limit: int = 20, db_path: str = "data/plans.db") -> list[dict[str, Any]]:
    """Asynchronously retrieve recent plans ordered by created_at DESC."""
    async with get_db_connection(db_path) as conn:
        async with conn.execute(
            "SELECT * FROM plans ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            plans = []
            for r in rows:
                p = dict(r)
                async with conn.execute(
                    "SELECT * FROM plan_steps WHERE plan_id = ? ORDER BY step_index ASC",
                    (p["id"],),
                ) as scur:
                    srows = await scur.fetchall()
                    p["steps"] = [dict(s) for s in srows]
                plans.append(p)
            return plans


async def check_database_health(db_path: str) -> dict[str, Any]:
    """Inspect database connectivity, pragma settings, and count plans and steps."""
    async with get_db_connection(db_path) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        journal_row = await cursor.fetchone()
        journal_mode = journal_row[0] if journal_row else "unknown"

        cursor = await conn.execute("SELECT count(*) FROM plans;")
        plans_row = await cursor.fetchone()
        plan_count = plans_row[0] if plans_row else 0

        cursor = await conn.execute("SELECT count(*) FROM plan_steps;")
        steps_row = await cursor.fetchone()
        step_count = steps_row[0] if steps_row else 0

        return {
            "journal_mode": journal_mode,
            "status": "connected",
            "database": db_path,
            "plan_count": plan_count,
            "step_count": step_count,
        }
