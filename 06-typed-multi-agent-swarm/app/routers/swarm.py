"""API routes for Swarm Task Dispatch, Status Queries, and Artifact Search."""

import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import create_swarm_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import Settings, get_settings
from app.database import (
    get_swarm_task_sync,
    save_swarm_task_sync,
    search_artifacts_fts_sync,
)
from app.models import (
    ArtifactSearchHit,
    CodeArtifact,
    ResearchFinding,
    ReviewAssessment,
    SwarmStatus,
    SwarmTaskRequest,
    SwarmTaskResponse,
)

router = APIRouter(prefix="/swarm", tags=["Swarm"])

# Module-level agent graph instance
_agent_graph = None


def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        settings = get_settings()
        mock_llm = DeterministicMockLLM()
        _agent_graph = create_swarm_graph(settings.database_path, mock_llm)
    return _agent_graph


def set_agent_graph(graph):
    global _agent_graph
    _agent_graph = graph


@router.post(
    "/dispatch",
    response_model=SwarmTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch a task through the typed multi-agent swarm",
)
def dispatch_task(
    request: SwarmTaskRequest,
    settings: Settings = Depends(get_settings),
    graph=Depends(get_agent_graph),
) -> SwarmTaskResponse:
    start_time = time.perf_counter()
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    # Initial persistent record
    save_swarm_task_sync(
        db_path=settings.database_path,
        task_id=task_id,
        task_description=request.task_description,
        status=SwarmStatus.RESEARCHING,
        iteration=0,
        max_iterations=request.max_iterations,
        created_at=now,
        updated_at=now,
    )

    initial_state = {
        "task_id": task_id,
        "task_description": request.task_description,
        "context": request.context,
        "iteration": 0,
        "max_iterations": request.max_iterations,
        "status": SwarmStatus.RESEARCHING,
        "research_packet": None,
        "code_packet": None,
        "review_packet": None,
        "history": [],
    }

    final_state = graph.invoke(initial_state)

    updated_now = datetime.now(timezone.utc).isoformat()
    save_swarm_task_sync(
        db_path=settings.database_path,
        task_id=task_id,
        task_description=request.task_description,
        status=final_state["status"],
        iteration=final_state["iteration"],
        max_iterations=request.max_iterations,
        created_at=now,
        updated_at=updated_now,
    )

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    return SwarmTaskResponse(
        task_id=task_id,
        task_description=request.task_description,
        status=final_state["status"],
        iteration=final_state["iteration"],
        max_iterations=request.max_iterations,
        research=final_state.get("research_packet"),
        code=final_state.get("code_packet"),
        review=final_state.get("review_packet"),
        history=final_state.get("history", []),
        execution_time_ms=round(duration_ms, 2),
    )


@router.get(
    "/tasks/{task_id}",
    response_model=SwarmTaskResponse,
    summary="Retrieve task status, typed packets, and audit trail",
)
def get_task(
    task_id: str,
    settings: Settings = Depends(get_settings),
) -> SwarmTaskResponse:
    record = get_swarm_task_sync(settings.database_path, task_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    # Reconstruct packets from stored artifacts
    research = None
    code = None
    review = None
    for art in record.get("artifacts", []):
        meta = art.get("metadata_json")
        art_type = art.get("artifact_type")
        import json
        payload = json.loads(meta) if isinstance(meta, str) else meta
        if art_type == "research":
            research = ResearchFinding(**payload)
        elif art_type == "code":
            code = CodeArtifact(**payload)
        elif art_type == "review":
            review = ReviewAssessment(**payload)

    return SwarmTaskResponse(
        task_id=record["task_id"],
        task_description=record["task_description"],
        status=SwarmStatus(record["status"]),
        iteration=record["iteration"],
        max_iterations=record["max_iterations"],
        research=research,
        code=code,
        review=review,
        history=record.get("history", []),
    )


@router.get(
    "/search",
    response_model=list[ArtifactSearchHit],
    summary="Full-text BM25 search across swarm artifacts via SQLite FTS5",
)
def search_artifacts(
    q: str = Query(..., min_length=1, description="BM25 search term"),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[ArtifactSearchHit]:
    return search_artifacts_fts_sync(
        db_path=settings.database_path,
        query=q,
        limit=limit,
    )
