"""Synthetic trajectory generator and golden DAG builder for CI evaluation."""

import random
from app.models import AgentTrajectory, GoldenDAG


class DeterministicMockLLM:
    """Generates default golden DAGs and synthetic agent trajectories for testing."""

    @staticmethod
    def get_default_golden_dag(dag_id: str = "golden-default") -> GoldenDAG:
        """Standard Golden DAG for code generation agents:
        checkout_branch -> run_static_analysis -> compile_code -> run_unit_tests -> report_results
        """
        return GoldenDAG(
            dag_id=dag_id,
            name="Default Code Gen Agent Golden DAG",
            allowed_nodes=[
                "checkout_branch",
                "run_static_analysis",
                "compile_code",
                "run_unit_tests",
                "report_results",
            ],
            allowed_transitions=[
                ["checkout_branch", "run_static_analysis"],
                ["run_static_analysis", "compile_code"],
                ["compile_code", "run_unit_tests"],
                ["run_unit_tests", "report_results"],
                # Retry loop on test failure
                ["run_unit_tests", "compile_code"],
            ],
            initial_nodes=["checkout_branch"],
            terminal_nodes=["report_results"],
            strict_topology=True,
        )

    @staticmethod
    def generate_trajectories(
        count: int = 100,
        pr_number: int = 42,
        commit_sha: str = "abc1234",
        inject_deviations: int = 0,
    ) -> list[AgentTrajectory]:
        """Generate test trajectories. If inject_deviations > 0, corrupt that many trajectories."""
        results = []
        for i in range(count):
            traj_id = f"traj-{i + 1:04d}"
            if i < inject_deviations:
                # Deviant trajectory: skips compilation and runs unit tests directly
                seq = ["checkout_branch", "run_static_analysis", "run_unit_tests", "report_results"]
            else:
                # Golden trajectory matching the DAG
                if i % 5 == 0:
                    # Trajectory with one retry loop
                    seq = [
                        "checkout_branch",
                        "run_static_analysis",
                        "compile_code",
                        "run_unit_tests",
                        "compile_code",
                        "run_unit_tests",
                        "report_results",
                    ]
                else:
                    seq = [
                        "checkout_branch",
                        "run_static_analysis",
                        "compile_code",
                        "run_unit_tests",
                        "report_results",
                    ]

            results.append(
                AgentTrajectory(
                    trajectory_id=traj_id,
                    pr_number=pr_number,
                    commit_sha=commit_sha,
                    tool_call_sequence=seq,
                )
            )
        return results
