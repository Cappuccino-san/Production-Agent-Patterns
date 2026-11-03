"""REST API endpoints for proxy message interception and audit searches."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import create_proxy_graph
from app.config import Settings, get_settings
from app.database import (
    get_intercepted_message_sync,
    search_intercepted_messages_fts_sync,
)
from app.models import MessagePacket, ProxySearchHit, SanitizationResult
from app.sanitizer import MessageSanitizer

router = APIRouter(prefix="/proxy", tags=["Proxy"])

_proxy_graph = None
_sanitizer = None


def get_sanitizer(settings: Settings = Depends(get_settings)) -> MessageSanitizer:
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = MessageSanitizer(
            quarantine_threshold=settings.quarantine_threshold_score,
            block_critical=settings.block_critical_injections,
        )
    return _sanitizer


def get_proxy_graph(
    settings: Settings = Depends(get_settings),
    sanitizer: MessageSanitizer = Depends(get_sanitizer),
):
    global _proxy_graph
    if _proxy_graph is None:
        _proxy_graph = create_proxy_graph(settings.database_path, sanitizer)
    return _proxy_graph


def set_proxy_graph(graph):
    global _proxy_graph
    _proxy_graph = graph


@router.post(
    "/send",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Transmit a message between agents through the sanitization proxy middleware",
)
def send_message(
    packet: MessagePacket,
    graph=Depends(get_proxy_graph),
) -> dict:
    initial_state = {
        "message_id": packet.message_id,
        "sender_agent": packet.sender_agent,
        "receiver_agent": packet.receiver_agent,
        "raw_content": packet.content,
        "sanitized_content": "",
        "action_taken": "",
        "risk_score": 0.0,
        "matched_rules": [],
        "delivered": False,
        "audit_trail": [],
    }

    final_state = graph.invoke(initial_state)

    return {
        "message_id": packet.message_id,
        "sender_agent": packet.sender_agent,
        "receiver_agent": packet.receiver_agent,
        "delivered": final_state["delivered"],
        "action_taken": final_state["action_taken"].value,
        "risk_score": final_state["risk_score"],
        "sanitized_content": final_state["sanitized_content"],
        "matched_rules": final_state["matched_rules"],
        "audit_trail": final_state["audit_trail"],
    }


@router.get(
    "/search",
    response_model=list[ProxySearchHit],
    summary="Search intercepted messages and injection attempts via SQLite FTS5 BM25 search",
)
def search_messages(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[ProxySearchHit]:
    return search_intercepted_messages_fts_sync(settings.database_path, q, limit)


@router.get(
    "/messages/{message_id}",
    response_model=dict,
    summary="Retrieve intercepted message audit details",
)
def get_message(
    message_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    record = get_intercepted_message_sync(settings.database_path, message_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found.",
        )
    return record
