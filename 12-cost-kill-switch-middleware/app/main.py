"""Main FastAPI application for Cost Kill-Switch and Model Fallback Middleware."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.database import init_db_sync
from app.models import RFC7807Error
from app.routers.cost import router as cost_router
from app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db_sync(settings.sqlite_db_path)
    yield


app = FastAPI(
    title="Cost Kill-Switch Middleware",
    description="Agentic cost control router monitoring loop depth and projected spend, halting at $0.50 with model fallback.",
    version="1.0.0",
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
app.include_router(cost_router)
