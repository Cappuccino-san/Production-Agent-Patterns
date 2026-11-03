"""StateGraph node implementations for Researcher, Coder, and Reviewer agents."""

import uuid
from typing import Any
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import SwarmState
from app.database import save_swarm_artifact_sync, save_swarm_step_sync, save_swarm_task_sync
from app.models import SwarmStatus, SwarmStepLog


class SwarmNodeExecutor:
    """Manages node execution and SQLite WAL persistence."""

    def __init__(self, db_path: str, mock_llm: DeterministicMockLLM) -> None:
        self.db_path = db_path
        self.mock_llm = mock_llm

    def researcher_node(self, state: SwarmState) -> dict[str, Any]:
        """Researcher agent: Synthesizes problem into a typed ResearchFinding packet."""
        task_id = state["task_id"]
        topic = state["task_description"]
        context = state.get("context")

        # Produce typed packet
        finding = self.mock_llm.generate_research(topic=topic, context=context)

        step_id = f"step-{uuid.uuid4().hex[:8]}"
        step = SwarmStepLog(
            step_id=step_id,
            agent_role="researcher",
            action="synthesize_requirements",
            packet_type="ResearchFinding",
            payload=finding.model_dump(),
        )

        # Ensure task record exists in SQLite WAL for foreign key integrity
        save_swarm_task_sync(
            db_path=self.db_path,
            task_id=task_id,
            task_description=topic,
            status=SwarmStatus.RESEARCHING,
            iteration=0,
            max_iterations=state.get("max_iterations", 3),
            created_at=finding.created_at,
            updated_at=finding.created_at,
        )

        # Persist finding artifact to SQLite WAL
        artifact_id = f"art-res-{uuid.uuid4().hex[:8]}"
        save_swarm_artifact_sync(
            db_path=self.db_path,
            artifact_id=artifact_id,
            task_id=task_id,
            artifact_type="research",
            title=f"Research on {finding.topic}",
            content="\n".join(finding.key_points + finding.recommendations),
            metadata=finding.model_dump(),
            created_at=finding.created_at,
        )
        save_swarm_step_sync(
            db_path=self.db_path,
            step_id=step_id,
            task_id=task_id,
            agent_role="researcher",
            action="synthesize_requirements",
            packet_type="ResearchFinding",
            payload=finding.model_dump(),
            timestamp=step.timestamp,
        )

        return {
            "research_packet": finding,
            "status": SwarmStatus.CODING,
            "history": [step],
        }

    def coder_node(self, state: SwarmState) -> dict[str, Any]:
        """Coder agent: Consumes typed ResearchFinding and previous critiques to emit CodeArtifact."""
        task_id = state["task_id"]
        research = state["research_packet"]
        iteration = state.get("iteration", 0) + 1
        critiques = state["review_packet"].critiques if state.get("review_packet") else None

        # Produce typed packet
        artifact = self.mock_llm.generate_code(
            research=research,
            iteration=iteration,
            critiques=critiques,
        )

        step_id = f"step-{uuid.uuid4().hex[:8]}"
        step = SwarmStepLog(
            step_id=step_id,
            agent_role="coder",
            action=f"generate_code_iteration_{iteration}",
            packet_type="CodeArtifact",
            payload=artifact.model_dump(),
        )

        # Persist code artifact to SQLite WAL
        art_id = f"art-code-{uuid.uuid4().hex[:8]}"
        save_swarm_artifact_sync(
            db_path=self.db_path,
            artifact_id=art_id,
            task_id=task_id,
            artifact_type="code",
            title=f"Code {artifact.filename}",
            content=f"{artifact.code}\n{artifact.test_cases}",
            metadata=artifact.model_dump(),
            created_at=artifact.created_at,
        )
        save_swarm_step_sync(
            db_path=self.db_path,
            step_id=step_id,
            task_id=task_id,
            agent_role="coder",
            action=f"generate_code_iteration_{iteration}",
            packet_type="CodeArtifact",
            payload=artifact.model_dump(),
            timestamp=step.timestamp,
        )

        return {
            "code_packet": artifact,
            "iteration": iteration,
            "status": SwarmStatus.REVIEWING,
            "history": [step],
        }

    def reviewer_node(self, state: SwarmState) -> dict[str, Any]:
        """Reviewer agent: Evaluates typed CodeArtifact against engineering rubrics."""
        task_id = state["task_id"]
        code = state["code_packet"]
        iteration = state["iteration"]

        # Produce typed packet
        assessment = self.mock_llm.generate_review(artifact=code, iteration=iteration)

        next_status = SwarmStatus.COMPLETED if assessment.approved else (
            SwarmStatus.FAILED if iteration >= state["max_iterations"] else SwarmStatus.CODING
        )

        step_id = f"step-{uuid.uuid4().hex[:8]}"
        step = SwarmStepLog(
            step_id=step_id,
            agent_role="reviewer",
            action=f"review_iteration_{iteration}",
            packet_type="ReviewAssessment",
            payload=assessment.model_dump(),
        )

        # Persist review artifact to SQLite WAL
        art_id = f"art-rev-{uuid.uuid4().hex[:8]}"
        save_swarm_artifact_sync(
            db_path=self.db_path,
            artifact_id=art_id,
            task_id=task_id,
            artifact_type="review",
            title=f"Review Assessment iter {iteration}",
            content=f"Approved: {assessment.approved}, Score: {assessment.score}\nCritiques: {', '.join(assessment.critiques)}",
            metadata=assessment.model_dump(),
            created_at=assessment.created_at,
        )
        save_swarm_step_sync(
            db_path=self.db_path,
            step_id=step_id,
            task_id=task_id,
            agent_role="reviewer",
            action=f"review_iteration_{iteration}",
            packet_type="ReviewAssessment",
            payload=assessment.model_dump(),
            timestamp=step.timestamp,
        )

        return {
            "review_packet": assessment,
            "status": next_status,
            "history": [step],
        }
