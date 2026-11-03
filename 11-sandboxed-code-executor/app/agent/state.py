"""Typed LangGraph state for Code-Interpreter Agent."""

from typing import Annotated, Any, Optional, TypedDict
from app.models import ExecutionResult, ExecutionStatus


def merge_audit(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return existing + new_items


class CodeInterpreterState(TypedDict):
    task_prompt: str
    generated_code: str
    timeout_seconds: float
    ast_violations: list[str]
    execution_result: Optional[ExecutionResult]
    final_answer: str
    audit_trail: Annotated[list[dict[str, Any]], merge_audit]
