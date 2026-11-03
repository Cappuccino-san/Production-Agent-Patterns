"""FastAPI Routers package."""

from app.routers.health import router as health_router
from app.routers.plans import router as plans_router

__all__ = ["health_router", "plans_router"]
