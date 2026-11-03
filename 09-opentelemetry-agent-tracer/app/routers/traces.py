"""API endpoints for executing traced agent workflows and querying telemetry spans."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.graph import create_traced_graph
from app.config import Settings, get_settings
from app.database import (
    get_agent_trace_sync,
    search_agent_spans_fts_sync,
)
from app.models import AgentTrace, SpanSearchHit, TraceRunRequest
from app.tracer import AgentTracer

router = APIRouter(prefix="/traces", tags=["Traces"])

_tracer: AgentTracer = AgentTracer()
_traced_graph = None


def get_tracer() -> AgentTracer:
    return _tracer


def get_traced_graph():
    global _traced_graph
    if _traced_graph is None:
        settings = get_settings()
        _traced_graph = create_traced_graph(settings.database_path, _tracer)
    return _traced_graph


def set_traced_graph(graph):
    global _traced_graph
    _traced_graph = graph


@router.post(
    "/run-agent",
    response_model=AgentTrace,
    status_code=status.HTTP_201_CREATED,
    summary="Execute agent task with full OpenTelemetry span capture across LLM hops, tools, and mutations",
)
def run_traced_agent(
    request: TraceRunRequest,
    settings: Settings = Depends(get_settings),
    tracer: AgentTracer = Depends(get_tracer),
    graph=Depends(get_traced_graph),
) -> AgentTrace:
    # 1. Start root trace
    trace_id = tracer.start_trace(agent_name=request.agent_name, sink=request.destination_sink)

    # 2. Invoke LangGraph with trace context
    initial_state = {
        "trace_id": trace_id,
        "task_prompt": request.prompt,
        "intermediate_thought": "",
        "tool_output": "",
        "final_output": "",
        "total_tokens": 0,
        "spans": [],
    }

    graph.invoke(initial_state)

    trace = get_agent_trace_sync(settings.database_path, trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve persisted telemetry trace.",
        )
    return trace


@router.get(
    "/search",
    response_model=list[SpanSearchHit],
    summary="Search span attributes and state mutations via SQLite FTS5 BM25 search",
)
def search_spans(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> list[SpanSearchHit]:
    return search_agent_spans_fts_sync(settings.database_path, q, limit)


@router.get(
    "/{trace_id}",
    response_model=AgentTrace,
    summary="Retrieve trace waterfall with all LLM hops, token metrics, and tool latencies",
)
def get_trace(
    trace_id: str,
    settings: Settings = Depends(get_settings),
) -> AgentTrace:
    trace = get_agent_trace_sync(settings.database_path, trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace '{trace_id}' not found.",
        )
    return trace
