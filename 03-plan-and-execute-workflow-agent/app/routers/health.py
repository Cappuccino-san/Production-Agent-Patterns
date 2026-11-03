"""Health and readiness probe endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from app import __version__
from app.config import Settings, get_settings
from app.database import get_db_connection
from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness probe")
async def liveness_probe() -> dict[str, str]:
    """Kubernetes / Docker liveness probe confirming process is responsive."""
    return {"status": "alive"}


@router.get("/health/ready", summary="Readiness probe")
async def readiness_probe(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Readiness probe verifying database connectivity."""
    try:
        async with get_db_connection(settings.database_path) as conn:
            async with conn.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                if not row or row[0] != 1:
                    raise ValueError("Database returned unexpected response")
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connectivity check failed: {exc}",
        ) from exc


@router.get("/health", response_model=HealthResponse, summary="Detailed health status")
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Consolidated health report including database status and environment."""
    db_status = "connected"
    try:
        async with get_db_connection(settings.database_path) as conn:
            async with conn.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                if not row or row[0] != 1:
                    db_status = "degraded"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        version=__version__,
        database=db_status,
        environment=settings.environment,
    )
