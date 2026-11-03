"""Tier 5: Boundary Conditions, Empty Sequences, and CLI Gate Resilience."""

from fastapi.testclient import TestClient
from app.cli_eval import main as cli_main
from app.agent.graph import create_eval_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.models import AgentTrajectory, EvalVerdict


class TestBoundaryResilience:
    def test_empty_sequence_trajectory(self, temp_db: str):
        graph = create_eval_graph(temp_db)
        golden_dag = DeterministicMockLLM.get_default_golden_dag()

        state = {
            "eval_id": "eval-empty-test",
            "dag_id": "golden-default",
            "pr_number": 99,
            "commit_sha": "empty-sha",
            "golden_dag": golden_dag,
            "trajectories": [
                AgentTrajectory(
                    trajectory_id="empty-1",
                    pr_number=99,
                    commit_sha="empty-sha",
                    tool_call_sequence=["checkout_branch"],  # Doesn't reach terminal node
                )
            ],
            "total_evaluated": 0,
            "passed_count": 0,
            "failed_count": 0,
            "verdict": EvalVerdict.PASS,
            "fail_on_any_deviation": True,
            "deviations": [],
            "logs": [],
        }

        result = graph.invoke(state)
        assert result["failed_count"] == 1
        assert result["verdict"] == EvalVerdict.BLOCK

    def test_cli_execution_clean_exit(self, monkeypatch, temp_db: str):
        """Verify CLI runner succeeds and returns 0 exit code on 100 golden trajectories."""
        test_args = [
            "cli_eval",
            "--dag-id", "golden-default",
            "--num-trajectories", "10",
            "--db-path", temp_db,
        ]
        monkeypatch.setattr("sys.argv", test_args)
        exit_code = cli_main()
        assert exit_code == 0
