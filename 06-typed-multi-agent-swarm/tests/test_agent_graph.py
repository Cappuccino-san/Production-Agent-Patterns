"""Tier 2: LangGraph State Machine Execution and Typed Packet Handoff Tests."""

import pytest
from app.agent.graph import create_swarm_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import merge_history
from app.models import (
    CodeArtifact,
    ResearchFinding,
    ReviewAssessment,
    SwarmStatus,
    SwarmStepLog,
)


class TestAgentGraphExecution:
    def test_single_pass_approval(self, temp_db: str, mock_llm: DeterministicMockLLM):
        graph = create_swarm_graph(temp_db, mock_llm)

        initial_state = {
            "task_id": "test-task-1",
            "task_description": "Implement an async sliding window rate limiter",
            "context": "Must handle 10,000 req/sec",
            "iteration": 0,
            "max_iterations": 3,
            "status": SwarmStatus.RESEARCHING,
            "research_packet": None,
            "code_packet": None,
            "review_packet": None,
            "history": [],
        }

        result = graph.invoke(initial_state)

        assert result["status"] == SwarmStatus.COMPLETED
        assert result["iteration"] == 1

        # Verify strict typed packet handoffs
        assert isinstance(result["research_packet"], ResearchFinding)
        assert isinstance(result["code_packet"], CodeArtifact)
        assert isinstance(result["review_packet"], ReviewAssessment)
        assert result["review_packet"].approved is True

        # Verify step history
        roles = [step.agent_role for step in result["history"]]
        assert roles == ["researcher", "coder", "reviewer"]

    def test_multi_iteration_feedback_loop(self, temp_db: str, mock_llm_multi_iter: DeterministicMockLLM):
        graph = create_swarm_graph(temp_db, mock_llm_multi_iter)

        initial_state = {
            "task_id": "test-task-2",
            "task_description": "Build high-throughput pub/sub engine",
            "context": None,
            "iteration": 0,
            "max_iterations": 3,
            "status": SwarmStatus.RESEARCHING,
            "research_packet": None,
            "code_packet": None,
            "review_packet": None,
            "history": [],
        }

        result = graph.invoke(initial_state)

        assert result["status"] == SwarmStatus.COMPLETED
        assert result["iteration"] == 2
        assert result["review_packet"].approved is True

        # Reviewer ran twice, coder ran twice, researcher ran once
        roles = [step.agent_role for step in result["history"]]
        assert roles == ["researcher", "coder", "reviewer", "coder", "reviewer"]

    def test_max_iterations_exhaustion(self, temp_db: str):
        # Force approval only at iteration 5, but max is set to 2
        mock_llm_strict = DeterministicMockLLM(force_approval_on_iteration=5)
        graph = create_swarm_graph(temp_db, mock_llm_strict)

        initial_state = {
            "task_id": "test-task-fail",
            "task_description": "Build distributed Paxos cluster",
            "context": None,
            "iteration": 0,
            "max_iterations": 2,
            "status": SwarmStatus.RESEARCHING,
            "research_packet": None,
            "code_packet": None,
            "review_packet": None,
            "history": [],
        }

        result = graph.invoke(initial_state)

        assert result["status"] == SwarmStatus.FAILED
        assert result["iteration"] == 2
        assert result["review_packet"].approved is False

    def test_merge_history_reducer(self):
        s1 = SwarmStepLog(step_id="1", agent_role="r", action="a", packet_type="P", payload={})
        s2 = SwarmStepLog(step_id="2", agent_role="c", action="b", packet_type="P", payload={})
        s3 = SwarmStepLog(step_id="1", agent_role="r", action="a", packet_type="P", payload={})

        merged = merge_history([s1], [s2, s3])
        assert len(merged) == 2
        assert [m.step_id for m in merged] == ["1", "2"]
