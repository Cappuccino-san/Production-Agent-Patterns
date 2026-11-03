"""API router for agent execution with Cost Kill-Switch and Model Fallback Middleware."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import build_cost_guard_graph
from app.agent.state import CostAgentState
from app.config import Settings, get_settings
from app.database import get_cost_run_sync, save_cost_run_sync, search_cost_summaries_fts_sync
from app.models import (
    AgentTaskRunRequest,
    AgentTaskRunResponse,
    CostLedgerEntry,
    CostSearchHit,
    CostStatus,
    RFC7807Error,
)
from app.pricing import MODEL_PRICING_PER_1K

router = APIRouter(prefix="/cost", tags=["Cost Control"])


@router.post(
    "/run-agent",
    response_model=AgentTaskRunResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": RFC7807Error}, 500: {"model": RFC7807Error}},
)
async def run_cost_guarded_agent(
    payload: AgentTaskRunRequest,
    settings: Settings = Depends(get_settings),
) -> AgentTaskRunResponse:
    """Executes an agent task with real-time loop depth and $0.50 spend kill switch."""
    request_id = f"cost-{uuid.uuid4().hex[:12]}"
    graph = build_cost_guard_graph()

    initial_state = CostAgentState(
        request_id=request_id,
        prompt=payload.prompt,
        force_spend_spike=payload.force_spend_spike,
        max_iterations=payload.max_iterations,
    )

    result_state = graph.invoke(initial_state)

    response = AgentTaskRunResponse(
        request_id=request_id,
        prompt=payload.prompt,
        initial_model="gpt-4o",
        final_model=result_state["current_model"],
        total_tokens=result_state["total_tokens"],
        total_cost_usd=result_state["current_spend_usd"],
        loop_depth=result_state["current_step"],
        status=result_state["status"],
        kill_switch_triggered=result_state["kill_switch_triggered"],
        fallback_engaged=result_state["fallback_engaged"],
        final_output=result_state["final_output"],
        ledger=result_state["ledger"],
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    save_cost_run_sync(settings.sqlite_db_path, response)
    return response


@router.get(
    "/search",
    response_model=list[CostSearchHit],
    status_code=status.HTTP_200_OK,
)
async def search_cost_runs(
    q: str = Query(..., min_length=1, description="FTS5 query search term"),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[CostSearchHit]:
    """Performs Porter-stemmed BM25 search over cost run records."""
    return search_cost_summaries_fts_sync(settings.sqlite_db_path, q, limit)


@router.get(
    "/pricing-table",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def get_pricing_table() -> dict:
    """Returns token pricing table per 1,000 tokens."""
    return {
        "pricing_per_1k_tokens": MODEL_PRICING_PER_1K,
        "kill_switch_threshold_usd": 0.50,
        "default_fallback_model": "gpt-4o-mini",
    }


@router.get(
    "/{request_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": RFC7807Error}},
)
async def get_cost_ledger(
    request_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Retrieves single cost execution record and its complete step ledger."""
    run = get_cost_run_sync(settings.sqlite_db_path, request_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cost execution record '{request_id}' not found.",
        )
    return run
