"""API router for production traffic handling and shadow trajectory diffing."""

import random
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import build_comparator_graph
from app.agent.state import ShadowComparatorState
from app.config import Settings, get_settings
from app.database import (
    get_shadow_comparison_sync,
    list_comparisons_sync,
    save_shadow_comparison_sync,
    save_traffic_request_sync,
    search_comparisons_fts_sync,
)
from app.models import (
    AgentTrafficRequest,
    AgentTrafficResponse,
    ComparatorSearchHit,
    RFC7807Error,
    ShadowComparisonReport,
)

router = APIRouter(prefix="/comparator", tags=["Shadow Comparator"])


@router.post(
    "/execute",
    response_model=AgentTrafficResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": RFC7807Error}, 500: {"model": RFC7807Error}},
)
async def handle_agent_traffic(
    payload: AgentTrafficRequest,
    settings: Settings = Depends(get_settings),
) -> AgentTrafficResponse:
    """Handles production agent request and mirrors 5% traffic to candidate topology in shadow plane."""
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    is_sampled = payload.force_shadow or (random.random() < settings.shadow_sample_rate)

    graph = build_comparator_graph()
    initial_state = ShadowComparatorState(
        request_id=request_id,
        prompt=payload.prompt,
        is_shadow_sampled=is_sampled,
    )

    result_state = graph.invoke(initial_state)

    primary = result_state["primary_trajectory"]
    comparison = result_state.get("comparison_report")

    response = AgentTrafficResponse(
        request_id=request_id,
        prompt=payload.prompt,
        primary_output=primary.final_output,
        primary_cost_usd=primary.cost_usd,
        primary_latency_ms=primary.latency_ms,
        is_shadow_sampled=is_sampled,
        shadow_comparison_id=comparison.comparison_id if comparison else None,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    save_traffic_request_sync(settings.sqlite_db_path, response)

    if comparison:
        save_shadow_comparison_sync(settings.sqlite_db_path, comparison)

    return response


@router.get(
    "/comparisons",
    response_model=list[dict],
    status_code=status.HTTP_200_OK,
)
async def list_shadow_comparisons(
    limit: int = Query(default=20, ge=1, le=100),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """Lists recent shadow trajectory comparison diffs."""
    return list_comparisons_sync(settings.sqlite_db_path, limit)


@router.get(
    "/search",
    response_model=list[ComparatorSearchHit],
    status_code=status.HTTP_200_OK,
)
async def search_shadow_comparisons(
    q: str = Query(..., min_length=1, description="FTS5 query search term"),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[ComparatorSearchHit]:
    """Performs Porter-stemmed BM25 search over shadow trajectory comparisons."""
    return search_comparisons_fts_sync(settings.sqlite_db_path, q, limit)


@router.get(
    "/{comparison_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": RFC7807Error}},
)
async def get_comparison_detail(
    comparison_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Retrieves full diff details and recommendations for a shadow comparison."""
    comp = get_shadow_comparison_sync(settings.sqlite_db_path, comparison_id)
    if not comp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shadow comparison '{comparison_id}' not found.",
        )
    return comp
