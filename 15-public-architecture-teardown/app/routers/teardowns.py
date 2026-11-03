"""API router for published architectural teardowns, benchmarks, and LangGraph assistant."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import build_teardown_agent_graph
from app.agent.state import TeardownAssistantState
from app.config import Settings, get_settings
from app.database import (
    get_benchmarks_sync,
    get_teardown_by_slug_sync,
    get_teardowns_sync,
    search_teardowns_fts_sync,
)
from app.models import (
    AgentQueryRequest,
    AgentQueryResponse,
    BenchmarkMetric,
    RFC7807Error,
    TeardownDeepDive,
    TeardownSearchHit,
)

router = APIRouter(prefix="/teardowns", tags=["Teardowns & Benchmarks"])


@router.get(
    "",
    response_model=list[TeardownDeepDive],
    status_code=status.HTTP_200_OK,
)
async def list_teardowns(
    settings: Settings = Depends(get_settings),
) -> list[TeardownDeepDive]:
    """Retrieves all 3 published architectural deep dives."""
    return get_teardowns_sync(settings.sqlite_db_path)


@router.get(
    "/benchmarks",
    response_model=list[BenchmarkMetric],
    status_code=status.HTTP_200_OK,
)
async def list_benchmarks(
    settings: Settings = Depends(get_settings),
) -> list[BenchmarkMetric]:
    """Retrieves cost-per-task, latency, and resilience benchmarks across all 15 repositories."""
    return get_benchmarks_sync(settings.sqlite_db_path)


@router.get(
    "/search",
    response_model=list[TeardownSearchHit],
    status_code=status.HTTP_200_OK,
)
async def search_teardowns(
    q: str = Query(..., min_length=1, description="FTS5 search term"),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[TeardownSearchHit]:
    """Performs Porter-stemmed BM25 search over published deep-dive content."""
    return search_teardowns_fts_sync(settings.sqlite_db_path, q, limit)


@router.post(
    "/query-agent",
    response_model=AgentQueryResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": RFC7807Error}, 500: {"model": RFC7807Error}},
)
async def query_teardown_agent(
    payload: AgentQueryRequest,
    settings: Settings = Depends(get_settings),
) -> AgentQueryResponse:
    """Queries the interactive LangGraph architectural assistant."""
    query_id = f"qry-{uuid.uuid4().hex[:12]}"
    graph = build_teardown_agent_graph()

    initial_state = TeardownAssistantState(
        query_id=query_id,
        query=payload.query,
        db_path=settings.sqlite_db_path,
    )

    result_state = graph.invoke(initial_state)

    return AgentQueryResponse(
        query_id=query_id,
        query=payload.query,
        answer=result_state["answer"],
        sources=result_state["sources"],
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/{slug}",
    response_model=TeardownDeepDive,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": RFC7807Error}},
)
async def get_teardown_by_slug(
    slug: str,
    settings: Settings = Depends(get_settings),
) -> TeardownDeepDive:
    """Retrieves single published deep dive by unique slug."""
    deep_dive = get_teardown_by_slug_sync(settings.sqlite_db_path, slug)
    if not deep_dive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teardown deep-dive with slug '{slug}' not found.",
        )
    return deep_dive
