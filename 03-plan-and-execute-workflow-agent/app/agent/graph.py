"""LangGraph StateGraph orchestration for Plan-and-Execute workflow."""

from typing import Any, Optional
from langgraph.graph import END, StateGraph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    executor_node,
    planner_node,
    replanner_node,
    synthesizer_node,
)
from app.agent.state import PlanExecuteState


def should_replan_or_continue(state: PlanExecuteState) -> str:
    """Determine whether to trigger adaptive replanning, continue execution, or synthesize."""
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 15)
    if iterations >= max_iterations:
        return "synthesizer"

    if state.get("needs_replan", False):
        if not state.get("allow_replanning", True):
            return "synthesizer"
        if state.get("replan_count", 0) >= 3:
            return "synthesizer"
        return "replanner"

    current_idx = state.get("current_step_index", 0)
    plan = state.get("plan", [])
    if current_idx >= len(plan):
        return "synthesizer"

    return "executor"


def build_plan_execute_graph(llm: Optional[DeterministicMockLLM] = None) -> Any:
    """Compile and return the complete Plan-and-Execute StateGraph."""
    workflow = StateGraph(PlanExecuteState)

    # Node wrappers allowing injected or default mock LLM
    p_node = (lambda s: planner_node(s, llm)) if llm else planner_node
    e_node = (lambda s: executor_node(s, llm)) if llm else executor_node
    r_node = (lambda s: replanner_node(s, llm)) if llm else replanner_node
    s_node = (lambda s: synthesizer_node(s, llm)) if llm else synthesizer_node

    workflow.add_node("planner", p_node)
    workflow.add_node("executor", e_node)
    workflow.add_node("replanner", r_node)
    workflow.add_node("synthesizer", s_node)

    # Entry point & edge transitions
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "executor")

    workflow.add_conditional_edges(
        "executor",
        should_replan_or_continue,
        {
            "replanner": "replanner",
            "executor": "executor",
            "synthesizer": "synthesizer",
        },
    )

    workflow.add_conditional_edges(
        "replanner",
        should_replan_or_continue,
        {
            "executor": "executor",
            "synthesizer": "synthesizer",
            "replanner": "replanner",
        },
    )

    workflow.add_edge("synthesizer", END)

    return workflow.compile()
