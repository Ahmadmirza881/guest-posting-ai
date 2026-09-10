"""API routes package for Guest Posting AI."""

from app.routes.health import router as health_router
from app.routes.searches import router as searches_router
from app.routes.websites import router as websites_router
from app.routes.auth import router as auth_router

__all__ = [
    "health_router",
    "searches_router",
    "websites_router",
    "auth_router",
]
