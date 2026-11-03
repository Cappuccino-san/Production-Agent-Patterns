"""REST API endpoints for CI Trajectory Evaluation, Golden DAG management, and FTS5 search."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import create_eval_graph
from app.config import Settings, get_settings
from app.database import (
    get_eval_run_sync,
    get_golden_dag_sync,
    save_golden_dag_sync,
    search_trajectory_logs_fts_sync,
)
from app.models import (
    EvalRunRequest,
    EvalRunResponse,
    EvalVerdict,
    GoldenDAG,
    TrajectorySearchHit,
)

router = APIRouter(prefix="/ci", tags=["CI Evaluation Gate"])

_eval_graph = None


def get_eval_graph():
    global _eval_graph
    if _eval_graph is None:
        settings = get_settings()
        _eval_graph = create_eval_graph(settings.database_path)
    return _eval_graph


def set_eval_graph(graph):
    global _eval_graph
    _eval_graph = graph


@router.post(
    "/golden-dag",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update a Golden DAG specification",
)
def register_golden_dag(
    dag: GoldenDAG,
    settings: Settings = Depends(get_settings),
) -> dict:
    save_golden_dag_sync(settings.database_path, dag, datetime.now(timezone.utc).isoformat())
    return {"dag_id": dag.dag_id, "status": "REGISTERED", "name": dag.name}


@router.post(
    "/evaluate",
    response_model=EvalRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Replay candidate trajectories against the Golden DAG and emit CI Gate verdict",
)
def evaluate_trajectories(
    request: EvalRunRequest,
    settings: Settings = Depends(get_settings),
    graph=Depends(get_eval_graph),
) -> EvalRunResponse:
    eval_id = f"eval-{uuid.uuid4().hex[:8]}"

    initial_state = {
        "eval_id": eval_id,
        "dag_id": request.dag_id,
        "pr_number": request.pr_number,
        "commit_sha": request.commit_sha,
        "golden_dag": None,
        "trajectories": request.trajectories,
        "total_evaluated": 0,
        "passed_count": 0,
        "failed_count": 0,
        "verdict": EvalVerdict.PASS,
        "fail_on_any_deviation": settings.fail_on_any_deviation,
        "deviations": [],
        "logs": [],
    }

    final_state = graph.invoke(initial_state)

    return EvalRunResponse(
        eval_id=eval_id,
        pr_number=request.pr_number,
        commit_sha=request.commit_sha,
        dag_id=request.dag_id,
        total_evaluated=final_state["total_evaluated"],
        passed_count=final_state["passed_count"],
        failed_count=final_state["failed_count"],
        verdict=final_state["verdict"],
        deviations=final_state.get("deviations", []),
    )


@router.get(
    "/evals/{eval_id}",
    response_model=dict,
    summary="Retrieve evaluation run report and trajectory logs",
)
def get_evaluation(
    eval_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    record = get_eval_run_sync(settings.database_path, eval_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation run '{eval_id}' not found.",
        )
    return record


@router.get(
    "/search",
    response_model=list[TrajectorySearchHit],
    summary="Search trajectory deviation logs via SQLite FTS5 BM25 full-text search",
)
def search_trajectory_logs(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[TrajectorySearchHit]:
    return search_trajectory_logs_fts_sync(settings.database_path, q, limit)
