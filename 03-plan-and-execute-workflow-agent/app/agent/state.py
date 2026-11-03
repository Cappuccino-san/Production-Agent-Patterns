"""LangGraph state schema for Plan-and-Execute workflow."""

from typing import Any, Optional, TypedDict


class PlanExecuteState(TypedDict, total=False):
    """Execution state tracked across the LangGraph Plan-and-Execute lifecycle."""

    goal: str
    plan: list[dict[str, Any]]
    current_step_index: int
    past_steps: list[dict[str, Any]]
    response: Optional[str]
    needs_replan: bool
    completed: bool
    iterations: int
    max_iterations: int
    replan_count: int
    allow_replanning: bool
    plan_id: Optional[str]
    db_path: Optional[str]
    error: Optional[str]
