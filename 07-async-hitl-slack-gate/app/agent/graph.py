"""LangGraph state machine graphs for drafting and resuming HITL Slack Gate workflows."""

from typing import Literal
from langgraph.graph import END, START, StateGraph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import HITLGateExecutor
from app.agent.state import HITLGateState


def route_decision(state: HITLGateState) -> Literal["execute", "abort"]:
    if state.get("decision") == "approve":
        return "execute"
    return "abort"


def create_draft_graph(db_path: str, mock_llm: DeterministicMockLLM, timeout_hours: int = 72):
    """Compiles the drafting and state serialization phase."""
    executor = HITLGateExecutor(db_path, mock_llm, timeout_hours)
    builder = StateGraph(HITLGateState)
    builder.add_node("draft", executor.draft_node)
    builder.add_node("serialize", executor.serialize_gate_node)

    builder.add_edge(START, "draft")
    builder.add_edge("draft", "serialize")
    builder.add_edge("serialize", END)
    return builder.compile()


def create_resume_graph(db_path: str, mock_llm: DeterministicMockLLM):
    """Compiles the resume and execution phase triggered by Slack webhook decision."""
    executor = HITLGateExecutor(db_path, mock_llm)
    builder = StateGraph(HITLGateState)
    builder.add_node("execute", executor.execute_node)
    builder.add_node("abort", executor.abort_node)

    builder.add_conditional_edges(
        START,
        route_decision,
        {
            "execute": "execute",
            "abort": "abort",
        },
    )
    builder.add_edge("execute", END)
    builder.add_edge("abort", END)
    return builder.compile()
