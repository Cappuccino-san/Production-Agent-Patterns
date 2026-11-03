"""Health probe endpoints."""

from fastapi import APIRouter, Depends, status
from app.config import Settings, get_settings
from app.database import check_database_health
from app.models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Kubernetes / Docker liveness probe confirming process responsiveness."""
    return {"status": "live"}


@router.get("/health/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def readiness_probe(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Kubernetes / Docker readiness probe checking DB connectivity and WAL mode."""
    db_health = await check_database_health(settings.database_path)
    return HealthResponse(
        status="healthy",
        environment=settings.environment,
        database=f"connected (journal_mode={db_health['journal_mode']})",
    )


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def general_health(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """General health overview endpoint."""
    db_health = await check_database_health(settings.database_path)
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        database=f"connected (journal_mode={db_health['journal_mode']})",
    )
