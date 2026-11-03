"""FastAPI API routers package."""

from app.routers.documents import router as documents_router
from app.routers.health import router as health_router
from app.routers.rag import router as rag_router

__all__ = ["documents_router", "health_router", "rag_router"]
