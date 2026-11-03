"""LangGraph TypedDict state definition for the ReAct Prompt-to-Code Agent."""

import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """State tracked across ReAct graph nodes."""

    prompt: str
    language: str
    code: str
    is_valid: bool
    output: Optional[str]
    steps: Annotated[list[str], operator.add]
    iterations: int
    max_iterations: int
    completed: bool
    error: Optional[str]
