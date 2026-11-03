"""LangGraph StateGraph assembly, compilation, and execution orchestration."""

from typing import Any, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import (
    approval_gate_node,
    audit_node,
    execution_node,
    rejection_node,
    route_after_gate,
    route_after_triage,
    triage_node,
)
from app.agent.state import ApprovalAgentState


def create_approval_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """Construct and compile the Human-in-the-Loop StateGraph.

    Freezes execution at `approval_gate_node` for any action requiring human approval.
    """
    builder = StateGraph(ApprovalAgentState)

    builder.add_node("triage_node", triage_node)
    builder.add_node("approval_gate_node", approval_gate_node)
    builder.add_node("execution_node", execution_node)
    builder.add_node("rejection_node", rejection_node)
    builder.add_node("audit_node", audit_node)

    builder.add_edge(START, "triage_node")
    builder.add_conditional_edges(
        "triage_node",
        route_after_triage,
        {
            "execution_node": "execution_node",
            "approval_gate_node": "approval_gate_node",
        },
    )
    builder.add_conditional_edges(
        "approval_gate_node",
        route_after_gate,
        {
            "execution_node": "execution_node",
            "rejection_node": "rejection_node",
        },
    )
    builder.add_edge("execution_node", "audit_node")
    builder.add_edge("rejection_node", "audit_node")
    builder.add_edge("audit_node", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["approval_gate_node"],
    )


def submit_action_to_graph(
    graph: CompiledStateGraph,
    thread_id: str,
    request_id: str,
    action_type: str,
    description: str,
    payload: dict[str, Any],
    risk_level: Optional[str] = None,
    created_at: Optional[str] = None,
) -> dict[str, Any]:
    """Submit a new action request to the LangGraph pipeline."""
    initial_state: ApprovalAgentState = {
        "thread_id": thread_id,
        "request_id": request_id,
        "action_type": action_type,
        "description": description,
        "payload": payload,
        "risk_level": risk_level or "",
        "status": "submitted",
        "decision": None,
        "decision_reason": None,
        "decision_by": None,
        "modified_payload": None,
        "result": None,
        "execution_logs": [f"Request '{request_id}' submitted into thread '{thread_id}'."],
        "created_at": created_at or "",
        "completed_at": None,
    }
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(initial_state, config)
    state_snapshot = graph.get_state(config)
    return {
        "values": state_snapshot.values,
        "next": state_snapshot.next,
    }


def resume_graph_with_decision(
    graph: CompiledStateGraph,
    thread_id: str,
    decision: str,
    decision_by: str,
    decision_reason: Optional[str] = None,
    modified_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Resume an interrupted LangGraph execution thread with reviewer decision."""
    config = {"configurable": {"thread_id": thread_id}}
    update_data: dict[str, Any] = {
        "decision": decision,
        "decision_by": decision_by,
        "decision_reason": decision_reason,
    }
    if modified_payload is not None:
        update_data["modified_payload"] = modified_payload

    graph.update_state(config, update_data)
    graph.invoke(None, config)
    state_snapshot = graph.get_state(config)
    return {
        "values": state_snapshot.values,
        "next": state_snapshot.next,
    }
