"""LangGraph state machine for Teardown Assistant."""

from langgraph.graph import END, StateGraph
from app.agent.nodes import fts_retriever_node, synthesis_node
from app.agent.state import TeardownAssistantState


def build_teardown_agent_graph():
    """Builds and compiles the Teardown Assistant StateGraph."""
    graph = StateGraph(TeardownAssistantState)

    graph.add_node("fts_retriever", fts_retriever_node)
    graph.add_node("synthesis", synthesis_node)

    graph.set_entry_point("fts_retriever")
    graph.add_edge("fts_retriever", "synthesis")
    graph.add_edge("synthesis", END)

    return graph.compile()
