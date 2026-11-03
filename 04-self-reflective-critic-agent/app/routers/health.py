"""Health and readiness check endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.database import check_database_health
from app.models import LiveResponse, ReadyResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=LiveResponse, summary="Liveness Probe")
async def live() -> LiveResponse:
    """Return liveness probe status indicating application is running."""
    return LiveResponse(status="alive", service="self-reflective-critic-agent")


@router.get("/ready", response_model=ReadyResponse, summary="Readiness Probe")
async def ready(settings: Settings = Depends(get_settings)) -> ReadyResponse:
    """Verify database connectivity, WAL mode, and table operational readiness."""
    try:
        health = await check_database_health(settings.database_path)
        return ReadyResponse(
            status="ready",
            database=health["database"],
            journal_mode=health["journal_mode"],
            sessions_count=health["sessions_count"],
            reflections_count=health["reflections_count"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database readiness check failed: {exc}",
        ) from exc
