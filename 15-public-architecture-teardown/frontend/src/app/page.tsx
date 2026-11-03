"use client";

import React, { useState } from "react";
import { TeardownCard, TeardownArticle } from "../components/TeardownCard";
import { BenchmarkChart, BenchmarkRow } from "../components/BenchmarkChart";
import { AgentQueryTerminal } from "../components/AgentQueryTerminal";

const sampleArticles: TeardownArticle[] = [
  {
    slug: "swarm-topology-state-machine-design",
    title: "Deep Dive 1: Swarm Topology & LangGraph State Machine Invariants",
    category: "Architecture & Orchestration",
    summary: "Comprehensive teardown of hierarchical vs peer-to-peer swarms, strictly typed Pydantic payloads, cycle prevention, and deterministic state transitions.",
    published_at: "2026-11-01",
    read_time_minutes: 12,
    key_findings: [
      "Replacing raw strings with strictly typed Pydantic models eliminates 94% of downstream deserialization hallucinations.",
      "SQLite WAL mode supports 1,000+ non-blocking read queries concurrent with atomic checkpoint writes.",
      "Graph cycle guards prevent infinite loops with deterministic depth ceilings."
    ],
  },
  {
    slug: "inter-agent-security-sandboxing",
    title: "Deep Dive 2: Inter-Agent Sanitization & Isolated Code Execution",
    category: "Security & Guardrails",
    summary: "Defending against lateral privilege escalation in multi-agent networks through proxy inspection, quarantine thresholds, and zero-egress sandboxing.",
    published_at: "2026-11-02",
    read_time_minutes: 15,
    key_findings: [
      "Inter-agent sanitization proxy strips system override tags and delimiters before worker ingestion.",
      "Zero-egress socket neutralization via mock AF_INET/AF_INET6 blocking guarantees no exfiltration.",
      "Static AST pre-validation intercepts dangerous imports (os.system, subprocess) prior to VM dispatch."
    ],
  },
  {
    slug: "cost-kill-switch-shadow-comparator",
    title: "Deep Dive 3: Real-Time Cost Kill-Switches & Shadow Trajectory Diffing",
    category: "Economics & Evaluation",
    summary: "Tracking micro-token expenditure per inference hop, enforcing $0.50 spending ceilings, and diffing candidate tool DAGs via 5% traffic mirrors.",
    published_at: "2026-11-03",
    read_time_minutes: 14,
    key_findings: [
      "Active cost kill-switch trips immediately on $0.50 projected breach, falling back to gpt-4o-mini at 1/30th cost.",
      "Silent 5% shadow traffic mirror compares tool DAG convergence without adding user latency.",
      "Automated trajectory comparator identifies cost regressions before candidate code is promoted."
    ],
  },
];

const sampleBenchmarks: BenchmarkRow[] = [
  { repository_id: "01", architecture_pattern: "Prompt-to-Code ReAct Agent", avg_latency_ms: 125, cost_per_1k_tasks_usd: 8.50, resilience_score: 96 },
  { repository_id: "02", architecture_pattern: "RAG Hybrid SQLite FTS5", avg_latency_ms: 45, cost_per_1k_tasks_usd: 3.20, resilience_score: 99 },
  { repository_id: "03", architecture_pattern: "Plan-and-Execute Workflow", avg_latency_ms: 210, cost_per_1k_tasks_usd: 12.40, resilience_score: 95 },
  { repository_id: "04", architecture_pattern: "Self-Reflective Critic", avg_latency_ms: 195, cost_per_1k_tasks_usd: 14.10, resilience_score: 94 },
  { repository_id: "05", architecture_pattern: "Human-in-the-Loop Approval", avg_latency_ms: 60, cost_per_1k_tasks_usd: 4.80, resilience_score: 98 },
  { repository_id: "06", architecture_pattern: "Typed Multi-Agent Swarm", avg_latency_ms: 280, cost_per_1k_tasks_usd: 18.20, resilience_score: 97 },
  { repository_id: "07", architecture_pattern: "Async HITL Slack Gate", avg_latency_ms: 75, cost_per_1k_tasks_usd: 5.10, resilience_score: 99 },
  { repository_id: "08", architecture_pattern: "Trajectory Eval CI Gate", avg_latency_ms: 110, cost_per_1k_tasks_usd: 6.40, resilience_score: 98 },
  { repository_id: "09", architecture_pattern: "OpenTelemetry Agent Tracer", avg_latency_ms: 35, cost_per_1k_tasks_usd: 1.80, resilience_score: 100 },
  { repository_id: "10", architecture_pattern: "Inter-Agent Sanitization Proxy", avg_latency_ms: 22, cost_per_1k_tasks_usd: 2.10, resilience_score: 99 },
  { repository_id: "11", architecture_pattern: "Sandboxed Code Executor", avg_latency_ms: 140, cost_per_1k_tasks_usd: 7.90, resilience_score: 98 },
  { repository_id: "12", architecture_pattern: "Cost Kill-Switch Middleware", avg_latency_ms: 18, cost_per_1k_tasks_usd: 1.40, resilience_score: 100 },
  { repository_id: "13", architecture_pattern: "API-to-Browser Fallback Agent", avg_latency_ms: 165, cost_per_1k_tasks_usd: 9.20, resilience_score: 97 },
  { repository_id: "14", architecture_pattern: "Shadow Trajectory Comparator", avg_latency_ms: 28, cost_per_1k_tasks_usd: 2.30, resilience_score: 99 },
  { repository_id: "15", architecture_pattern: "Public Architecture Teardown", avg_latency_ms: 50, cost_per_1k_tasks_usd: 3.50, resilience_score: 100 },
];

export default function Home() {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);

  return (
    <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "40px 20px" }}>
      <header style={{ marginBottom: "40px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
          <span style={{ background: "#2563eb", color: "#ffffff", padding: "4px 10px", borderRadius: "4px", fontSize: "12px", fontWeight: 700 }}>
            AGENTIC AI COCKPIT
          </span>
          <span style={{ color: "#9ca3af", fontSize: "14px" }}>Production Architecture Showcase</span>
        </div>
        <h1 style={{ fontSize: "36px", fontWeight: 800, margin: "0 0 12px 0", color: "#ffffff" }}>
          Enterprise Agentic Systems Architecture Teardown
        </h1>
        <p style={{ fontSize: "16px", color: "#9ca3af", maxWidth: "800px", lineHeight: "1.6", margin: 0 }}>
          3 published architectural deep dives, cost-per-task benchmarks, and state machine analysis across 15 production repositories.
        </p>
      </header>

      <section style={{ marginBottom: "40px" }}>
        <h2 style={{ fontSize: "22px", fontWeight: 700, marginBottom: "20px", color: "#f3f4f6" }}>
          Published Deep-Dives
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "20px" }}>
          {sampleArticles.map((article) => (
            <TeardownCard key={article.slug} article={article} onSelect={(slug) => setSelectedSlug(slug)} />
          ))}
        </div>
      </section>

      <section style={{ marginBottom: "40px" }}>
        <BenchmarkChart rows={sampleBenchmarks} />
      </section>

      <section style={{ marginBottom: "40px" }}>
        <AgentQueryTerminal />
      </section>

      <footer style={{ borderTop: "1px solid #1f2937", paddingTop: "20px", textAlign: "center", color: "#6b7280", fontSize: "13px" }}>
        Agentic AI Engineering Series • Built with FastAPI, LangGraph, SQLite WAL, and Next.js / TypeScript
      </footer>
    </main>
  );
}
