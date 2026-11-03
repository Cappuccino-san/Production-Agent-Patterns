"""FastAPI Application entrypoint with lifespan context manager and RFC 7807 errors."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.routers import agent, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup (DB init & pragmas) and shutdown teardown."""
    settings = get_settings()
    await init_db(settings.database_path)
    yield


app = FastAPI(
    title="Prompt-to-Code ReAct Agent API",
    description="Production-grade agent generating validated code with AST checking and SQLite WAL+FTS5",
    version="0.1.0",
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


# Global RFC 7807 Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Format HTTP exceptions conforming to RFC 7807 Problem Details."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"urn:agent:error:{exc.status_code}",
            "title": exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            "status": exc.status_code,
            "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "instance": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Format unhandled exceptions conforming to RFC 7807 Problem Details."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "type": "urn:agent:error:internal",
            "title": "Internal Server Error",
            "status": 500,
            "detail": str(exc),
            "instance": str(request.url.path),
        },
    )


# Include Routers
app.include_router(health.router)
app.include_router(agent.router)
