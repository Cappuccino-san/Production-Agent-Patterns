"""Discrete node handlers for ReAct Prompt-to-Code StateGraph."""

import ast
import contextlib
import io
from typing import Any, Optional

from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import AgentState

_DEFAULT_LLM = DeterministicMockLLM()


def reason_node(state: AgentState, llm: Optional[DeterministicMockLLM] = None) -> dict[str, Any]:
    """Reason about the coding objective and synthesize/refactor implementation."""
    engine = llm or _DEFAULT_LLM
    current_iter = state.get("iterations", 0) + 1
    previous_error = state.get("error")

    thought, code = engine.reason_and_generate(
        prompt=state["prompt"],
        iteration=current_iter,
        error=previous_error,
    )

    action_step = f"Action: Synthesized {len(code.splitlines())} lines of {state.get('language', 'python')} code."
    return {
        "code": code,
        "iterations": current_iter,
        "steps": [thought, action_step],
        "error": None,
    }


def validate_ast_node(state: AgentState) -> dict[str, Any]:
    """Validate Python syntax using Abstract Syntax Tree (AST) compilation."""
    code = state.get("code", "")
    language = state.get("language", "python").lower()

    if language != "python":
        # For non-python languages, basic sanity check
        if code.strip():
            return {
                "is_valid": True,
                "error": None,
                "steps": [f"Observation: Non-Python language '{language}' passed basic format verification."],
            }
        return {
            "is_valid": False,
            "error": "Empty code payload",
            "steps": ["Observation: Code payload was empty."],
        }

    try:
        ast.parse(code)
        return {
            "is_valid": True,
            "error": None,
            "steps": ["Observation: AST syntax validation passed with zero errors."],
        }
    except SyntaxError as exc:
        err_msg = f"SyntaxError on line {exc.lineno}: {exc.msg}"
        return {
            "is_valid": False,
            "error": err_msg,
            "steps": [f"Observation: AST validation detected error: {err_msg}."],
        }


def execute_tool_node(state: AgentState) -> dict[str, Any]:
    """Execute validated Python code inside a restricted sandbox and capture stdout."""
    code = state.get("code", "")
    captured_stdout = io.StringIO()

    safe_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bin": bin,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "pow": pow,
        "print": print,
        "range": range,
        "reversed": reversed,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
    }
    sandbox_globals = {"__name__": "__main__", "__builtins__": safe_builtins}

    try:
        with contextlib.redirect_stdout(captured_stdout):
            exec(code, sandbox_globals)  # noqa: S102
        output = captured_stdout.getvalue().strip()
        step_log = f"Action: Executed sandbox runner. Captured stdout: '{output}'"
        return {
            "output": output or "Execution succeeded with no stdout",
            "steps": [step_log],
            "error": None,
        }
    except Exception as exc:
        error_detail = f"RuntimeError during sandbox execution: {exc}"
        return {
            "output": None,
            "error": error_detail,
            "steps": [f"Action: Sandbox execution failed: {error_detail}"],
        }


def finalize_node(state: AgentState) -> dict[str, Any]:
    """Finalize the agent run packaging final code, output, and completion state."""
    is_valid = state.get("is_valid", False)
    output = state.get("output")
    error = state.get("error")

    if not is_valid and not output:
        output = f"Code generation incomplete or invalid. Last error: {error}"

    return {
        "completed": True,
        "output": output,
        "steps": ["Finalize: Packaging completed run deliverables."],
    }
