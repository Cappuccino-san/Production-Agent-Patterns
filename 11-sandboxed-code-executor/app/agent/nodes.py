"""Node implementations for Code-Interpreter agent and sandbox execution."""

from typing import Any
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import CodeInterpreterState
from app.database import save_execution_result_sync
from app.models import ExecutionStatus
from app.sandbox import execute_in_sandbox, validate_ast_security


class CodeInterpreterExecutor:
    def __init__(self, db_path: str, mock_llm: DeterministicMockLLM) -> None:
        self.db_path = db_path
        self.mock_llm = mock_llm

    def generate_code_node(self, state: CodeInterpreterState) -> dict[str, Any]:
        prompt = state["task_prompt"]
        code = self.mock_llm.generate_code_for_task(prompt)
        return {
            "generated_code": code,
            "audit_trail": [{"event": "CODE_SYNTHESIZED", "length": len(code)}],
        }

    def ast_gate_node(self, state: CodeInterpreterState) -> dict[str, Any]:
        code = state["generated_code"]
        violations = validate_ast_security(code)
        return {
            "ast_violations": violations,
            "audit_trail": [{"event": "AST_GATED", "violations_count": len(violations)}],
        }

    def execute_node(self, state: CodeInterpreterState) -> dict[str, Any]:
        code = state["generated_code"]
        timeout = state.get("timeout_seconds", 5.0)

        result = execute_in_sandbox(code, timeout_seconds=timeout)

        # Persist to SQLite WAL
        save_execution_result_sync(self.db_path, code, result)

        if result.status == ExecutionStatus.SUCCESS:
            final = f"Execution Succeeded:\n{result.stdout.strip()}"
        else:
            final = f"Execution Failed ({result.status.value}):\n{result.stderr.strip()}"

        return {
            "execution_result": result,
            "final_answer": final,
            "audit_trail": [{
                "event": "SANDBOX_EXECUTED",
                "status": result.status.value,
                "latency_ms": result.execution_time_ms,
            }],
        }
