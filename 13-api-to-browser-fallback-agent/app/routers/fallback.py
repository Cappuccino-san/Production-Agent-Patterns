"""API router for executing workflows with API-to-Browser Fallback routing."""

import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import build_fallback_graph
from app.agent.state import FallbackState
from app.config import Settings, get_settings
from app.database import get_execution_sync, save_execution_sync, search_executions_fts_sync
from app.models import (
    FallbackSearchHit,
    RFC7807Error,
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
)

router = APIRouter(prefix="/fallback", tags=["Fallback Execution"])


@router.post(
    "/execute",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": RFC7807Error}, 500: {"model": RFC7807Error}},
)
async def execute_workflow(
    payload: WorkflowExecutionRequest,
    settings: Settings = Depends(get_settings),
) -> WorkflowExecutionResponse:
    """Executes a workflow attempting direct REST API call, automatically falling back to headless browser on error."""
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"
    graph = build_fallback_graph()

    initial_state = FallbackState(
        execution_id=execution_id,
        action=payload.action,
        target_id=payload.target_id,
        api_endpoint=payload.api_endpoint,
        gui_url=payload.gui_url,
        simulate_api_failure=payload.simulate_api_failure,
        simulated_failure_type=payload.simulated_failure_type,
        start_time_epoch=time.time(),
    )

    result_state = graph.invoke(initial_state)

    response = WorkflowExecutionResponse(
        execution_id=execution_id,
        action=payload.action,
        target_id=payload.target_id,
        execution_channel=result_state["execution_channel"],
        status=result_state["status"],
        api_status_code=result_state.get("api_status_code"),
        api_error_detail=result_state.get("api_error_detail"),
        fallback_triggered=result_state["fallback_triggered"],
        browser_session_id=result_state.get("browser_session_id"),
        extracted_data=result_state["extracted_data"],
        latency_ms=result_state["latency_ms"],
        logs=result_state["logs"],
    )

    save_execution_sync(settings.sqlite_db_path, response)
    return response


@router.get(
    "/search",
    response_model=list[FallbackSearchHit],
    status_code=status.HTTP_200_OK,
)
async def search_executions(
    q: str = Query(..., min_length=1, description="FTS5 query search term"),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[FallbackSearchHit]:
    """Performs Porter-stemmed BM25 search over past fallback execution records."""
    return search_executions_fts_sync(settings.sqlite_db_path, q, limit)


@router.get(
    "/{execution_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": RFC7807Error}},
)
async def get_execution_details(
    execution_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Retrieves full execution record and sequential audit log trail."""
    record = get_execution_sync(settings.sqlite_db_path, execution_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution record '{execution_id}' not found.",
        )
    return record
