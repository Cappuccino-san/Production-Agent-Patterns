"""Tier 2: LangGraph State Machine Code-Interpreter Tests."""

import pytest
from app.agent.graph import create_interpreter_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.models import ExecutionStatus


class TestAgentGraph:
    def test_interpreter_computational_task_success(self, temp_db: str, mock_llm: DeterministicMockLLM):
        graph = create_interpreter_graph(temp_db, mock_llm)

        state = {
            "task_prompt": "Compute the first 10 Fibonacci numbers and print the result",
            "generated_code": "",
            "timeout_seconds": 5.0,
            "ast_violations": [],
            "execution_result": None,
            "final_answer": "",
            "audit_trail": [],
        }

        result = graph.invoke(state)

        assert result["generated_code"] != ""
        assert len(result["ast_violations"]) == 0
        assert result["execution_result"] is not None
        assert result["execution_result"].status == ExecutionStatus.SUCCESS
        assert "Fibonacci(10) = 55" in result["execution_result"].stdout
        assert "Execution Succeeded" in result["final_answer"]

    def test_interpreter_prime_numbers_task(self, temp_db: str, mock_llm: DeterministicMockLLM):
        graph = create_interpreter_graph(temp_db, mock_llm)

        state = {
            "task_prompt": "Find all prime numbers up to 50",
            "generated_code": "",
            "timeout_seconds": 5.0,
            "ast_violations": [],
            "execution_result": None,
            "final_answer": "",
            "audit_trail": [],
        }

        result = graph.invoke(state)
        assert result["execution_result"].status == ExecutionStatus.SUCCESS
        assert "Primes up to 50" in result["execution_result"].stdout
