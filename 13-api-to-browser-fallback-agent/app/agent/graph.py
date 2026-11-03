"""LangGraph state graph for API-to-Browser Fallback Agent."""

from typing import Literal
from langgraph.graph import END, StateGraph
from app.agent.nodes import (
    api_executor_node,
    browser_executor_node,
    fallback_router_node,
    result_formatter_node,
)
from app.agent.state import FallbackState


def route_after_router(state: FallbackState) -> Literal["browser_executor", "result_formatter"]:
    """Routes to headless browser executor if fallback was triggered, otherwise formats result."""
    if state.fallback_triggered:
        return "browser_executor"
    return "result_formatter"


def build_fallback_graph():
    """Builds and compiles the API-to-Browser Fallback StateGraph."""
    graph = StateGraph(FallbackState)

    graph.add_node("api_executor", api_executor_node)
    graph.add_node("fallback_router", fallback_router_node)
    graph.add_node("browser_executor", browser_executor_node)
    graph.add_node("result_formatter", result_formatter_node)

    graph.set_entry_point("api_executor")

    graph.add_edge("api_executor", "fallback_router")

    graph.add_conditional_edges(
        "fallback_router",
        route_after_router,
        {
            "browser_executor": "browser_executor",
            "result_formatter": "result_formatter",
        },
    )

    graph.add_edge("browser_executor", "result_formatter")
    graph.add_edge("result_formatter", END)

    return graph.compile()
