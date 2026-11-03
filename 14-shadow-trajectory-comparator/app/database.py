"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for Shadow Comparator."""

import json
import os
import sqlite3
from typing import Optional
from app.models import (
    AgentTrafficResponse,
    ComparatorSearchHit,
    ComparisonRecommendation,
    ShadowComparisonReport,
    TrajectorySummary,
)


def get_db_connection(db_path: str) -> sqlite3.Connection:
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.isolation_level = None  # Autocommit for PRAGMAs
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.isolation_level = ""
    return conn


def init_db_sync(db_path: str) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_requests (
                request_id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                primary_output TEXT NOT NULL,
                primary_cost_usd REAL NOT NULL,
                primary_latency_ms REAL NOT NULL,
                is_shadow_sampled INTEGER NOT NULL,
                shadow_comparison_id TEXT,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS shadow_comparisons (
                comparison_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL REFERENCES traffic_requests(request_id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                primary_trajectory_json TEXT NOT NULL,
                candidate_trajectory_json TEXT NOT NULL,
                path_similarity_score REAL NOT NULL,
                cost_delta_usd REAL NOT NULL,
                cost_savings_pct REAL NOT NULL,
                latency_delta_ms REAL NOT NULL,
                recommendation TEXT NOT NULL,
                diff_summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS shadow_comparisons_fts USING fts5(
                comparison_id UNINDEXED,
                request_id,
                prompt,
                recommendation,
                diff_summary,
                content='shadow_comparisons',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS shadow_comparisons_ai AFTER INSERT ON shadow_comparisons BEGIN
                INSERT INTO shadow_comparisons_fts(rowid, comparison_id, request_id, prompt, recommendation, diff_summary)
                VALUES (new.rowid, new.comparison_id, new.request_id, new.prompt, new.recommendation, new.diff_summary);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS shadow_comparisons_ad AFTER DELETE ON shadow_comparisons BEGIN
                INSERT INTO shadow_comparisons_fts(shadow_comparisons_fts, rowid, comparison_id, request_id, prompt, recommendation, diff_summary)
                VALUES('delete', old.rowid, old.comparison_id, old.request_id, old.prompt, old.recommendation, old.diff_summary);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS shadow_comparisons_au AFTER UPDATE ON shadow_comparisons BEGIN
                INSERT INTO shadow_comparisons_fts(shadow_comparisons_fts, rowid, comparison_id, request_id, prompt, recommendation, diff_summary)
                VALUES('delete', old.rowid, old.comparison_id, old.request_id, old.prompt, old.recommendation, old.diff_summary);
                INSERT INTO shadow_comparisons_fts(rowid, comparison_id, request_id, prompt, recommendation, diff_summary)
                VALUES (new.rowid, new.comparison_id, new.request_id, new.prompt, new.recommendation, new.diff_summary);
            END;
            """)
    finally:
        conn.close()


def save_traffic_request_sync(db_path: str, response: AgentTrafficResponse) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO traffic_requests (
                    request_id, prompt, primary_output, primary_cost_usd,
                    primary_latency_ms, is_shadow_sampled, shadow_comparison_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    shadow_comparison_id=excluded.shadow_comparison_id;
                """,
                (
                    response.request_id,
                    response.prompt,
                    response.primary_output,
                    response.primary_cost_usd,
                    response.primary_latency_ms,
                    1 if response.is_shadow_sampled else 0,
                    response.shadow_comparison_id,
                    response.created_at,
                ),
            )
    finally:
        conn.close()


def save_shadow_comparison_sync(db_path: str, report: ShadowComparisonReport) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO shadow_comparisons (
                    comparison_id, request_id, prompt, primary_trajectory_json,
                    candidate_trajectory_json, path_similarity_score, cost_delta_usd,
                    cost_savings_pct, latency_delta_ms, recommendation, diff_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comparison_id) DO UPDATE SET
                    recommendation=excluded.recommendation,
                    diff_summary=excluded.diff_summary;
                """,
                (
                    report.comparison_id,
                    report.request_id,
                    report.prompt,
                    json.dumps(report.primary_trajectory.model_dump()),
                    json.dumps(report.candidate_trajectory.model_dump()),
                    report.path_similarity_score,
                    report.cost_delta_usd,
                    report.cost_savings_pct,
                    report.latency_delta_ms,
                    report.recommendation.value,
                    report.diff_summary,
                    report.created_at,
                ),
            )
    finally:
        conn.close()


def get_shadow_comparison_sync(db_path: str, comparison_id: str) -> Optional[dict]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shadow_comparisons WHERE comparison_id = ?", (comparison_id,))
        row = cursor.fetchone()
        if not row:
            return None

        res = dict(row)
        res["primary_trajectory"] = json.loads(res["primary_trajectory_json"])
        res["candidate_trajectory"] = json.loads(res["candidate_trajectory_json"])
        return res
    finally:
        conn.close()


def list_comparisons_sync(db_path: str, limit: int = 20) -> list[dict]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shadow_comparisons ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["primary_trajectory"] = json.loads(d["primary_trajectory_json"])
            d["candidate_trajectory"] = json.loads(d["candidate_trajectory_json"])
            result.append(d)
        return result
    finally:
        conn.close()


def search_comparisons_fts_sync(db_path: str, query: str, limit: int = 10) -> list[ComparatorSearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        sanitized = "".join(c for c in query if c.isalnum() or c in (" ", "-", "_", "*")).strip()
        if not sanitized:
            return []

        cursor.execute(
            """
            SELECT 
                comparison_id,
                request_id,
                recommendation,
                snippet(shadow_comparisons_fts, -1, '<b>', '</b>', '...', 12) AS snippet,
                bm25(shadow_comparisons_fts) AS rank
            FROM shadow_comparisons_fts
            WHERE shadow_comparisons_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            ComparatorSearchHit(
                record_id=r["comparison_id"],
                comparison_id=r["comparison_id"],
                request_id=r["request_id"],
                recommendation=r["recommendation"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
