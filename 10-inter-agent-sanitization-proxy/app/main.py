"""FastAPI application entrypoint for Inter-Agent Sanitization Proxy service."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.agent.graph import create_proxy_graph
from app.config import get_settings
from app.database import init_db_sync
from app.models import RFC7807Error
from app.routers.health import router as health_router
from app.routers.proxy import (
    get_sanitizer,
    router as proxy_router,
    set_proxy_graph,
)

logger = logging.getLogger("inter-agent-sanitization-proxy")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("Initializing SQLite database with WAL and FTS5 triggers: %s", settings.database_path)
    init_db_sync(settings.database_path)

    sanitizer = get_sanitizer(settings)
    graph = create_proxy_graph(settings.database_path, sanitizer)
    set_proxy_graph(graph)
    logger.info("Inter-Agent Sanitization Proxy state machine compiled.")
    yield


app = FastAPI(
    title="Inter-Agent Sanitization Proxy Service",
    version="0.1.0",
    description="Middleware that intercepts messages between agents, stripping malicious instructions to prevent cross-agent prompt injection.",
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
        type="https://errors.proxy.dev/validation-error",
        title="Invalid Request Content",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
        instance=str(request.url),
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=err.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    err = RFC7807Error(
        type="https://errors.proxy.dev/http-error",
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
        type="https://errors.proxy.dev/internal-error",
        title="Internal Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
        instance=str(request.url),
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=err.model_dump())


app.include_router(health_router)
app.include_router(proxy_router)
