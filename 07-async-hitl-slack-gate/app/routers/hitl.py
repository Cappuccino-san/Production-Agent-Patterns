"""HTTP routes for High-Stakes Action Drafting, Slack Webhook Resumption, and FTS5 Audit Search."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import create_draft_graph, create_resume_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import Settings, get_settings
from app.database import (
    get_gate_action_sync,
    search_gate_audits_fts_sync,
)
from app.models import (
    AuditSearchHit,
    GateActionRecord,
    GateStatus,
    HighStakesActionDraft,
    SlackInteractiveWebhook,
)

router = APIRouter(prefix="/hitl", tags=["HITL Slack Gate"])

_draft_graph = None
_resume_graph = None


def get_draft_graph():
    global _draft_graph
    if _draft_graph is None:
        settings = get_settings()
        mock_llm = DeterministicMockLLM()
        _draft_graph = create_draft_graph(settings.database_path, mock_llm, settings.approval_timeout_hours)
    return _draft_graph


def set_draft_graph(graph):
    global _draft_graph
    _draft_graph = graph


def get_resume_graph():
    global _resume_graph
    if _resume_graph is None:
        settings = get_settings()
        mock_llm = DeterministicMockLLM()
        _resume_graph = create_resume_graph(settings.database_path, mock_llm)
    return _resume_graph


def set_resume_graph(graph):
    global _resume_graph
    _resume_graph = graph


@router.post(
    "/draft",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Draft and serialize high-stakes action into SQLite WAL, waiting for human approval",
)
def draft_action(
    draft: HighStakesActionDraft,
    settings: Settings = Depends(get_settings),
    graph=Depends(get_draft_graph),
) -> dict:
    action_id = f"act-{uuid.uuid4().hex[:8]}"

    initial_state = {
        "action_id": action_id,
        "action_type": draft.action_type,
        "description": draft.description,
        "target_system": draft.target_system,
        "risk_score": draft.risk_score,
        "payload": draft.payload,
        "status": GateStatus.DRAFTED,
        "expires_at": "",
        "created_at": "",
        "updated_at": "",
        "approver_id": None,
        "decision": None,
        "decision_reason": None,
        "execution_result": None,
        "slack_blocks": None,
        "audit_trail": [],
    }

    result = graph.invoke(initial_state)

    return {
        "action_id": action_id,
        "status": result["status"],
        "risk_score": result["risk_score"],
        "expires_at": result["expires_at"],
        "slack_blocks": result["slack_blocks"],
    }


@router.post(
    "/slack/webhook",
    response_model=GateActionRecord,
    summary="Slack interactive webhook receiving human approve/reject button interactions",
)
def handle_slack_webhook(
    payload: SlackInteractiveWebhook,
    settings: Settings = Depends(get_settings),
    resume_graph=Depends(get_resume_graph),
) -> GateActionRecord:
    record = get_gate_action_sync(settings.database_path, payload.action_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action '{payload.action_id}' not found.",
        )

    # Atomically claim action lock to prevent concurrent double-approvals
    from app.database import claim_gate_action_sync
    claimed = claim_gate_action_sync(settings.database_path, payload.action_id)
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Action '{payload.action_id}' is already finalized in status '{record.status.value}'.",
        )

    # Check 3-day SLA expiration window
    expires_dt = datetime.fromisoformat(record.expires_at)
    now_dt = datetime.now(timezone.utc)
    decision = payload.decision
    if now_dt > expires_dt:
        decision = "timeout"

    resume_state = {
        "action_id": record.action_id,
        "action_type": record.action_type,
        "description": record.description,
        "target_system": record.payload.get("target_system", "production"),
        "risk_score": record.risk_score,
        "payload": record.payload,
        "status": record.status,
        "expires_at": record.expires_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "approver_id": payload.user_id,
        "decision": decision,
        "decision_reason": payload.reason or ("3-day SLA expired" if decision == "timeout" else f"Decision by {payload.user_id}"),
        "execution_result": None,
        "slack_blocks": None,
        "audit_trail": [],
    }

    result = resume_graph.invoke(resume_state)

    updated_record = get_gate_action_sync(settings.database_path, payload.action_id)
    return updated_record


@router.get(
    "/actions/{action_id}",
    response_model=GateActionRecord,
    summary="Query serialized action status, expiration, and audit result",
)
def get_action(
    action_id: str,
    settings: Settings = Depends(get_settings),
) -> GateActionRecord:
    record = get_gate_action_sync(settings.database_path, action_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action '{action_id}' not found.",
        )
    return record


@router.get(
    "/search",
    response_model=list[AuditSearchHit],
    summary="Full-text BM25 search across HITL audit log notes via SQLite FTS5",
)
def search_audits(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[AuditSearchHit]:
    return search_gate_audits_fts_sync(settings.database_path, q, limit)
