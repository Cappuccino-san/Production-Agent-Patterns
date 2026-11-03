"""FastAPI application entrypoint with lifespan context manager and RFC 7807 error handlers."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.database import init_db
from app.models import ErrorDetail
from app.routers import health_router, plans_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing database initialization and cleanup."""
    settings = get_settings()
    await init_db(settings.database_path)
    yield


app = FastAPI(
    title="Plan-and-Execute Workflow Agent API",
    version=__version__,
    description=(
        "Production-grade microservice implementing the Plan-and-Execute agentic pattern with "
        "dynamic task decomposition, step-by-step tool execution, adaptive replanning, "
        "SQLite WAL persistence, and FTS5 BM25 full-text search."
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
app.include_router(plans_router)


# RFC 7807 Error Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """RFC 7807 compliant HTTP exception handler."""
    problem = ErrorDetail(
        type="https://errors.example.com/http-error",
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
        type="https://errors.example.com/validation-error",
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
        type="https://errors.example.com/internal-error",
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


@app.get("/", summary="Root metadata endpoint")
async def root_endpoint() -> dict[str, Any]:
    """Root metadata discovery endpoint."""
    return {
        "service": "Plan-and-Execute Workflow Agent API",
        "version": __version__,
        "docs_url": "/docs",
        "health_url": "/health",
        "api_prefix": "/api/v1/plans",
    }
