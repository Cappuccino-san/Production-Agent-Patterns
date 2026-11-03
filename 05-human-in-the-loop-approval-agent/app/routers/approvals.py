"""Approval requests API router implementing submit, pending, review, and search endpoints."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import resume_graph_with_decision, submit_action_to_graph
from app.config import Settings, get_settings
from app.database import (
    complete_approval_request,
    create_approval_record,
    get_approval_record,
    list_pending_requests,
    search_audit_log,
    update_approval_decision,
)
from app.models import (
    ActionSubmitRequest,
    ApprovalRequestResponse,
    ApprovalStatus,
    AuditSearchResponse,
    AuditSearchResultItem,
    DecisionResultResponse,
    DecisionSubmitRequest,
    PendingApprovalsListResponse,
)

router = APIRouter(prefix="/approvals", tags=["Approvals"])


def get_agent_graph(request: Request) -> CompiledStateGraph:
    """Dependency retrieving compiled LangGraph agent from application state."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent graph is not initialized",
        )
    return graph


@router.post(
    "/submit",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an action request for execution or approval gate triage",
)
async def submit_action(
    req: ActionSubmitRequest,
    settings: Settings = Depends(get_settings),
    graph: CompiledStateGraph = Depends(get_agent_graph),
) -> ApprovalRequestResponse:
    """Submit an action request.

    Low-risk requests execute immediately and return completed state.
    Medium, High, and Critical risk requests pause at the approval checkpoint.
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    thread_id = f"thread_{uuid.uuid4().hex[:12]}"

    # Execute graph up to interrupt or completion
    graph_res = submit_action_to_graph(
        graph=graph,
        thread_id=thread_id,
        request_id=request_id,
        action_type=req.action_type,
        description=req.description,
        payload=req.payload,
        risk_level=req.risk_override.value if req.risk_override else None,
    )

    state_vals = graph_res["values"]
    status_val = state_vals.get("status", "pending_approval")
    risk_val = state_vals.get("risk_level", "MEDIUM")
    result_val = state_vals.get("result")
    logs = state_vals.get("execution_logs", [])

    # Persist record in SQLite WAL
    db_rec = await create_approval_record(
        thread_id=thread_id,
        action_type=req.action_type,
        risk_level=risk_val,
        description=req.description,
        payload=req.payload,
        status=status_val,
        request_id=request_id,
        decision=state_vals.get("decision"),
        decision_by=state_vals.get("decision_by"),
        decision_reason=state_vals.get("decision_reason"),
        result=result_val,
        execution_logs=logs,
        db_path=settings.database_path,
    )

    checkpoint_info = {
        "thread_id": thread_id,
        "next_nodes": list(graph_res.get("next", ())),
    }

    return ApprovalRequestResponse(
        id=db_rec["id"],
        thread_id=db_rec["thread_id"],
        action_type=db_rec["action_type"],
        risk_level=db_rec["risk_level"],
        description=db_rec["description"],
        payload=db_rec["payload"],
        status=db_rec["status"],
        decision=db_rec.get("decision"),
        decision_reason=db_rec.get("decision_reason"),
        decision_by=db_rec.get("decision_by"),
        result=db_rec.get("result"),
        execution_logs=db_rec.get("execution_logs", []),
        created_at=db_rec["created_at"],
        decided_at=db_rec.get("decided_at"),
        completed_at=db_rec.get("completed_at"),
        checkpoint_state=checkpoint_info,
    )


@router.get(
    "/pending",
    response_model=PendingApprovalsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all requests awaiting human approval",
)
async def get_pending_approvals(
    settings: Settings = Depends(get_settings),
) -> PendingApprovalsListResponse:
    """Retrieve all requests currently paused at the approval checkpoint."""
    records = await list_pending_requests(settings.database_path)
    items = [
        ApprovalRequestResponse(
            id=r["id"],
            thread_id=r["thread_id"],
            action_type=r["action_type"],
            risk_level=r["risk_level"],
            description=r["description"],
            payload=r["payload"],
            status=r["status"],
            decision=r.get("decision"),
            decision_reason=r.get("decision_reason"),
            decision_by=r.get("decision_by"),
            result=r.get("result"),
            execution_logs=r.get("execution_logs", []),
            created_at=r["created_at"],
            decided_at=r.get("decided_at"),
            completed_at=r.get("completed_at"),
        )
        for r in records
    ]
    return PendingApprovalsListResponse(items=items, count=len(items))


@router.get(
    "/search",
    response_model=AuditSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="FTS5 BM25 full-text search across approval audit logs",
)
async def search_approvals(
    q: str = Query(..., min_length=1, description="Search query terms"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results to return"),
    settings: Settings = Depends(get_settings),
) -> AuditSearchResponse:
    """Search audit logs using SQLite FTS5 BM25 ranked full-text search."""
    raw_results = await search_audit_log(q, settings.database_path, limit)
    items = [
        AuditSearchResultItem(
            id=r["id"],
            thread_id=r["thread_id"],
            action_type=r["action_type"],
            risk_level=r["risk_level"],
            description=r["description"],
            status=r["status"],
            decision=r.get("decision"),
            decision_reason=r.get("decision_reason"),
            result=r.get("result"),
            snippet=r.get("snippet"),
            bm25_score=round(float(r.get("bm25_score", 0.0)), 4),
        )
        for r in raw_results
    ]
    return AuditSearchResponse(query=q, count=len(items), results=items)


@router.get(
    "/{id}",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Get approval request details, history, and checkpoint state",
)
async def get_approval_by_id(
    id: str,
    settings: Settings = Depends(get_settings),
    graph: CompiledStateGraph = Depends(get_agent_graph),
) -> ApprovalRequestResponse:
    """Retrieve detailed approval request information by ID."""
    record = await get_approval_record(id, settings.database_path)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{id}' was not found",
        )

    # Check LangGraph thread state if still active
    checkpoint_info: Optional[dict] = None
    try:
        config = {"configurable": {"thread_id": record["thread_id"]}}
        state_snapshot = graph.get_state(config)
        checkpoint_info = {
            "thread_id": record["thread_id"],
            "next_nodes": list(state_snapshot.next),
            "values": {
                k: v for k, v in state_snapshot.values.items()
                if k in ("status", "risk_level", "decision", "result")
            },
        }
    except Exception:
        pass

    return ApprovalRequestResponse(
        id=record["id"],
        thread_id=record["thread_id"],
        action_type=record["action_type"],
        risk_level=record["risk_level"],
        description=record["description"],
        payload=record["payload"],
        status=record["status"],
        decision=record.get("decision"),
        decision_reason=record.get("decision_reason"),
        decision_by=record.get("decision_by"),
        result=record.get("result"),
        execution_logs=record.get("execution_logs", []),
        created_at=record["created_at"],
        decided_at=record.get("decided_at"),
        completed_at=record.get("completed_at"),
        checkpoint_state=checkpoint_info,
    )


@router.post(
    "/{id}/decision",
    response_model=DecisionResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit human review decision (approve, reject, modify) and resume execution",
)
async def submit_decision(
    id: str,
    req: DecisionSubmitRequest,
    settings: Settings = Depends(get_settings),
    graph: CompiledStateGraph = Depends(get_agent_graph),
) -> DecisionResultResponse:
    """Review and render a decision on a pending approval request.

    - APPROVE: Resumes execution and commits the tool action.
    - REJECT: Cancels execution with recorded reviewer rationale.
    - MODIFY: Resumes execution with reviewer-specified modified payload parameters.
    """
    record = await get_approval_record(id, settings.database_path)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{id}' was not found",
        )

    if record["status"] != ApprovalStatus.PENDING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval request '{id}' is already finalized with status '{record['status']}'",
        )

    thread_id = record["thread_id"]

    # 1. Update database record with decision details
    await update_approval_decision(
        request_id=id,
        decision=req.decision.value,
        decision_by=req.decision_by,
        decision_reason=req.decision_reason,
        status=req.decision.value,
        db_path=settings.database_path,
        modified_payload=req.modified_payload,
    )

    # 2. Resume LangGraph thread
    try:
        resume_res = resume_graph_with_decision(
            graph=graph,
            thread_id=thread_id,
            decision=req.decision.value,
            decision_by=req.decision_by,
            decision_reason=req.decision_reason,
            modified_payload=req.modified_payload,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume LangGraph thread: {exc}",
        )

    final_values = resume_res["values"]
    final_status = final_values.get("status", "completed")
    final_result = final_values.get("result")
    final_logs = final_values.get("execution_logs", [])

    # 3. Finalize database record
    await complete_approval_request(
        request_id=id,
        status=final_status,
        result=final_result,
        execution_logs=final_logs,
        db_path=settings.database_path,
    )

    msg = f"Request '{id}' decision '{req.decision.value}' processed. Status: '{final_status}'."

    return DecisionResultResponse(
        request_id=id,
        thread_id=thread_id,
        status=final_status,
        decision=req.decision,
        decision_by=req.decision_by,
        result=final_result,
        message=msg,
    )
