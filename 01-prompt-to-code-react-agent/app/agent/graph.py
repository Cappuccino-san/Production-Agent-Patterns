"""LangGraph StateGraph workflow construction and conditional routing."""

from typing import Any, Literal, Optional
from langgraph.graph import END, StateGraph

from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import execute_tool_node, finalize_node, reason_node, validate_ast_node
from app.agent.state import AgentState


def should_continue(state: AgentState) -> Literal["execute_tool", "reason", "finalize"]:
    """Conditional routing edge deciding whether to execute, retry, or finalize."""
    is_valid = state.get("is_valid", False)
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 5)

    if is_valid:
        return "execute_tool"
    if iterations < max_iterations:
        return "reason"
    return "finalize"


def create_agent_graph(
    llm: Optional[DeterministicMockLLM] = None,
    checkpointer: Any = None,
) -> Any:
    """Build and compile the ReAct Prompt-to-Code StateGraph."""
    workflow = StateGraph(AgentState)

    # Injectable reason node wrapper
    def bound_reason_node(state: AgentState) -> dict[str, Any]:
        return reason_node(state, llm=llm)

    # Register Nodes
    workflow.add_node("reason", bound_reason_node)
    workflow.add_node("validate_ast", validate_ast_node)
    workflow.add_node("execute_tool", execute_tool_node)
    workflow.add_node("finalize", finalize_node)

    # Set Entry Point
    workflow.set_entry_point("reason")

    # Connect Edges
    workflow.add_edge("reason", "validate_ast")

    # Conditional Branching after AST Validation
    workflow.add_conditional_edges(
        "validate_ast",
        should_continue,
        {
            "execute_tool": "execute_tool",
            "reason": "reason",
            "finalize": "finalize",
        },
    )

    workflow.add_edge("execute_tool", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile(checkpointer=checkpointer)
