"""Typed LangGraph State definition for Multi-Agent Swarm."""

from typing import Annotated, Optional, TypedDict
from app.models import CodeArtifact, ResearchFinding, ReviewAssessment, SwarmStatus, SwarmStepLog


def merge_history(
    existing: list[SwarmStepLog],
    new_items: list[SwarmStepLog],
) -> list[SwarmStepLog]:
    """Reducer combining step audit logs without duplicates."""
    seen_ids = {item.step_id for item in existing}
    combined = list(existing)
    for item in new_items:
        if item.step_id not in seen_ids:
            combined.append(item)
            seen_ids.add(item.step_id)
    return combined


class SwarmState(TypedDict):
    """LangGraph state machine state where all agents pass strictly typed objects."""
    task_id: str
    task_description: str
    context: Optional[str]
    iteration: int
    max_iterations: int
    status: SwarmStatus
    # Strictly typed packet payloads (never raw untyped strings)
    research_packet: Optional[ResearchFinding]
    code_packet: Optional[CodeArtifact]
    review_packet: Optional[ReviewAssessment]
    # Reducer-managed immutable step history
    history: Annotated[list[SwarmStepLog], merge_history]
