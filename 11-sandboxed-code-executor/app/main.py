"""FastAPI entrypoint for Sandboxed Code Executor service."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.agent.graph import create_interpreter_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.config import get_settings
from app.database import init_db_sync
from app.models import RFC7807Error
from app.routers.health import router as health_router
from app.routers.sandbox import (
    router as sandbox_router,
    set_agent_graph,
)

logger = logging.getLogger("sandboxed-code-executor")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("Initializing SQLite database with WAL and FTS5 triggers: %s", settings.database_path)
    init_db_sync(settings.database_path)

    mock_llm = DeterministicMockLLM()
    graph = create_interpreter_graph(settings.database_path, mock_llm)
    set_agent_graph(graph)
    logger.info("Code-Interpreter Agent graph compiled.")
    yield


app = FastAPI(
    title="Sandboxed Code Executor Service",
    version="0.1.0",
    description="Code-interpreter agent writing and executing Python in isolated microVM sandbox with zero internet egress.",
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
    err = RFC7807Error(
        type="https://errors.sandbox.dev/validation-error",
        title="Invalid Request Content",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
        instance=str(request.url),
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=err.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    err = RFC7807Error(
        type="https://errors.sandbox.dev/http-error",
        title="HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail),
        instance=str(request.url),
    )
    return JSONResponse(status_code=exc.status_code, content=err.model_dump())


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Server error: %s", exc)
    err = RFC7807Error(
        type="https://errors.sandbox.dev/internal-error",
        title="Internal Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
        instance=str(request.url),
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=err.model_dump())


app.include_router(health_router)
app.include_router(sandbox_router)
