"""Health and readiness probe router."""

from fastapi import APIRouter, Depends, status
from app.config import Settings, get_settings
from app.database import check_database_health
from app.models import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    """Basic liveness probe confirming server process is running."""
    return {
        "status": "live",
        "service": "human-in-the-loop-approval-agent",
    }


@router.get("/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def readiness(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Readiness probe validating database connectivity and WAL mode."""
    db_health = await check_database_health(settings.database_path)
    return HealthResponse(
        status="ready" if db_health.get("status") == "connected" else "degraded",
        database=db_health,
        environment=settings.environment,
        version="0.1.0",
    )
