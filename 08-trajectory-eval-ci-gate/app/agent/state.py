"""Typed LangGraph state for Trajectory Eval CI Gate."""

from typing import Annotated, Any, Optional, TypedDict
from app.models import AgentTrajectory, EvalVerdict, GoldenDAG, TrajectoryDeviation


def merge_deviations(
    existing: list[TrajectoryDeviation],
    new_items: list[TrajectoryDeviation],
) -> list[TrajectoryDeviation]:
    return existing + new_items


def merge_logs(
    existing: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return existing + new_items


class TrajectoryEvalState(TypedDict):
    eval_id: str
    dag_id: str
    pr_number: int
    commit_sha: str
    golden_dag: Optional[GoldenDAG]
    trajectories: list[AgentTrajectory]
    total_evaluated: int
    passed_count: int
    failed_count: int
    verdict: EvalVerdict
    fail_on_any_deviation: bool
    deviations: Annotated[list[TrajectoryDeviation], merge_deviations]
    logs: Annotated[list[dict[str, Any]], merge_logs]
