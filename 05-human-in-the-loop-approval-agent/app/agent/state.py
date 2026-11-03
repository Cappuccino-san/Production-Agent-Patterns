"""LangGraph agent state definition and type hints."""

import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict


class ApprovalAgentState(TypedDict):
    """Central state object passed between nodes in the approval agent graph."""

    thread_id: str
    request_id: str
    action_type: str
    description: str
    payload: dict[str, Any]
    risk_level: str
    status: str
    decision: Optional[str]
    decision_reason: Optional[str]
    decision_by: Optional[str]
    modified_payload: Optional[dict[str, Any]]
    result: Optional[str]
    execution_logs: Annotated[list[str], operator.add]
    created_at: str
    completed_at: Optional[str]
