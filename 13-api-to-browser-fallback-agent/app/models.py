"""Pydantic v2 domain schemas for API-to-Browser Fallback Agent."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ExecutionChannel(str, Enum):
    API = "API"
    BROWSER_FALLBACK = "BROWSER_FALLBACK"


class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED_VIA_API = "COMPLETED_VIA_API"
    COMPLETED_VIA_BROWSER_FALLBACK = "COMPLETED_VIA_BROWSER_FALLBACK"
    FAILED = "FAILED"


class WorkflowActionType(str, Enum):
    FETCH_INVOICE = "FETCH_INVOICE"
    EXTRACT_METRICS = "EXTRACT_METRICS"
    EXPORT_REPORT = "EXPORT_REPORT"


class ExecutionLogEntry(BaseModel):
    log_id: str
    execution_id: str
    channel: ExecutionChannel
    step_name: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkflowExecutionRequest(BaseModel):
    action: WorkflowActionType = Field(default=WorkflowActionType.FETCH_INVOICE)
    target_id: str = Field(..., min_length=2, max_length=100, description="Resource identifier like INV-2026-001")
    api_endpoint: str = Field(default="https://api.internal.service/v1/invoices")
    gui_url: str = Field(default="https://portal.internal.service/dashboard/invoices")
    simulate_api_failure: bool = Field(default=False)
    simulated_failure_type: str = Field(default="404", description="404, timeout, or 500")


class WorkflowExecutionResponse(BaseModel):
    execution_id: str
    action: WorkflowActionType
    target_id: str
    execution_channel: ExecutionChannel
    status: WorkflowStatus
    api_status_code: Optional[int] = None
    api_error_detail: Optional[str] = None
    fallback_triggered: bool = False
    browser_session_id: Optional[str] = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    logs: list[ExecutionLogEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FallbackSearchHit(BaseModel):
    record_id: str
    execution_id: str
    action: str
    execution_channel: str
    status: str
    snippet: str
    rank: float


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
