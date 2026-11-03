"""Deterministic Mock LLM Engine for offline, 100% reliable execution and testing."""

import uuid
from typing import Optional
from app.models import CodeArtifact, ResearchFinding, ReviewAssessment


class DeterministicMockLLM:
    """Simulates LLM inference for Researcher, Coder, and Reviewer agents without network calls."""

    def __init__(self, force_approval_on_iteration: int = 1) -> None:
        self.force_approval_on_iteration = force_approval_on_iteration

    def generate_research(self, topic: str, context: Optional[str] = None) -> ResearchFinding:
        """Produce a strictly typed ResearchFinding packet."""
        sanitized_topic = topic.strip()
        return ResearchFinding(
            topic=sanitized_topic,
            key_points=[
                f"Architecture strategy for '{sanitized_topic}' requires isolated domain modeling.",
                "High-performance concurrency demands asynchronous coroutine scheduling.",
                "State integrity guaranteed via strictly typed Pydantic validation boundaries.",
            ],
            recommendations=[
                "Implement dependency-injected interfaces for clean test mocking.",
                "Enforce WAL journaling and busy timeouts on local persistent storage.",
            ],
            confidence=0.96,
        )

    def generate_code(
        self,
        research: ResearchFinding,
        iteration: int,
        critiques: Optional[list[str]] = None,
    ) -> CodeArtifact:
        """Produce a strictly typed CodeArtifact packet based on research and prior critiques."""
        remediation_note = ""
        if critiques:
            remediation_note = f"\n# Remediation applied for iteration {iteration}: {', '.join(critiques)}"

        code_str = f'''"""Implementation generated for {research.topic}."""
import asyncio

async def execute_task() -> dict[str, str]:
    """Execute high-concurrency swarm task cleanly."""{remediation_note}
    await asyncio.sleep(0.001)
    return {{"status": "success", "iteration": "{iteration}", "topic": "{research.topic}"}}
'''
        test_cases_str = f'''"""Unit test suite for {research.topic}."""
import pytest
from app.models import ResearchFinding

@pytest.mark.asyncio
async def test_execution_basic():
    assert True
'''
        return CodeArtifact(
            filename=f"module_v{iteration}.py",
            language="python",
            code=code_str,
            test_cases=test_cases_str,
            dependencies=["asyncio", "pydantic"],
        )

    def generate_review(
        self,
        artifact: CodeArtifact,
        iteration: int,
    ) -> ReviewAssessment:
        """Produce a strictly typed ReviewAssessment packet evaluating the CodeArtifact."""
        should_approve = iteration >= self.force_approval_on_iteration
        if should_approve:
            return ReviewAssessment(
                approved=True,
                score=98.5,
                critiques=[],
                suggested_fixes=[],
            )
        else:
            return ReviewAssessment(
                approved=False,
                score=72.0,
                critiques=[
                    "Missing explicit type annotations on local helper functions",
                    "Boundary exception recovery logging needs refinement",
                ],
                suggested_fixes=[
                    "Add explicit return type hint to coroutine helper",
                    "Wrap core loop in try/except with structured error logging",
                ],
            )
