"""Tier 2: LangGraph State Machine Trajectory Replay and Gate Verdict Tests."""

import pytest
from app.agent.graph import create_eval_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.models import EvalVerdict


class TestAgentGraph:
    def test_replay_100_golden_trajectories_passes_gate(self, temp_db: str):
        graph = create_eval_graph(temp_db)
        golden_dag = DeterministicMockLLM.get_default_golden_dag()
        trajectories = DeterministicMockLLM.generate_trajectories(
            count=100,
            pr_number=88,
            commit_sha="golden-sha",
            inject_deviations=0,
        )

        state = {
            "eval_id": "eval-100-pass",
            "dag_id": "golden-default",
            "pr_number": 88,
            "commit_sha": "golden-sha",
            "golden_dag": golden_dag,
            "trajectories": trajectories,
            "total_evaluated": 0,
            "passed_count": 0,
            "failed_count": 0,
            "verdict": EvalVerdict.PASS,
            "fail_on_any_deviation": True,
            "deviations": [],
            "logs": [],
        }

        result = graph.invoke(state)

        assert result["total_evaluated"] == 100
        assert result["passed_count"] == 100
        assert result["failed_count"] == 0
        assert result["verdict"] == EvalVerdict.PASS
        assert len(result["deviations"]) == 0

    def test_replay_100_trajectories_with_deviations_blocks_pr(self, temp_db: str):
        graph = create_eval_graph(temp_db)
        golden_dag = DeterministicMockLLM.get_default_golden_dag()
        # Inject 3 deviations out of 100
        trajectories = DeterministicMockLLM.generate_trajectories(
            count=100,
            pr_number=89,
            commit_sha="deviant-sha",
            inject_deviations=3,
        )

        state = {
            "eval_id": "eval-100-block",
            "dag_id": "golden-default",
            "pr_number": 89,
            "commit_sha": "deviant-sha",
            "golden_dag": golden_dag,
            "trajectories": trajectories,
            "total_evaluated": 0,
            "passed_count": 0,
            "failed_count": 0,
            "verdict": EvalVerdict.PASS,
            "fail_on_any_deviation": True,
            "deviations": [],
            "logs": [],
        }

        result = graph.invoke(state)

        assert result["total_evaluated"] == 100
        assert result["passed_count"] == 97
        assert result["failed_count"] == 3
        assert result["verdict"] == EvalVerdict.BLOCK
        assert len(result["deviations"]) == 3

        # Verify deviation specifics
        first_dev = result["deviations"][0]
        assert "Illegal edge transition" in first_dev.error_reason
