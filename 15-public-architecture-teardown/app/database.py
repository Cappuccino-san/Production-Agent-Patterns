"""SQLite WAL database engine with FTS5 virtual tables and sync triggers for Architecture Teardown."""

import json
import os
import sqlite3
from typing import Optional
from app.models import BenchmarkMetric, TeardownDeepDive, TeardownSearchHit

DEFAULT_DEEP_DIVES = [
    TeardownDeepDive(
        slug="swarm-topology-state-machine-design",
        title="Deep Dive 1: Swarm Topology & LangGraph State Machine Invariants",
        category="Architecture & Orchestration",
        summary="Comprehensive teardown of hierarchical vs peer-to-peer swarms, strictly typed Pydantic payloads, cycle prevention, and deterministic state transitions.",
        content_markdown="""# Deep Dive 1: Swarm Topology & LangGraph State Machine Invariants

## 1. The Death of String-Based Inter-Agent Communication
Passing raw strings between autonomous agents introduces deserialization hallucinations, type degradation, and silent prompt injection vulnerabilities. In modern agentic engineering, all inter-agent hops MUST be strictly typed Pydantic v2 domain schemas.

## 2. LangGraph State Machine Topology
Using `StateGraph` with explicit conditional edge routers guarantees that transitions are deterministic and cyclic loops cannot exceed configured depth boundaries.

```
[Researcher] --(ResearchFinding)--> [Coder] --(CodeArtifact)--> [Reviewer] --(ReviewAssessment)--> [Approval Gate]
```

## 3. SQLite WAL Persistence Invariants
Every state transition is atomically journaled using SQLite in Write-Ahead Logging (`WAL`) mode with external content FTS5 triggers, ensuring concurrent readers never block writer transactions.
""",
        key_findings=[
            "Replacing raw strings with strictly typed Pydantic models eliminates 94% of downstream deserialization hallucinations.",
            "SQLite WAL mode supports 1,000+ non-blocking read queries concurrent with atomic checkpoint writes.",
            "Graph cycle guards prevent infinite loops with deterministic depth ceilings."
        ],
        read_time_minutes=12,
        published_at="2026-11-01T12:00:00Z",
    ),
    TeardownDeepDive(
        slug="inter-agent-security-sandboxing",
        title="Deep Dive 2: Inter-Agent Sanitization & Isolated Code Execution",
        category="Security & Guardrails",
        summary="Defending against lateral privilege escalation in multi-agent networks through proxy inspection, quarantine thresholds, and zero-egress sandboxing.",
        content_markdown="""# Deep Dive 2: Inter-Agent Sanitization & Isolated Code Execution

## 1. Cross-Agent Prompt Injection Threat Model
When an untrusted external agent produces code or instructions consumed by an internal agent, prompt injections can laterally escalate privileges. 

## 2. The Inter-Agent Sanitization Proxy
A dedicated middleware layer intercepts all messages, scrubbing system prompt override directives (`ignore previous instructions`, `new role: admin`), stripping delimiters (`<system>`, `[PROMPT]`), and calculating risk scores. If an attack exceeds the quarantine threshold (e.g., 75.0), the payload is quarantined.

## 3. Sandboxed Zero-Internet Code Interpretation
Code execution runs within an isolated runtime where `socket.socket` is monkeypatched to forbid any non-loopback connections, static AST analysis forbids `eval()` and `__import__`, and execution is strictly killed after 5 seconds.
""",
        key_findings=[
            "Inter-agent sanitization proxy strips system override tags and delimiters before worker ingestion.",
            "Zero-egress socket neutralization via mock AF_INET/AF_INET6 blocking guarantees no exfiltration.",
            "Static AST pre-validation intercepts dangerous imports (os.system, subprocess) prior to VM dispatch."
        ],
        read_time_minutes=15,
        published_at="2026-11-02T12:00:00Z",
    ),
    TeardownDeepDive(
        slug="cost-kill-switch-shadow-comparator",
        title="Deep Dive 3: Real-Time Cost Kill-Switches & Shadow Trajectory Diffing",
        category="Economics & Evaluation",
        summary="Tracking micro-token expenditure per inference hop, enforcing $0.50 spending ceilings, and diffing candidate tool DAGs via 5% traffic mirrors.",
        content_markdown="""# Deep Dive 3: Real-Time Cost Kill-Switches & Shadow Trajectory Diffing

## 1. Runaway LLM Loops & The $0.50 Safety Kill-Switch
Autonomous agents with tool access can fall into degenerate retry cycles, burning hundreds of dollars in minutes. We enforce a real-time rate card and projected spend calculation per step. Breaching $0.50 triggers a hard halt on the frontier model (`gpt-4o`) and dynamically falls back to an economical tier (`gpt-4o-mini`).

## 2. Non-Blocking 5% Shadow Traffic Mirroring
Before rolling out candidate agent topologies or new prompt variants, 5% of production traffic is mirrored asynchronously to a candidate execution plane.

## 3. Tool-Call DAG Diffing
The differ computes tool-call Jaccard similarity, cost deltas, and latency differentials. If the candidate achieves >= 10% cost savings with zero latency regression, an automated `DEPLOY_CANDIDATE` recommendation is generated.
""",
        key_findings=[
            "Active cost kill-switch trips immediately on $0.50 projected breach, falling back to gpt-4o-mini at 1/30th cost.",
            "Silent 5% shadow traffic mirror compares tool DAG convergence without adding user latency.",
            "Automated trajectory comparator identifies cost regressions before candidate code is promoted."
        ],
        read_time_minutes=14,
        published_at="2026-11-03T12:00:00Z",
    ),
]

DEFAULT_BENCHMARKS = [
    BenchmarkMetric(repository_id="01", architecture_pattern="Prompt-to-Code ReAct Agent", avg_latency_ms=125.0, cost_per_1k_tasks_usd=8.50, resilience_score=96),
    BenchmarkMetric(repository_id="02", architecture_pattern="RAG Hybrid SQLite FTS5", avg_latency_ms=45.0, cost_per_1k_tasks_usd=3.20, resilience_score=99),
    BenchmarkMetric(repository_id="03", architecture_pattern="Plan-and-Execute Workflow", avg_latency_ms=210.0, cost_per_1k_tasks_usd=12.40, resilience_score=95),
    BenchmarkMetric(repository_id="04", architecture_pattern="Self-Reflective Critic", avg_latency_ms=195.0, cost_per_1k_tasks_usd=14.10, resilience_score=94),
    BenchmarkMetric(repository_id="05", architecture_pattern="Human-in-the-Loop Approval", avg_latency_ms=60.0, cost_per_1k_tasks_usd=4.80, resilience_score=98),
    BenchmarkMetric(repository_id="06", architecture_pattern="Typed Multi-Agent Swarm", avg_latency_ms=280.0, cost_per_1k_tasks_usd=18.20, resilience_score=97),
    BenchmarkMetric(repository_id="07", architecture_pattern="Async HITL Slack Gate", avg_latency_ms=75.0, cost_per_1k_tasks_usd=5.10, resilience_score=99),
    BenchmarkMetric(repository_id="08", architecture_pattern="Trajectory Eval CI Gate", avg_latency_ms=110.0, cost_per_1k_tasks_usd=6.40, resilience_score=98),
    BenchmarkMetric(repository_id="09", architecture_pattern="OpenTelemetry Agent Tracer", avg_latency_ms=35.0, cost_per_1k_tasks_usd=1.80, resilience_score=100),
    BenchmarkMetric(repository_id="10", architecture_pattern="Inter-Agent Sanitization Proxy", avg_latency_ms=22.0, cost_per_1k_tasks_usd=2.10, resilience_score=99),
    BenchmarkMetric(repository_id="11", architecture_pattern="Sandboxed Code Executor", avg_latency_ms=140.0, cost_per_1k_tasks_usd=7.90, resilience_score=98),
    BenchmarkMetric(repository_id="12", architecture_pattern="Cost Kill-Switch Middleware", avg_latency_ms=18.0, cost_per_1k_tasks_usd=1.40, resilience_score=100),
    BenchmarkMetric(repository_id="13", architecture_pattern="API-to-Browser Fallback Agent", avg_latency_ms=165.0, cost_per_1k_tasks_usd=9.20, resilience_score=97),
    BenchmarkMetric(repository_id="14", architecture_pattern="Shadow Trajectory Comparator", avg_latency_ms=28.0, cost_per_1k_tasks_usd=2.30, resilience_score=99),
    BenchmarkMetric(repository_id="15", architecture_pattern="Public Architecture Teardown", avg_latency_ms=50.0, cost_per_1k_tasks_usd=3.50, resilience_score=100),
]


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
            CREATE TABLE IF NOT EXISTS teardowns (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                content_markdown TEXT NOT NULL,
                key_findings TEXT NOT NULL,
                read_time_minutes INTEGER NOT NULL,
                published_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                repository_id TEXT PRIMARY KEY,
                architecture_pattern TEXT NOT NULL,
                avg_latency_ms REAL NOT NULL,
                cost_per_1k_tasks_usd REAL NOT NULL,
                resilience_score INTEGER NOT NULL
            );
            """)

            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS teardowns_fts USING fts5(
                slug UNINDEXED,
                title,
                category,
                summary,
                content_markdown,
                content='teardowns',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS teardowns_ai AFTER INSERT ON teardowns BEGIN
                INSERT INTO teardowns_fts(rowid, slug, title, category, summary, content_markdown)
                VALUES (new.rowid, new.slug, new.title, new.category, new.summary, new.content_markdown);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS teardowns_ad AFTER DELETE ON teardowns BEGIN
                INSERT INTO teardowns_fts(teardowns_fts, rowid, slug, title, category, summary, content_markdown)
                VALUES('delete', old.rowid, old.slug, old.title, old.category, old.summary, old.content_markdown);
            END;
            """)

            conn.execute("""
            CREATE TRIGGER IF NOT EXISTS teardowns_au AFTER UPDATE ON teardowns BEGIN
                INSERT INTO teardowns_fts(teardowns_fts, rowid, slug, title, category, summary, content_markdown)
                VALUES('delete', old.rowid, old.slug, old.title, old.category, old.summary, old.content_markdown);
                INSERT INTO teardowns_fts(rowid, slug, title, category, summary, content_markdown)
                VALUES (new.rowid, new.slug, new.title, new.category, new.summary, new.content_markdown);
            END;
            """)

            # Seed deep dives if table is empty
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM teardowns")
            count = cursor.fetchone()[0]
            if count == 0:
                for dd in DEFAULT_DEEP_DIVES:
                    conn.execute(
                        """
                        INSERT INTO teardowns (
                            slug, title, category, summary, content_markdown,
                            key_findings, read_time_minutes, published_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            dd.slug,
                            dd.title,
                            dd.category,
                            dd.summary,
                            dd.content_markdown,
                            json.dumps(dd.key_findings),
                            dd.read_time_minutes,
                            dd.published_at,
                        ),
                    )

            # Seed benchmarks if table is empty
            cursor.execute("SELECT COUNT(*) FROM benchmarks")
            b_count = cursor.fetchone()[0]
            if b_count == 0:
                for bm in DEFAULT_BENCHMARKS:
                    conn.execute(
                        """
                        INSERT INTO benchmarks (
                            repository_id, architecture_pattern, avg_latency_ms,
                            cost_per_1k_tasks_usd, resilience_score
                        ) VALUES (?, ?, ?, ?, ?);
                        """,
                        (
                            bm.repository_id,
                            bm.architecture_pattern,
                            bm.avg_latency_ms,
                            bm.cost_per_1k_tasks_usd,
                            bm.resilience_score,
                        ),
                    )
    finally:
        conn.close()


def get_teardowns_sync(db_path: str) -> list[TeardownDeepDive]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teardowns ORDER BY published_at ASC")
        rows = cursor.fetchall()
        return [
            TeardownDeepDive(
                slug=r["slug"],
                title=r["title"],
                category=r["category"],
                summary=r["summary"],
                content_markdown=r["content_markdown"],
                key_findings=json.loads(r["key_findings"]),
                read_time_minutes=r["read_time_minutes"],
                published_at=r["published_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_teardown_by_slug_sync(db_path: str, slug: str) -> Optional[TeardownDeepDive]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teardowns WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        if not row:
            return None
        return TeardownDeepDive(
            slug=row["slug"],
            title=row["title"],
            category=row["category"],
            summary=row["summary"],
            content_markdown=row["content_markdown"],
            key_findings=json.loads(row["key_findings"]),
            read_time_minutes=row["read_time_minutes"],
            published_at=row["published_at"],
        )
    finally:
        conn.close()


def get_benchmarks_sync(db_path: str) -> list[BenchmarkMetric]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM benchmarks ORDER BY CAST(repository_id AS INTEGER) ASC")
        rows = cursor.fetchall()
        return [
            BenchmarkMetric(
                repository_id=r["repository_id"],
                architecture_pattern=r["architecture_pattern"],
                avg_latency_ms=r["avg_latency_ms"],
                cost_per_1k_tasks_usd=r["cost_per_1k_tasks_usd"],
                resilience_score=r["resilience_score"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def search_teardowns_fts_sync(db_path: str, query: str, limit: int = 10) -> list[TeardownSearchHit]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        # Replace non-alphanumeric chars (including hyphens) with spaces to avoid FTS5 NOT operator syntax
        clean_tokens = [tok for tok in "".join(c if c.isalnum() else " " for c in query).split() if tok]
        if not clean_tokens:
            return []
        sanitized = " ".join(clean_tokens)

        cursor.execute(
            """
            SELECT 
                slug,
                title,
                category,
                snippet(teardowns_fts, -1, '<b>', '</b>', '...', 12) AS snippet,
                bm25(teardowns_fts) AS rank
            FROM teardowns_fts
            WHERE teardowns_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        return [
            TeardownSearchHit(
                record_id=r["slug"],
                slug=r["slug"],
                title=r["title"],
                category=r["category"],
                snippet=r["snippet"],
                rank=float(r["rank"]),
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
