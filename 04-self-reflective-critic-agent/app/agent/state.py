"""LangGraph state schema for the Reflexion Actor-Critic workflow."""

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """Typed state dictionary passed across nodes in the reflexion graph."""

    session_id: str
    task: str
    threshold: float
    max_iterations: int
    iteration: int
    current_draft: str
    critique: str
    defects: list[str]
    suggestions: list[str]
    rubric_scores: dict[str, float]
    composite_score: float
    passed: bool
    status: str
    custom_rubric: Optional[list[dict[str, Any]]]
    history: list[dict[str, Any]]
    db_path: str
    seed: Optional[int]
