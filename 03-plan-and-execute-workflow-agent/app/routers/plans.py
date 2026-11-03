"""REST API routes for Plan-and-Execute workflow operations."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import build_plan_execute_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import PlanExecuteState
from app.config import Settings, get_settings
from app.database import (
    create_plan,
    get_plan,
    list_plans,
    search_steps,
)
from app.models import (
    PlanCreate,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanResponse,
    PlanSearchResult,
    PlanStep,
)

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


def get_llm_engine() -> DeterministicMockLLM:
    """Dependency provider for Mock LLM engine."""
    return DeterministicMockLLM()


@router.post(
    "",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and decompose a goal into a multi-step plan",
)
@router.post(
    "/create",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_plan_endpoint(
    payload: PlanCreate,
    settings: Settings = Depends(get_settings),
    llm: DeterministicMockLLM = Depends(get_llm_engine),
) -> PlanResponse:
    """Deconstruct user objective into an ordered plan and persist to SQLite WAL."""
    generated_steps = llm.generate_plan(payload.goal)
    if not generated_steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to generate plan steps for the provided goal",
        )

    plan_record = await create_plan(payload.goal, generated_steps, settings.database_path)
    return PlanResponse.model_validate(plan_record)


@router.get(
    "/search",
    response_model=list[PlanSearchResult],
    summary="Search step execution logs using SQLite FTS5 BM25 ranking",
)
async def search_plans_endpoint(
    q: str = Query(..., min_length=1, max_length=200, description="Search query string"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results to return"),
    settings: Settings = Depends(get_settings),
) -> list[PlanSearchResult]:
    """Execute FTS5 BM25 ranked full-text query across plan step titles, descriptions, and outputs."""
    raw_results = await search_steps(q, settings.database_path, limit)
    return [PlanSearchResult.model_validate(r) for r in raw_results]


@router.get(
    "",
    response_model=list[PlanResponse],
    summary="List recently created plans",
)
async def list_plans_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    settings: Settings = Depends(get_settings),
) -> list[PlanResponse]:
    """Retrieve recent plans ordered by creation timestamp."""
    plans = await list_plans(limit, settings.database_path)
    return [PlanResponse.model_validate(p) for p in plans]


@router.get(
    "/{plan_id}",
    response_model=PlanResponse,
    summary="Retrieve plan details and step execution history",
)
async def get_plan_endpoint(
    plan_id: str,
    settings: Settings = Depends(get_settings),
) -> PlanResponse:
    """Fetch current execution state, steps, and results for a plan."""
    plan_record = await get_plan(plan_id, settings.database_path)
    if not plan_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found",
        )
    return PlanResponse.model_validate(plan_record)


@router.post(
    "/{plan_id}/execute",
    response_model=PlanExecuteResponse,
    summary="Execute plan steps using LangGraph state graph with adaptive replanning",
)
async def execute_plan_endpoint(
    plan_id: str,
    payload: Optional[PlanExecuteRequest] = None,
    settings: Settings = Depends(get_settings),
    llm: DeterministicMockLLM = Depends(get_llm_engine),
) -> PlanExecuteResponse:
    """Execute plan steps sequentially, dynamically replanning on step failures."""
    plan_record = await get_plan(plan_id, settings.database_path)
    if not plan_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found",
        )

    req = payload or PlanExecuteRequest(plan_id=plan_id)
    max_iters = req.max_iterations or settings.max_iterations

    # Initialize LangGraph state
    initial_state: PlanExecuteState = {
        "goal": plan_record["goal"],
        "plan": plan_record.get("steps", []),
        "current_step_index": plan_record.get("current_step_index", 0),
        "past_steps": [s for s in plan_record.get("steps", []) if s.get("status") == "completed"],
        "response": plan_record.get("final_response"),
        "needs_replan": False,
        "completed": False,
        "iterations": 0,
        "max_iterations": max_iters,
        "replan_count": 0,
        "allow_replanning": req.allow_replanning,
        "plan_id": plan_id,
        "db_path": settings.database_path,
        "error": None,
    }

    graph = build_plan_execute_graph(llm)
    final_state = graph.invoke(initial_state)

    # Reload fresh state from database
    updated_plan = await get_plan(plan_id, settings.database_path)
    if not updated_plan:
        updated_plan = plan_record

    steps_models = [PlanStep.model_validate(s) for s in updated_plan.get("steps", [])]

    return PlanExecuteResponse(
        plan_id=plan_id,
        goal=updated_plan["goal"],
        status=updated_plan["status"],
        completed=final_state.get("completed", False),
        iterations=final_state.get("iterations", 0),
        steps=steps_models,
        response=final_state.get("response") or updated_plan.get("final_response"),
    )
