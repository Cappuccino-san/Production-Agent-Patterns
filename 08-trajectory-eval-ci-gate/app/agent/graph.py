"""LangGraph state machine graph compilation for Trajectory Eval CI Gate."""

from langgraph.graph import END, START, StateGraph
from app.agent.nodes import TrajectoryGateExecutor
from app.agent.state import TrajectoryEvalState


def create_eval_graph(db_path: str):
    executor = TrajectoryGateExecutor(db_path)
    builder = StateGraph(TrajectoryEvalState)

    builder.add_node("load_dag", executor.load_dag_node)
    builder.add_node("replay", executor.replay_node)
    builder.add_node("verdict", executor.verdict_node)

    builder.add_edge(START, "load_dag")
    builder.add_edge("load_dag", "replay")
    builder.add_edge("replay", "verdict")
    builder.add_edge("verdict", END)

    return builder.compile()
