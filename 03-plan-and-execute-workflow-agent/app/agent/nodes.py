"""LangGraph node handlers for Plan-and-Execute workflow."""

import logging
import uuid
from typing import Any, Optional
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import PlanExecuteState
from app.database import (
    replace_remaining_steps_sync,
    update_plan_status_sync,
    update_step_sync,
)

logger = logging.getLogger(__name__)


def planner_node(
    state: PlanExecuteState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Decompose high-level goal into an initial sequence of plan steps."""
    engine = llm or DeterministicMockLLM()
    goal = state.get("goal", "").strip()

    existing_plan = state.get("plan")
    if existing_plan:
        plan = [dict(s) for s in existing_plan]
    else:
        generated = engine.generate_plan(goal)
        plan = []
        for idx, s in enumerate(generated):
            step = dict(s)
            step.setdefault("id", f"step_{uuid.uuid4().hex[:12]}")
            step.setdefault("step_index", idx)
            step.setdefault("status", "pending")
            step.setdefault("result", None)
            step.setdefault("error", None)
            plan.append(step)

    return {
        "plan": plan,
        "current_step_index": state.get("current_step_index", 0),
        "past_steps": state.get("past_steps", []),
        "completed": False,
        "needs_replan": False,
        "replan_count": state.get("replan_count", 0),
        "iterations": state.get("iterations", 0) + 1,
    }


def executor_node(
    state: PlanExecuteState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Execute the current active step in the plan using specialized tools."""
    engine = llm or DeterministicMockLLM()
    plan = [dict(s) for s in state.get("plan", [])]
    current_idx = state.get("current_step_index", 0)
    past_steps = list(state.get("past_steps", []))
    db_path = state.get("db_path")
    plan_id = state.get("plan_id")

    if current_idx >= len(plan):
        return {
            "completed": True,
            "needs_replan": False,
            "iterations": state.get("iterations", 0) + 1,
        }

    current_step = plan[current_idx]
    execution_outcome = engine.execute_step(current_step, past_steps, current_idx)

    status = execution_outcome.get("status", "completed")
    result = execution_outcome.get("result")
    error = execution_outcome.get("error")

    current_step["status"] = status
    current_step["result"] = result
    current_step["error"] = error

    step_record = dict(current_step)
    past_steps.append(step_record)

    # Persist step execution in SQLite WAL database if configured
    step_id = current_step.get("id")
    if db_path and step_id:
        try:
            update_step_sync(step_id, status, result, error, db_path)
            if plan_id:
                update_plan_status_sync(plan_id, "in_progress", current_idx, None, db_path)
        except Exception as exc:
            logger.error(
                "Failed to persist step %s execution in database for plan %s: %s",
                step_id,
                plan_id,
                exc,
                exc_info=True,
            )

    if status == "failed":
        # Step failed; flag for adaptive replanning
        return {
            "plan": plan,
            "current_step_index": current_idx,
            "past_steps": past_steps,
            "needs_replan": True,
            "completed": False,
            "error": error,
            "iterations": state.get("iterations", 0) + 1,
        }

    # Step succeeded; advance index
    next_idx = current_idx + 1
    is_finished = next_idx >= len(plan)

    return {
        "plan": plan,
        "current_step_index": next_idx,
        "past_steps": past_steps,
        "needs_replan": False,
        "completed": is_finished,
        "error": None,
        "iterations": state.get("iterations", 0) + 1,
    }


def replanner_node(
    state: PlanExecuteState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Dynamically reconstruct remaining plan steps after a failure or unexpected finding."""
    engine = llm or DeterministicMockLLM()
    goal = state.get("goal", "")
    plan = [dict(s) for s in state.get("plan", [])]
    current_idx = state.get("current_step_index", 0)
    past_steps = list(state.get("past_steps", []))
    db_path = state.get("db_path")
    plan_id = state.get("plan_id")

    failed_step = past_steps[-1] if past_steps else (plan[current_idx] if current_idx < len(plan) else {})
    remaining_steps = plan[current_idx + 1 :] if (current_idx + 1 < len(plan)) else []

    # Generate adapted plan steps
    new_remaining = engine.replan(goal, failed_step, past_steps, remaining_steps)

    # Reassemble plan: finished steps up to current_idx, then new replacement steps
    rebuilt_plan = plan[:current_idx]
    new_steps_with_id = []
    for offset, ns in enumerate(new_remaining):
        step_entry = dict(ns)
        step_id = step_entry.get("id") or f"step_{uuid.uuid4().hex[:12]}"
        step_entry["id"] = step_id
        step_entry["step_index"] = current_idx + offset
        step_entry.setdefault("status", "pending")
        step_entry.setdefault("result", None)
        step_entry.setdefault("error", None)
        rebuilt_plan.append(step_entry)
        new_steps_with_id.append(step_entry)

    # Update database ledger if attached
    if db_path and plan_id:
        try:
            replace_remaining_steps_sync(plan_id, current_idx, new_steps_with_id, db_path)
        except Exception as exc:
            logger.error(
                "Failed to replace remaining steps for plan %s in database: %s",
                plan_id,
                exc,
                exc_info=True,
            )

    return {
        "plan": rebuilt_plan,
        "current_step_index": current_idx,
        "needs_replan": False,
        "completed": False,
        "replan_count": state.get("replan_count", 0) + 1,
        "error": None,
        "iterations": state.get("iterations", 0) + 1,
    }


def synthesizer_node(
    state: PlanExecuteState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Synthesize all completed step deliverables into a final unified response."""
    engine = llm or DeterministicMockLLM()
    goal = state.get("goal", "")
    past_steps = state.get("past_steps", [])
    plan = state.get("plan", [])
    current_idx = state.get("current_step_index", 0)
    db_path = state.get("db_path")
    plan_id = state.get("plan_id")

    final_response = engine.synthesize(goal, past_steps)

    # A plan is only completed if:
    # 1. Total steps in plan > 0 and current_step_index >= len(plan) (all steps executed)
    # 2. No steps in plan are marked 'failed'
    # 3. No steps in plan are still 'pending'
    # 4. Agent does not have an active needs_replan flag
    all_steps_executed = len(plan) > 0 and current_idx >= len(plan)
    has_failed_step = any(s.get("status") == "failed" for s in plan)
    has_pending_step = any(s.get("status") == "pending" for s in plan)
    needs_replan = state.get("needs_replan", False)

    if all_steps_executed and not has_failed_step and not has_pending_step and not needs_replan:
        status = "completed"
        completed = True
    else:
        status = "failed"
        completed = False

    if db_path and plan_id:
        try:
            update_plan_status_sync(
                plan_id,
                status,
                current_idx,
                final_response,
                db_path,
            )
        except Exception as exc:
            logger.error(
                "Failed to update final plan status for plan %s in database: %s",
                plan_id,
                exc,
                exc_info=True,
            )

    return {
        "response": final_response,
        "completed": completed,
        "needs_replan": False,
        "iterations": state.get("iterations", 0) + 1,
    }
