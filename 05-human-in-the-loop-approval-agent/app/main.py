"""FastAPI application initialization with lifespan management and RFC 7807 error handling."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.graph import create_approval_graph
from app.config import get_settings
from app.database import SqliteCheckpointer, init_db
from app.models import ErrorDetail
from app.routers import approvals, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize SQLite WAL database and compile LangGraph agent on startup."""
    settings = get_settings()

    # Initialize SQLite database schemas, WAL pragmas, and FTS5 triggers
    await init_db(settings.database_path)

    # Initialize checkpointer and compile agent graph
    checkpointer = SqliteCheckpointer(settings.database_path)
    graph = create_approval_graph(checkpointer=checkpointer)

    app.state.checkpointer = checkpointer
    app.state.graph = graph

    yield

    # Clean shutdown tasks if necessary
    app.state.graph = None
    app.state.checkpointer = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Human-in-the-Loop Approval Agent",
        description="Production-grade LangGraph approval gate with checkpoint interrupts and SQLite WAL persistence.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register RFC 7807 exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error_detail = ErrorDetail(
            type="https://tools.ietf.org/html/rfc7807#section-3.1",
            title="Request Validation Error",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc.errors()),
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_detail.model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        error_detail = ErrorDetail(
            type="https://tools.ietf.org/html/rfc7807#section-3.1",
            title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            status=exc.status_code,
            detail=str(exc.detail),
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_detail.model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        error_detail = ErrorDetail(
            type="https://tools.ietf.org/html/rfc7807#section-3.1",
            title="Internal Server Error",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(exc)}",
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_detail.model_dump(),
        )

    # Include health and approvals routers
    app.include_router(health.router)
    app.include_router(approvals.router, prefix=settings.api_prefix)

    return app


app = create_app()
