"""LangGraph state graph definition for Cost Kill-Switch and Model Fallback Middleware."""

from typing import Literal
from langgraph.graph import END, StateGraph
from app.agent.nodes import (
    fallback_router_node,
    fallback_worker_node,
    frontier_planner_node,
    halt_worker_node,
)
from app.agent.state import CostAgentState
from app.models import CostStatus


def route_after_frontier(state: CostAgentState) -> Literal["fallback_router", "frontier_planner", "__end__"]:
    """Routes based on kill-switch status and loop depth."""
    if state.kill_switch_triggered:
        return "fallback_router"
    if state.current_step >= state.max_iterations or state.status == CostStatus.COMPLETED:
        return END
    return "frontier_planner"


def route_after_fallback_decision(state: CostAgentState) -> Literal["fallback_worker", "halt_worker"]:
    """Routes based on fallback viability."""
    if state.status == CostStatus.HALTED_BUDGET_EXCEEDED:
        return "halt_worker"
    return "fallback_worker"


def build_cost_guard_graph():
    """Builds and compiles the Cost Guard StateGraph."""
    graph = StateGraph(CostAgentState)

    graph.add_node("frontier_planner", frontier_planner_node)
    graph.add_node("fallback_router", fallback_router_node)
    graph.add_node("fallback_worker", fallback_worker_node)
    graph.add_node("halt_worker", halt_worker_node)

    graph.set_entry_point("frontier_planner")

    graph.add_conditional_edges(
        "frontier_planner",
        route_after_frontier,
        {
            "fallback_router": "fallback_router",
            "frontier_planner": "frontier_planner",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "fallback_router",
        route_after_fallback_decision,
        {
            "fallback_worker": "fallback_worker",
            "halt_worker": "halt_worker",
        },
    )

    graph.add_edge("fallback_worker", END)
    graph.add_edge("halt_worker", END)

    return graph.compile()
