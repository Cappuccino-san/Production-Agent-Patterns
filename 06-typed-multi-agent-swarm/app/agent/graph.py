"""LangGraph state machine graph compilation and conditional routing."""

from typing import Literal
from langgraph.graph import END, START, StateGraph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import SwarmNodeExecutor
from app.agent.state import SwarmState
from app.models import SwarmStatus


def should_continue(state: SwarmState) -> Literal["coder", "__end__"]:
    """Conditional router: loop back to coder if rejected and budget remains; else terminate."""
    status = state.get("status")
    if status in (SwarmStatus.COMPLETED, SwarmStatus.FAILED):
        return "__end__"

    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 3)
    if iteration >= max_iterations:
        return "__end__"

    return "coder"


def create_swarm_graph(db_path: str, mock_llm: DeterministicMockLLM):
    """Compile typed LangGraph state machine with cyclic refinement loop."""
    executor = SwarmNodeExecutor(db_path=db_path, mock_llm=mock_llm)

    builder = StateGraph(SwarmState)
    builder.add_node("researcher", executor.researcher_node)
    builder.add_node("coder", executor.coder_node)
    builder.add_node("reviewer", executor.reviewer_node)

    builder.add_edge(START, "researcher")
    builder.add_edge("researcher", "coder")
    builder.add_edge("coder", "reviewer")

    builder.add_conditional_edges(
        "reviewer",
        should_continue,
        {
            "coder": "coder",
            "__end__": END,
        },
    )

    return builder.compile()
