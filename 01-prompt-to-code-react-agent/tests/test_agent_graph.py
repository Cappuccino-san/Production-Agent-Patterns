"""Tier 2: LangGraph State Machine, Nodes, and Conditional Routing Tests."""

import pytest

from app.agent.graph import create_agent_graph, should_continue
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import execute_tool_node, finalize_node, reason_node, validate_ast_node
from app.agent.state import AgentState


@pytest.mark.graph
def test_reason_node_increments_iterations_and_logs_steps() -> None:
    """Verify reason_node increments iteration counter and appends steps."""
    initial_state: AgentState = {
        "prompt": "Calculate factorial of 5",
        "language": "python",
        "code": "",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 0,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    update = reason_node(initial_state)
    assert update["iterations"] == 1
    assert "code" in update
    assert len(update["steps"]) == 2
    assert "Thought:" in update["steps"][0]
    assert "Action:" in update["steps"][1]


@pytest.mark.graph
def test_validate_ast_node_success() -> None:
    """Verify validate_ast_node validates syntactically correct Python code."""
    valid_state: AgentState = {
        "prompt": "Test",
        "language": "python",
        "code": "def greet(name: str) -> str:\n    return f'Hello {name}'\n",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    update = validate_ast_node(valid_state)
    assert update["is_valid"] is True
    assert update["error"] is None
    assert "passed with zero errors" in update["steps"][0]


@pytest.mark.graph
def test_validate_ast_node_syntax_error() -> None:
    """Verify validate_ast_node catches syntax errors with line numbers."""
    broken_state: AgentState = {
        "prompt": "Test",
        "language": "python",
        "code": "def broken_func(\n    return 42",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    update = validate_ast_node(broken_state)
    assert update["is_valid"] is False
    assert "SyntaxError on line" in update["error"]
    assert "AST validation detected error" in update["steps"][0]


@pytest.mark.graph
def test_execute_tool_node_captures_stdout() -> None:
    """Verify execute_tool_node executes in sandbox and captures stdout."""
    code_state: AgentState = {
        "prompt": "Test",
        "language": "python",
        "code": "total = sum([1, 2, 3, 4])\nprint(f'Sum: {total}')",
        "is_valid": True,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    update = execute_tool_node(code_state)
    assert update["output"] == "Sum: 10"
    assert "Executed sandbox runner" in update["steps"][0]


@pytest.mark.graph
def test_execute_tool_node_handles_runtime_exception() -> None:
    """Verify execute_tool_node catches runtime errors cleanly."""
    failing_state: AgentState = {
        "prompt": "Test",
        "language": "python",
        "code": "raise ValueError('Custom sandbox failure')",
        "is_valid": True,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    update = execute_tool_node(failing_state)
    assert update["output"] is None
    assert "RuntimeError during sandbox execution" in update["error"]


@pytest.mark.graph
def test_finalize_node() -> None:
    """Verify finalize_node marks state as completed."""
    state: AgentState = {
        "prompt": "Test",
        "language": "python",
        "code": "print('Done')",
        "is_valid": True,
        "output": "Done",
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    update = finalize_node(state)
    assert update["completed"] is True
    assert update["output"] == "Done"


@pytest.mark.graph
def test_should_continue_routing() -> None:
    """Verify conditional edge decisions."""
    # 1. Valid code -> execute_tool
    valid_state: AgentState = {
        "prompt": "T",
        "language": "python",
        "code": "pass",
        "is_valid": True,
        "output": None,
        "steps": [],
        "iterations": 1,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    assert should_continue(valid_state) == "execute_tool"

    # 2. Invalid code with budget remaining -> reason (retry loop)
    retry_state: AgentState = {
        "prompt": "T",
        "language": "python",
        "code": "bad",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 2,
        "max_iterations": 5,
        "completed": False,
        "error": "SyntaxError",
    }
    assert should_continue(retry_state) == "reason"

    # 3. Invalid code with budget exhausted -> finalize
    exhausted_state: AgentState = {
        "prompt": "T",
        "language": "python",
        "code": "bad",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 5,
        "max_iterations": 5,
        "completed": False,
        "error": "SyntaxError",
    }
    assert should_continue(exhausted_state) == "finalize"


@pytest.mark.graph
def test_graph_end_to_end_execution() -> None:
    """Verify full LangGraph execution from start to finish."""
    graph = create_agent_graph()
    initial_state = {
        "prompt": "Write a factorial function in python",
        "language": "python",
        "code": "",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 0,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    final_state = graph.invoke(initial_state)
    assert final_state["completed"] is True
    assert final_state["is_valid"] is True
    assert final_state["iterations"] == 1
    assert "Factorial(5): 120" in final_state["output"]
    assert len(final_state["steps"]) >= 4


@pytest.mark.graph
def test_graph_self_healing_recovery_loop() -> None:
    """Verify graph detects syntax error, loops back, self-heals, and succeeds."""
    graph = create_agent_graph()
    initial_state = {
        "prompt": "simulate_syntax_error and calculate sum",
        "language": "python",
        "code": "",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 0,
        "max_iterations": 5,
        "completed": False,
        "error": None,
    }
    final_state = graph.invoke(initial_state)
    assert final_state["completed"] is True
    assert final_state["is_valid"] is True
    assert final_state["iterations"] == 2
    assert "Total: 30" in final_state["output"]


@pytest.mark.graph
def test_graph_max_iterations_exhaustion() -> None:
    """Verify graph terminates when max_iterations is reached without infinite recursion."""
    # Mock LLM that always returns broken code
    mock_llm = DeterministicMockLLM(
        custom_generator=lambda prompt, iter_num, err: ("Always broken", "def bad_syntax(:\n")
    )
    graph = create_agent_graph(llm=mock_llm)

    initial_state = {
        "prompt": "Unfixable task",
        "language": "python",
        "code": "",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 0,
        "max_iterations": 3,
        "completed": False,
        "error": None,
    }
    final_state = graph.invoke(initial_state)
    assert final_state["completed"] is True
    assert final_state["is_valid"] is False
    assert final_state["iterations"] == 3
