"""RAG query and FTS5 search endpoints."""

from fastapi import APIRouter, Depends, Query, status

from app.agent.graph import arun_rag_agent
from app.config import Settings, get_settings
from app.database import search_documents
from app.models import (
    RAGQueryRequest,
    RAGQueryResponse,
    RetrievedChunk,
    SearchQueryRequest,
    SearchQueryResponse,
)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute complete LangGraph RAG reasoning workflow",
)
async def execute_rag_query(
    request: RAGQueryRequest,
    settings: Settings = Depends(get_settings),
) -> RAGQueryResponse:
    """Execute LangGraph RAG agent: decompose, retrieve via FTS5, grade, reformulate, and synthesize."""
    state = await arun_rag_agent(
        query=request.query,
        db_path=settings.database_path,
        top_k=request.top_k,
        threshold=request.threshold,
        max_iterations=request.max_iterations,
        enable_decomposition=request.enable_decomposition,
    )

    retrieved = [
        RetrievedChunk(
            id=d["id"],
            title=d["title"],
            content=d["content"],
            snippet=d.get("snippet", ""),
            score=d.get("score", 0.0),
            metadata=d.get("metadata", {}),
        )
        for d in state.get("retrieved_docs", [])
    ]

    return RAGQueryResponse(
        query=state.get("query", request.query),
        subqueries=state.get("subqueries", []),
        retrieved_docs=retrieved,
        is_relevant=state.get("is_relevant", True),
        answer=state.get("answer", ""),
        citations=state.get("citations", []),
        iterations=state.get("iterations", 1),
        completed=state.get("completed", True),
    )


@router.get(
    "/search",
    response_model=SearchQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute direct ranked FTS5 BM25 search",
)
async def direct_fts5_search(
    q: str = Query(..., min_length=1, description="Search terms for FTS5 full-text match"),
    limit: int = Query(default=10, ge=1, le=100),
    threshold: float = Query(default=0.0),
    settings: Settings = Depends(get_settings),
) -> SearchQueryResponse:
    """Directly query the SQLite FTS5 index without running the full agent graph."""
    hits = await search_documents(
        query=q,
        limit=limit,
        threshold=threshold,
        db_path=settings.database_path,
    )

    chunks = [
        RetrievedChunk(
            id=h["id"],
            title=h["title"],
            content=h["content"],
            snippet=h.get("snippet", ""),
            score=h.get("score", 0.0),
            metadata=h.get("metadata", {}),
        )
        for h in hits
    ]

    return SearchQueryResponse(
        query=q,
        total_results=len(chunks),
        results=chunks,
    )


@router.post(
    "/search",
    response_model=SearchQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Direct FTS5 search (POST)",
)
async def direct_fts5_search_post(
    req: SearchQueryRequest,
    settings: Settings = Depends(get_settings),
) -> SearchQueryResponse:
    """POST endpoint for direct FTS5 query."""
    hits = await search_documents(
        query=req.query,
        limit=req.limit,
        threshold=req.threshold,
        db_path=settings.database_path,
    )

    chunks = [
        RetrievedChunk(
            id=h["id"],
            title=h["title"],
            content=h["content"],
            snippet=h.get("snippet", ""),
            score=h.get("score", 0.0),
            metadata=h.get("metadata", {}),
        )
        for h in hits
    ]

    return SearchQueryResponse(
        query=req.query,
        total_results=len(chunks),
        results=chunks,
    )
