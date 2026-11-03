"""Tier 1: Pydantic Schema Validation Tests for Trajectory CI Gate."""

import pytest
from pydantic import ValidationError
from app.models import (
    AgentTrajectory,
    EvalRunRequest,
    EvalVerdict,
    GoldenDAG,
    RFC7807Error,
    TrajectoryDeviation,
)


class TestSchemas:
    def test_golden_dag_valid(self):
        dag = GoldenDAG(
            dag_id="custom-dag",
            name="Custom Agent DAG",
            allowed_nodes=["node_a", "node_b"],
            allowed_transitions=[["node_a", "node_b"]],
            initial_nodes=["node_a"],
            terminal_nodes=["node_b"],
        )
        assert dag.dag_id == "custom-dag"
        assert len(dag.allowed_transitions) == 1

    def test_golden_dag_empty_nodes_raises(self):
        with pytest.raises(ValidationError):
            GoldenDAG(
                dag_id="empty",
                name="Empty DAG",
                allowed_nodes=[],
                initial_nodes=["node_a"],
                terminal_nodes=["node_b"],
            )

    def test_agent_trajectory_valid(self):
        traj = AgentTrajectory(
            trajectory_id="traj-1",
            pr_number=55,
            commit_sha="fedcba9",
            tool_call_sequence=["tool1", "tool2"],
        )
        assert traj.pr_number == 55
        assert len(traj.tool_call_sequence) == 2

    def test_trajectory_deviation_model(self):
        dev = TrajectoryDeviation(
            trajectory_id="traj-99",
            step_index=2,
            expected_transitions=["compile_code"],
            actual_tool_call="drop_database",
            error_reason="Illegal tool hop",
        )
        assert dev.actual_tool_call == "drop_database"

    def test_rfc7807_error_model(self):
        err = RFC7807Error(
            title="Validation Error",
            status=422,
            detail="Field missing",
        )
        assert err.status == 422
