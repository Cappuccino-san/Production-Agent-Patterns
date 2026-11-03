"""Deterministic offline Mock LLM engine for Plan-and-Execute agent."""

from typing import Any, Optional


class DeterministicMockLLM:
    """Deterministic mock LLM providing structured planning, step execution, and replanning."""

    def __init__(
        self,
        custom_plan: Optional[list[dict[str, Any]]] = None,
        fail_at_step: Optional[int] = None,
        custom_synthesis: Optional[str] = None,
    ):
        self.custom_plan = custom_plan
        self.fail_at_step = fail_at_step
        self.custom_synthesis = custom_synthesis

    def generate_plan(self, goal: str) -> list[dict[str, Any]]:
        """Decompose a high-level goal into an ordered sequence of executable steps."""
        if self.custom_plan is not None:
            return [dict(s) for s in self.custom_plan]

        lower_goal = goal.lower()

        # Database / SQLite / Search domain
        if any(w in lower_goal for w in ["database", "sqlite", "fts5", "sql", "query"]):
            return [
                {
                    "title": "Design Database Schema and FTS5 Virtual Tables",
                    "description": "Establish relational tables, WAL pragmas, and FTS5 BM25 virtual tables with synchronization triggers.",
                    "tool": "database",
                },
                {
                    "title": "Seed Test Datasets and Verify Indexing",
                    "description": "Ingest baseline documents and verify full-text indexing consistency.",
                    "tool": "database",
                },
                {
                    "title": "Benchmark BM25 Retrieval and Query Latency",
                    "description": "Run search queries with varying token counts and measure sub-millisecond execution.",
                    "tool": "analysis",
                },
                {
                    "title": "Generate Performance Optimization Report",
                    "description": "Consolidate query execution plans, cache hit rates, and concurrency validation.",
                    "tool": "report",
                },
            ]

        # DevOps / Docker / Deployment domain
        if any(w in lower_goal for w in ["docker", "deploy", "ec2", "container", "devops", "ci/cd"]):
            return [
                {
                    "title": "Configure Multi-Stage Container Build",
                    "description": "Author hardened Dockerfile with unprivileged non-root user and minimal attack surface.",
                    "tool": "code",
                },
                {
                    "title": "Set Up Healthcheck and Compose Service",
                    "description": "Define docker-compose orchestration with persistent volume mounts and liveness probe.",
                    "tool": "devops",
                },
                {
                    "title": "Execute Build and Smoke Verification",
                    "description": "Build container image and test port 8000 health endpoints.",
                    "tool": "eval",
                },
                {
                    "title": "Finalize Deployment Manifest and Runbook",
                    "description": "Document production startup commands, environment variables, and rollback steps.",
                    "tool": "report",
                },
            ]

        # Analysis / Research / Finance domain
        if any(w in lower_goal for w in ["analysis", "market", "research", "finance", "data"]):
            return [
                {
                    "title": "Collect and Validate Input Telemetry",
                    "description": "Gather raw data points, parse structure, and sanitize records.",
                    "tool": "analysis",
                },
                {
                    "title": "Execute Statistical and Trend Modeling",
                    "description": "Compute mean, percentile distributions, growth trends, and anomaly indicators.",
                    "tool": "analysis",
                },
                {
                    "title": "Synthesize Actionable Executive Insights",
                    "description": "Formulate core strategic recommendations based on empirical findings.",
                    "tool": "report",
                },
            ]

        # Default multi-step engineering plan
        return [
            {
                "title": f"Analyze Objective and Establish Requirements for '{goal[:40]}'",
                "description": f"Deconstruct constraints, inputs, and acceptance criteria for: {goal}.",
                "tool": "analysis",
            },
            {
                "title": "Implement Core Solution Components",
                "description": "Execute primary technical workstream adhering to specified architecture.",
                "tool": "code",
            },
            {
                "title": "Validate Quality and Verify System Resilience",
                "description": "Run verification checks, regression tests, and boundary assertions.",
                "tool": "eval",
            },
            {
                "title": "Consolidate Deliverables and Finalize Summary",
                "description": "Assemble output artifacts, performance metrics, and operational readiness notes.",
                "tool": "report",
            },
        ]

    def execute_step(
        self,
        step: dict[str, Any],
        past_steps: list[dict[str, Any]],
        step_index: int,
    ) -> dict[str, Any]:
        """Simulate execution of a single plan step, returning result and status."""
        title = step.get("title", f"Step {step_index}")
        desc = step.get("description", "")
        tool = step.get("tool", "general")

        # Explicit failure injection
        if self.fail_at_step == step_index or "simulate_failure" in desc.lower() or "trigger_error" in desc.lower():
            return {
                "status": "failed",
                "error": f"Execution failed at step {step_index} ('{title}'): Simulated external dependency failure.",
                "result": None,
            }

        # Deterministic domain-specific outcomes
        if tool == "database":
            res = (
                f"Successfully initialized SQLite WAL tables and FTS5 BM25 virtual indexing for '{title}'. "
                f"Synchronization triggers verified with zero data drift."
            )
        elif tool == "code":
            res = (
                f"Implemented core logic for '{title}'. Syntax validated with 100% adherence to Pydantic schemas "
                f"and zero runtime exceptions."
            )
        elif tool == "eval":
            res = (
                f"Executed verification suite for '{title}'. All assertions passed with 0 failures, statement coverage >= 90%."
            )
        elif tool == "devops":
            res = (
                f"Configured orchestration and environment for '{title}'. Container health probes returned HTTP 200 OK."
            )
        elif tool == "analysis":
            res = (
                f"Completed analytical evaluation for '{title}'. Processed all input records; metrics within expected thresholds."
            )
        else:
            res = f"Completed step {step_index + 1}: '{title}' using tool '{tool}'. Deliverable validated successfully."

        return {
            "status": "completed",
            "result": res,
            "error": None,
        }

    def replan(
        self,
        goal: str,
        failed_step: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        remaining_steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Adaptively reconstruct remaining plan steps after encountering an error or new constraint."""
        failed_title = failed_step.get("title", "Active Step")
        failed_error = failed_step.get("error", "Unknown error")

        recovery_step = {
            "title": f"Diagnose and Recover from Failure: {failed_title[:50]}",
            "description": f"Apply fallback strategy and remediation for error: '{failed_error}'. Reconfigure execution path.",
            "tool": "eval",
        }

        adjusted_remaining = []
        for s in remaining_steps:
            adj = dict(s)
            adj["description"] = f"[Recovered Path] {adj.get('description', '')}"
            adjusted_remaining.append(adj)

        return [recovery_step] + adjusted_remaining

    def synthesize(
        self,
        goal: str,
        completed_steps: list[dict[str, Any]],
    ) -> str:
        """Synthesize a comprehensive final report summarizing plan accomplishments."""
        if self.custom_synthesis is not None:
            return self.custom_synthesis

        step_summaries = []
        for i, s in enumerate(completed_steps):
            title = s.get("title", f"Step {i+1}")
            status = s.get("status", "completed")
            result = s.get("result") or s.get("error") or "Executed"
            step_summaries.append(f"{i+1}. [{status.upper()}] {title}: {result}")

        summary_body = "\n".join(step_summaries)

        return (
            f"### Plan-and-Execute Workflow Summary\n\n"
            f"**Objective**: {goal}\n\n"
            f"**Execution Trace** ({len(completed_steps)} steps executed):\n"
            f"{summary_body}\n\n"
            f"**Outcome**: Workflow completed successfully. All plan milestones delivered in accordance "
            f"with technical specifications and verification criteria."
        )
