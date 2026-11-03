"""StateGraph compilation for Sandboxed Code Interpreter Agent."""

from langgraph.graph import END, START, StateGraph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import CodeInterpreterExecutor
from app.agent.state import CodeInterpreterState


def create_interpreter_graph(db_path: str, mock_llm: DeterministicMockLLM):
    executor = CodeInterpreterExecutor(db_path, mock_llm)
    builder = StateGraph(CodeInterpreterState)

    builder.add_node("generator", executor.generate_code_node)
    builder.add_node("ast_gate", executor.ast_gate_node)
    builder.add_node("sandbox", executor.execute_node)

    builder.add_edge(START, "generator")
    builder.add_edge("generator", "ast_gate")
    builder.add_edge("ast_gate", "sandbox")
    builder.add_edge("sandbox", END)

    return builder.compile()
