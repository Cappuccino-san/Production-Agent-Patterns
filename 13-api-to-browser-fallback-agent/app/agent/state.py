"""State definition for API-to-Browser Fallback LangGraph agent."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models import (
    ExecutionChannel,
    ExecutionLogEntry,
    WorkflowActionType,
    WorkflowStatus,
)


class FallbackState(BaseModel):
    execution_id: str
    action: WorkflowActionType = WorkflowActionType.FETCH_INVOICE
    target_id: str
    api_endpoint: str
    gui_url: str
    simulate_api_failure: bool = False
    simulated_failure_type: str = "404"
    execution_channel: ExecutionChannel = ExecutionChannel.API
    status: WorkflowStatus = WorkflowStatus.PENDING
    api_status_code: Optional[int] = None
    api_error_detail: Optional[str] = None
    fallback_triggered: bool = False
    browser_session_id: Optional[str] = None
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    logs: List[ExecutionLogEntry] = Field(default_factory=list)
    start_time_epoch: float = 0.0
    latency_ms: float = 0.0
