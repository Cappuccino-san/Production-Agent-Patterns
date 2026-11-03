"""Main FastAPI application for Public Architecture Teardown."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.database import init_db_sync
from app.models import RFC7807Error
from app.routers.health import router as health_router
from app.routers.teardowns import router as teardowns_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db_sync(settings.sqlite_db_path)
    yield


app = FastAPI(
    title="Public Architecture Teardown",
    description="Operations cockpit and published deep dives for 15 production agentic AI architectures.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=RFC7807Error(
            title="HTTP Exception",
            status=exc.status_code,
            detail=str(exc.detail),
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=RFC7807Error(
            title="Validation Error",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


app.include_router(health_router)
app.include_router(teardowns_router)
