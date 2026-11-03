"""Health check endpoints for container readiness and liveness."""

from fastapi import APIRouter
from app.config import get_settings
from app.database import get_db_connection

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def readiness() -> dict[str, str]:
    settings = get_settings()
    try:
        conn = get_db_connection(settings.database_path)
        conn.execute("SELECT 1;").fetchone()
        conn.close()
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}
