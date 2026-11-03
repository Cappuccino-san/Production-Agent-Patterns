"""Node implementations for loading DAGs, validating trajectories, and synthesizing CI gate verdicts."""

import uuid
from typing import Any
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import TrajectoryEvalState
from app.database import get_golden_dag_sync, save_eval_run_sync, save_golden_dag_sync
from app.models import EvalRunResponse, EvalVerdict, TrajectoryDeviation


class TrajectoryGateExecutor:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def load_dag_node(self, state: TrajectoryEvalState) -> dict[str, Any]:
        dag_id = state["dag_id"]
        dag = get_golden_dag_sync(self.db_path, dag_id)
        if not dag:
            # Fallback to default golden DAG and persist
            dag = DeterministicMockLLM.get_default_golden_dag(dag_id)
            save_golden_dag_sync(self.db_path, dag, "2026-11-02T12:00:00Z")

        return {"golden_dag": dag}

    def replay_node(self, state: TrajectoryEvalState) -> dict[str, Any]:
        dag = state["golden_dag"]
        trajectories = state["trajectories"]

        allowed_edges = {f"{u}->{v}" for u, v in dag.allowed_transitions}
        initial_set = set(dag.initial_nodes)
        terminal_set = set(dag.terminal_nodes)
        allowed_nodes = set(dag.allowed_nodes)

        deviations = []
        logs = []
        passed = 0
        failed = 0

        for traj in trajectories:
            seq = traj.tool_call_sequence
            is_valid = True
            reason = "Valid trajectory adheres to golden DAG"

            # Check 1: Non-empty sequence
            if not seq:
                is_valid = False
                reason = "Trajectory is empty"
                deviations.append(
                    TrajectoryDeviation(
                        trajectory_id=traj.trajectory_id,
                        step_index=0,
                        expected_transitions=list(initial_set),
                        actual_tool_call="",
                        error_reason=reason,
                    )
                )
            else:
                # Check 2: Initial step
                if seq[0] not in initial_set:
                    is_valid = False
                    reason = f"Initial step '{seq[0]}' not in golden initial nodes {sorted(initial_set)}"
                    deviations.append(
                        TrajectoryDeviation(
                            trajectory_id=traj.trajectory_id,
                            step_index=0,
                            expected_transitions=list(initial_set),
                            actual_tool_call=seq[0],
                            error_reason=reason,
                        )
                    )

                # Check 3: Pairwise edge transitions
                if is_valid:
                    for i in range(len(seq) - 1):
                        u, v = seq[i], seq[i + 1]
                        if f"{u}->{v}" not in allowed_edges:
                            is_valid = False
                            reason = f"Illegal edge transition '{u}' -> '{v}' not permitted in golden DAG"
                            deviations.append(
                                TrajectoryDeviation(
                                    trajectory_id=traj.trajectory_id,
                                    step_index=i + 1,
                                    expected_transitions=[edge.split("->")[1] for edge in allowed_edges if edge.startswith(f"{u}->")],
                                    actual_tool_call=v,
                                    error_reason=reason,
                                )
                            )
                            break

                # Check 4: Terminal step
                if is_valid and seq[-1] not in terminal_set:
                    is_valid = False
                    reason = f"Terminal step '{seq[-1]}' not in golden terminal nodes {sorted(terminal_set)}"
                    deviations.append(
                        TrajectoryDeviation(
                            trajectory_id=traj.trajectory_id,
                            step_index=len(seq) - 1,
                            expected_transitions=list(terminal_set),
                            actual_tool_call=seq[-1],
                            error_reason=reason,
                        )
                    )

            if is_valid:
                passed += 1
            else:
                failed += 1

            logs.append({
                "log_id": f"log-{uuid.uuid4().hex[:8]}",
                "trajectory_id": traj.trajectory_id,
                "tool_sequence": seq,
                "is_match": is_valid,
                "deviation_reason": reason,
            })

        return {
            "total_evaluated": len(trajectories),
            "passed_count": passed,
            "failed_count": failed,
            "deviations": deviations,
            "logs": logs,
        }

    def verdict_node(self, state: TrajectoryEvalState) -> dict[str, Any]:
        failed = state["failed_count"]
        fail_on_any = state.get("fail_on_any_deviation", True)

        verdict = EvalVerdict.BLOCK if (failed > 0 and fail_on_any) else EvalVerdict.PASS

        # Persist evaluation and trajectory logs to SQLite WAL
        eval_resp = EvalRunResponse(
            eval_id=state["eval_id"],
            pr_number=state["pr_number"],
            commit_sha=state["commit_sha"],
            dag_id=state["dag_id"],
            total_evaluated=state["total_evaluated"],
            passed_count=state["passed_count"],
            failed_count=state["failed_count"],
            verdict=verdict,
            deviations=state.get("deviations", []),
        )

        save_eval_run_sync(self.db_path, eval_resp, state["logs"])

        return {"verdict": verdict}
