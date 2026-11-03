"""Typed LangGraph state for OpenTelemetry Traced Agent."""

from typing import Annotated, Any, Optional, TypedDict
from app.models import AgentSpan


def merge_spans(existing: list[AgentSpan], new_items: list[AgentSpan]) -> list[AgentSpan]:
    return existing + new_items


class TracedAgentState(TypedDict):
    trace_id: str
    task_prompt: str
    intermediate_thought: str
    tool_output: str
    final_output: str
    total_tokens: int
    spans: Annotated[list[AgentSpan], merge_spans]
