"""StateGraph compilation for OpenTelemetry Traced Agent."""

from langgraph.graph import END, START, StateGraph
from app.agent.nodes import TracedNodeExecutor
from app.agent.state import TracedAgentState
from app.tracer import AgentTracer


def create_traced_graph(db_path: str, tracer: AgentTracer):
    executor = TracedNodeExecutor(db_path, tracer)
    builder = StateGraph(TracedAgentState)

    builder.add_node("reasoning", executor.reasoning_node)
    builder.add_node("tool", executor.tool_node)
    builder.add_node("mutation", executor.mutation_node)

    builder.add_edge(START, "reasoning")
    builder.add_edge("reasoning", "tool")
    builder.add_edge("tool", "mutation")
    builder.add_edge("mutation", END)

    return builder.compile()
