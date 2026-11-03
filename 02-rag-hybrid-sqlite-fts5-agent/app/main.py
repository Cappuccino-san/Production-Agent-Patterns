"""FastAPI application entrypoint with lifespan context manager and RFC 7807 error handlers."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.models import ErrorDetail
from app.routers import documents_router, health_router, rag_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing database initialization and cleanup."""
    settings = get_settings()
    await init_db(settings.database_path)
    yield


app = FastAPI(
    title="RAG Hybrid SQLite FTS5 Agent API",
    version="0.1.0",
    description=(
        "Production-grade microservice for hybrid Retrieval-Augmented Generation (RAG) "
        "featuring query decomposition, SQLite FTS5 BM25 search, relevance grading, "
        "iterative query reformulation, and answer synthesis with citations."
    ),
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(rag_router)


# RFC 7807 Error Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """RFC 7807 compliant HTTP exception handler."""
    problem = ErrorDetail(
        title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail),
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """RFC 7807 compliant validation exception handler."""
    problem = ErrorDetail(
        title="Request Validation Error",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc.errors()),
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """RFC 7807 compliant internal server error handler."""
    problem = ErrorDetail(
        title="Internal Server Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


@app.get("/", tags=["Root"])
async def root_endpoint() -> dict[str, Any]:
    """Root metadata endpoint."""
    return {
        "service": "RAG Hybrid SQLite FTS5 Agent",
        "version": "0.1.0",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_endpoints": {
            "documents": "/api/v1/documents",
            "rag_query": "/api/v1/rag/query",
            "rag_search": "/api/v1/rag/search",
        },
    }
