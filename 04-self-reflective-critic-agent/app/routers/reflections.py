"""REST API endpoints for the Reflexion Actor-Critic Agent."""

import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agent.graph import create_reflection_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import AgentState
from app.config import Settings, get_settings
from app.database import (
    create_session,
    get_session,
    list_sessions,
    search_reflections,
)
from app.models import (
    ReflectionExecuteRequest,
    ReflectionExecuteResponse,
    ReflectionStep,
    SearchResultItem,
    SearchReflectionsResponse,
    SessionDetailResponse,
    StandaloneEvaluateRequest,
    StandaloneEvaluateResponse,
)

router = APIRouter(prefix="/api/v1/reflections", tags=["Reflections"])


def get_llm_engine() -> DeterministicMockLLM:
    """Dependency injection provider for the deterministic mock LLM."""
    return DeterministicMockLLM()


@router.post(
    "/execute",
    response_model=ReflectionExecuteResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute full Reflexion Actor-Critic iteration loop",
)
async def execute_reflection_endpoint(
    payload: ReflectionExecuteRequest,
    settings: Settings = Depends(get_settings),
    llm: DeterministicMockLLM = Depends(get_llm_engine),
) -> ReflectionExecuteResponse:
    """Run iterative refinement loop: draft generation, critique evaluation, and reflection."""
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    rubric_json = (
        json.dumps([c.model_dump() for c in payload.custom_rubric])
        if payload.custom_rubric
        else None
    )

    # Initialize persistent session in SQLite WAL
    await create_session(
        task=payload.task,
        threshold=payload.threshold,
        rubric=rubric_json,
        session_id=session_id,
        db_path=settings.database_path,
    )

    # Prepare LangGraph state
    initial_state: AgentState = {
        "session_id": session_id,
        "task": payload.task,
        "threshold": payload.threshold,
        "max_iterations": payload.max_iterations,
        "iteration": 0,
        "current_draft": "",
        "critique": "",
        "defects": [],
        "suggestions": [],
        "rubric_scores": {},
        "composite_score": 0.0,
        "passed": False,
        "status": "in_progress",
        "custom_rubric": [c.model_dump() for c in payload.custom_rubric]
        if payload.custom_rubric
        else None,
        "history": [],
        "db_path": settings.database_path,
        "seed": payload.seed,
    }

    # Execute StateGraph
    graph = create_reflection_graph(llm)
    final_state = graph.invoke(initial_state)

    history_steps = [
        ReflectionStep.model_validate(step) for step in final_state.get("history", [])
    ]

    return ReflectionExecuteResponse(
        session_id=session_id,
        task=payload.task,
        status=final_state.get("status", "completed"),
        iterations_count=len(history_steps),
        final_score=final_state.get("composite_score", 0.0),
        final_draft=final_state.get("current_draft", ""),
        history=history_steps,
    )


@router.post(
    "/evaluate",
    response_model=StandaloneEvaluateResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate candidate text against multi-criteria rubric without running graph",
)
async def evaluate_candidate_endpoint(
    payload: StandaloneEvaluateRequest,
    llm: DeterministicMockLLM = Depends(get_llm_engine),
) -> StandaloneEvaluateResponse:
    """Directly evaluate candidate text or code against scoring rubric."""
    eval_result = llm.evaluate_draft(
        task=payload.task,
        draft=payload.candidate_text,
        criteria=payload.rubric,
        threshold=payload.threshold,
    )

    return StandaloneEvaluateResponse(
        task=payload.task,
        candidate_text=payload.candidate_text,
        evaluation=eval_result,
    )


@router.get(
    "/search",
    response_model=SearchReflectionsResponse,
    summary="Full-text BM25 search across historical drafts and critiques",
)
async def search_reflections_endpoint(
    q: str = Query(..., min_length=1, max_length=200, description="Full-text query"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
    settings: Settings = Depends(get_settings),
) -> SearchReflectionsResponse:
    """Search drafts, critiques, and rubric scores using SQLite FTS5 BM25 ranking."""
    raw_results = await search_reflections(q, settings.database_path, limit)
    items = [SearchResultItem.model_validate(r) for r in raw_results]

    return SearchReflectionsResponse(
        query=q,
        total_results=len(items),
        results=items,
    )


@router.get(
    "/sessions",
    response_model=list[SessionDetailResponse],
    summary="List recent reflection sessions",
)
async def list_sessions_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    settings: Settings = Depends(get_settings),
) -> list[SessionDetailResponse]:
    """Retrieve recent reflection sessions with their revision history."""
    sessions = await list_sessions(limit, settings.database_path)
    return [SessionDetailResponse.model_validate(s) for s in sessions]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Retrieve session details, revision history, and rubric scores",
)
async def get_session_endpoint(
    session_id: str,
    settings: Settings = Depends(get_settings),
) -> SessionDetailResponse:
    """Fetch session metadata and chronological iteration steps."""
    session_record = await get_session(session_id, settings.database_path)
    if not session_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    return SessionDetailResponse.model_validate(session_record)
