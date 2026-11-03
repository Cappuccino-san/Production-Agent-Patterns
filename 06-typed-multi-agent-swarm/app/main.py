"""FastAPI application entrypoint with lifespan context manager and RFC 7807 exception handlers."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.agent.graph import create_swarm_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync
from app.models import RFC7807Error
from app.routers.health import router as health_router
from app.routers.swarm import router as swarm_router, set_agent_graph

logger = logging.getLogger("typed-multi-agent-swarm")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize SQLite WAL database and compile the LangGraph multi-agent swarm on startup."""
    settings = get_settings()
    logger.info("Initializing SQLite database with WAL and FTS5 triggers: %s", settings.database_path)
    init_db_sync(settings.database_path)

    # Pre-compile the LangGraph state machine with deterministic mock LLM
    mock_llm = DeterministicMockLLM()
    graph = create_swarm_graph(settings.database_path, mock_llm)
    set_agent_graph(graph)
    logger.info("LangGraph swarm state machine compiled successfully.")

    yield

    logger.info("Shutting down Typed Multi-Agent Swarm service.")


app = FastAPI(
    title="Typed Multi-Agent Swarm Service",
    version="0.1.0",
    description="LangGraph state machine where Researcher, Coder, and Reviewer pass strictly typed state objects.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error_payload = RFC7807Error(
        type="https://errors.swarm.dev/validation-error",
        title="Invalid Request Content",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
        instance=str(request.url),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload.model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    error_payload = RFC7807Error(
        type="https://errors.swarm.dev/http-error",
        title="HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail),
        instance=str(request.url),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload.model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error: %s", exc)
    error_payload = RFC7807Error(
        type="https://errors.swarm.dev/internal-error",
        title="Internal Server Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
        instance=str(request.url),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload.model_dump(),
    )


app.include_router(health_router)
app.include_router(swarm_router)
