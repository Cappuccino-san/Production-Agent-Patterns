"""Health check endpoints for container and Kubernetes liveness/readiness probes."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.database import check_database_health
from app.models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Basic liveness probe verifying HTTP server responsiveness."""
    return {
        "status": "live",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def readiness_probe(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Readiness probe verifying SQLite WAL persistence and database availability."""
    try:
        health = await check_database_health(settings.database_path)
        return HealthResponse(
            status="ready",
            journal_mode=health["journal_mode"],
            database=health["database"],
            document_count=health.get("document_count", 0),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database readiness check failed: {exc}",
        ) from exc


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def overall_health(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Comprehensive service healthcheck endpoint."""
    return await readiness_probe(settings=settings)
