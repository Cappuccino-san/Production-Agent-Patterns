"""LangGraph node handlers for the Reflexion Actor-Critic workflow."""

import logging
from typing import Any, Optional

from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import AgentState
from app.database import add_reflection_sync, update_session_status_sync
from app.models import RubricCriterion

logger = logging.getLogger(__name__)


def actor_node(
    state: AgentState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Generate the initial baseline draft solution for the task."""
    engine = llm or DeterministicMockLLM(seed=state.get("seed"))
    task = state.get("task", "").strip()

    initial_draft = engine.generate_initial_draft(task)

    return {
        "current_draft": initial_draft,
        "iteration": 1,
        "status": "in_progress",
        "history": state.get("history", []),
    }


def critic_node(
    state: AgentState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Evaluate current draft against multi-criteria rubric and identify actionable defects."""
    engine = llm or DeterministicMockLLM(seed=state.get("seed"))
    task = state.get("task", "").strip()
    current_draft = state.get("current_draft", "")
    threshold = state.get("threshold", 85.0)

    # Convert custom rubric if supplied
    criteria = None
    custom_rubric_data = state.get("custom_rubric")
    if custom_rubric_data:
        criteria = [
            RubricCriterion(**c) if isinstance(c, dict) else c for c in custom_rubric_data
        ]

    evaluation = engine.evaluate_draft(
        task=task,
        draft=current_draft,
        criteria=criteria,
        threshold=threshold,
    )

    return {
        "rubric_scores": evaluation.criteria_scores,
        "composite_score": evaluation.composite_score,
        "critique": evaluation.critique,
        "defects": evaluation.defects,
        "suggestions": evaluation.suggestions,
        "passed": evaluation.passed,
    }


def reflection_node(
    state: AgentState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Persist reflection iteration into SQLite WAL database and record history."""
    session_id = state.get("session_id", "")
    iteration = state.get("iteration", 1)
    max_iterations = state.get("max_iterations", 4)
    draft = state.get("current_draft", "")
    critique = state.get("critique", "")
    rubric_scores = state.get("rubric_scores", {})
    composite_score = state.get("composite_score", 0.0)
    passed = state.get("passed", False)
    db_path = state.get("db_path")

    # Determine state status
    if passed:
        status = "completed"
    elif iteration >= max_iterations:
        status = "max_iterations_reached"
    else:
        status = "in_progress"

    # Persist in database
    step_record: dict[str, Any] = {}
    if db_path and session_id:
        try:
            step_record = add_reflection_sync(
                session_id=session_id,
                iteration=iteration,
                draft=draft,
                critique=critique,
                rubric_scores=rubric_scores,
                composite_score=composite_score,
                status=status,
                db_path=db_path,
            )
            update_session_status_sync(
                session_id=session_id,
                status=status,
                final_score=composite_score,
                db_path=db_path,
            )
        except Exception as exc:
            logger.error(
                "Failed to record reflection for session %s at iteration %d: %s",
                session_id,
                iteration,
                exc,
                exc_info=True,
            )

    if not step_record:
        step_record = {
            "iteration": iteration,
            "draft": draft,
            "critique": critique,
            "rubric_scores": rubric_scores,
            "composite_score": composite_score,
            "status": status,
            "created_at": "",
        }

    history = list(state.get("history", []))
    history.append(step_record)

    return {
        "status": status,
        "history": history,
    }


def reviser_node(
    state: AgentState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Ingest critique, previous draft, and defects to generate an improved revision."""
    engine = llm or DeterministicMockLLM(seed=state.get("seed"))
    task = state.get("task", "")
    previous_draft = state.get("current_draft", "")
    critique = state.get("critique", "")
    defects = state.get("defects", [])
    current_iteration = state.get("iteration", 1)

    revised_draft = engine.generate_revision(
        task=task,
        previous_draft=previous_draft,
        critique=critique,
        defects=defects,
        iteration=current_iteration,
    )

    next_iteration = current_iteration + 1

    return {
        "current_draft": revised_draft,
        "iteration": next_iteration,
        "status": "in_progress",
    }


def finalize_node(
    state: AgentState,
    llm: Optional[DeterministicMockLLM] = None,
) -> dict[str, Any]:
    """Finalize the reflection loop and commit final summary state."""
    session_id = state.get("session_id", "")
    status = state.get("status", "completed")
    composite_score = state.get("composite_score", 0.0)
    db_path = state.get("db_path")

    if db_path and session_id:
        try:
            update_session_status_sync(
                session_id=session_id,
                status=status,
                final_score=composite_score,
                db_path=db_path,
            )
        except Exception as exc:
            logger.error(
                "Failed to finalize session %s in database: %s",
                session_id,
                exc,
                exc_info=True,
            )

    return {
        "status": status,
    }


def should_continue(state: AgentState) -> str:
    """Conditional router determining whether to refine further or finalize."""
    if state.get("passed", False):
        return "finalize"
    if state.get("iteration", 1) >= state.get("max_iterations", 4):
        return "finalize"
    return "reviser"
