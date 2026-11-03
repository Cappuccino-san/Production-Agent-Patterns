"""State definition for Cost-Budgeted LangGraph agent."""

from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models import CostLedgerEntry, CostStatus


class CostAgentState(BaseModel):
    request_id: str
    prompt: str
    force_spend_spike: bool = False
    max_iterations: int = 5
    current_step: int = 0
    current_model: str = "gpt-4o"
    current_spend_usd: float = 0.0
    total_tokens: int = 0
    kill_switch_triggered: bool = False
    fallback_engaged: bool = False
    status: CostStatus = CostStatus.ACTIVE
    final_output: str = ""
    ledger: List[CostLedgerEntry] = Field(default_factory=list)
