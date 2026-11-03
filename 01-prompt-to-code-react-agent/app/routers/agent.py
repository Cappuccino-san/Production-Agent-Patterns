"""Agent execution and run history API router."""

import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agent.graph import create_agent_graph
from app.config import Settings, get_settings
from app.database import get_run, list_runs, save_run, search_runs
from app.models import AgentRunRequest, AgentRunResponse, RunSearchResult

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


def get_agent_runner() -> Any:
    """Dependency provider for compiled LangGraph agent runner."""
    return create_agent_graph()


@router.post(
    "/run",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Prompt-to-Code ReAct Agent execution",
)
async def run_agent(
    payload: AgentRunRequest,
    settings: Settings = Depends(get_settings),
    graph: Any = Depends(get_agent_runner),
) -> AgentRunResponse:
    """Execute the Prompt-to-Code ReAct loop, validate AST, run sandbox, and record run."""
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    initial_state = {
        "prompt": payload.prompt,
        "language": payload.language,
        "code": "",
        "is_valid": False,
        "output": None,
        "steps": [],
        "iterations": 0,
        "max_iterations": payload.max_iterations,
        "completed": False,
        "error": None,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception:
        # Fallback to sync invoke if async loop environment requires
        final_state = graph.invoke(initial_state)

    run_record = {
        "id": run_id,
        "prompt": payload.prompt,
        "language": payload.language,
        "code": final_state.get("code", ""),
        "is_valid": final_state.get("is_valid", False),
        "output": final_state.get("output"),
        "iterations": final_state.get("iterations", 1),
        "steps": final_state.get("steps", []),
        "status": "completed" if final_state.get("completed") else "failed",
    }

    await save_run(run_record, settings.database_path)
    stored_run = await get_run(run_id, settings.database_path)

    return AgentRunResponse(
        run_id=run_id,
        prompt=payload.prompt,
        language=payload.language,
        code=final_state.get("code", ""),
        is_valid=final_state.get("is_valid", False),
        output=final_state.get("output"),
        iterations=final_state.get("iterations", 1),
        steps=final_state.get("steps", []),
        status=run_record["status"],
        created_at=stored_run.get("created_at") if stored_run else None,
    )


@router.get(
    "/runs",
    response_model=list[AgentRunResponse],
    status_code=status.HTTP_200_OK,
    summary="List recent agent runs",
)
async def get_recent_runs(
    limit: int = Query(default=20, ge=1, le=100),
    settings: Settings = Depends(get_settings),
) -> list[AgentRunResponse]:
    """Retrieve history of agent code generation runs."""
    rows = await list_runs(limit=limit, db_path=settings.database_path)
    return [
        AgentRunResponse(
            run_id=row["id"],
            prompt=row["prompt"],
            language=row["language"],
            code=row["code"],
            is_valid=bool(row["is_valid"]),
            output=row.get("output"),
            iterations=row["iterations"],
            steps=row.get("steps", []),
            status=row["status"],
            created_at=row.get("created_at"),
        )
        for row in rows
    ]


@router.get(
    "/runs/search",
    response_model=list[RunSearchResult],
    status_code=status.HTTP_200_OK,
    summary="Search agent runs using SQLite FTS5 BM25 ranking",
)
async def search_run_history(
    q: str = Query(..., min_length=1, description="Keywords to match in prompt, code, or output"),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[RunSearchResult]:
    """Execute BM25 ranked full-text search against the SQLite FTS5 index."""
    results = await search_runs(query=q, limit=limit, db_path=settings.database_path)
    return [
        RunSearchResult(
            id=item["id"],
            prompt=item["prompt"],
            code=item["code"][:100],
            snippet=item.get("snippet", ""),
            rank=float(item.get("rank", 0.0)),
        )
        for item in results
    ]


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single agent run details by ID",
)
async def get_single_run(
    run_id: str,
    settings: Settings = Depends(get_settings),
) -> AgentRunResponse:
    """Fetch run metadata, steps, code, and execution output for a specific ID."""
    row = await get_run(run_id=run_id, db_path=settings.database_path)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with ID '{run_id}' not found",
        )

    return AgentRunResponse(
        run_id=row["id"],
        prompt=row["prompt"],
        language=row["language"],
        code=row["code"],
        is_valid=bool(row["is_valid"]),
        output=row.get("output"),
        iterations=row["iterations"],
        steps=row.get("steps", []),
        status=row["status"],
        created_at=row.get("created_at"),
    )
