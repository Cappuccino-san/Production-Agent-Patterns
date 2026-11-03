"""LangGraph StateGraph orchestration for the Reflexion Actor-Critic workflow."""

from typing import Any, Optional
from langgraph.graph import END, StateGraph

from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    actor_node,
    critic_node,
    finalize_node,
    reflection_node,
    reviser_node,
    should_continue,
)
from app.agent.state import AgentState


def create_reflection_graph(llm: Optional[DeterministicMockLLM] = None) -> Any:
    """Compile and return the complete Reflexion Actor-Critic StateGraph."""
    workflow = StateGraph(AgentState)

    # Node wrappers allowing injected or default mock LLM
    a_node = (lambda s: actor_node(s, llm)) if llm else actor_node
    c_node = (lambda s: critic_node(s, llm)) if llm else critic_node
    r_node = (lambda s: reflection_node(s, llm)) if llm else reflection_node
    rev_node = (lambda s: reviser_node(s, llm)) if llm else reviser_node
    f_node = (lambda s: finalize_node(s, llm)) if llm else finalize_node

    workflow.add_node("actor", a_node)
    workflow.add_node("critic", c_node)
    workflow.add_node("reflection", r_node)
    workflow.add_node("reviser", rev_node)
    workflow.add_node("finalize", f_node)

    # Entry point & edge transitions
    workflow.set_entry_point("actor")
    workflow.add_edge("actor", "critic")
    workflow.add_edge("critic", "reflection")

    workflow.add_conditional_edges(
        "reflection",
        should_continue,
        {
            "reviser": "reviser",
            "finalize": "finalize",
        },
    )

    workflow.add_edge("reviser", "critic")
    workflow.add_edge("finalize", END)

    return workflow.compile()
