"""LangGraph state machine for Shadow Trajectory Comparison."""

from typing import Literal
from langgraph.graph import END, StateGraph
from app.agent.comparator import diff_trajectories
from app.agent.state import ShadowComparatorState
from app.agent.topologies import execute_candidate_topology, execute_primary_topology


def primary_runner_node(state: ShadowComparatorState) -> dict:
    """Executes production primary agent topology."""
    primary = execute_primary_topology(state.prompt)
    return {"primary_trajectory": primary}


def check_shadow_sampling(state: ShadowComparatorState) -> Literal["candidate_runner", "__end__"]:
    """Determines whether candidate topology should be mirrored in the shadow plane."""
    if state.is_shadow_sampled:
        return "candidate_runner"
    return END


def candidate_runner_node(state: ShadowComparatorState) -> dict:
    """Executes experimental candidate agent topology in shadow plane."""
    candidate = execute_candidate_topology(state.prompt)
    return {"candidate_trajectory": candidate}


def diff_engine_node(state: ShadowComparatorState) -> dict:
    """Diffs tool-call DAGs, token costs, and latencies between primary and candidate."""
    if not state.primary_trajectory or not state.candidate_trajectory:
        return {}

    report = diff_trajectories(
        request_id=state.request_id,
        prompt=state.prompt,
        primary=state.primary_trajectory,
        candidate=state.candidate_trajectory,
    )
    return {"comparison_report": report}


def build_comparator_graph():
    """Builds and compiles the Shadow Comparator StateGraph."""
    graph = StateGraph(ShadowComparatorState)

    graph.add_node("primary_runner", primary_runner_node)
    graph.add_node("candidate_runner", candidate_runner_node)
    graph.add_node("diff_engine", diff_engine_node)

    graph.set_entry_point("primary_runner")

    graph.add_conditional_edges(
        "primary_runner",
        check_shadow_sampling,
        {
            "candidate_runner": "candidate_runner",
            END: END,
        },
    )

    graph.add_edge("candidate_runner", "diff_engine")
    graph.add_edge("diff_engine", END)

    return graph.compile()
