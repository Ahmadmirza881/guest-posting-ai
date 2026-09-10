"""Health check routes for Guest Posting AI backend."""

import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service Health Check")
async def health_check():
    """Health check endpoint to verify backend service status (non-blocking)."""
    return {
        "status": "ok",
        "service": "guest-posting-ai-backend"
    }


@router.get("/health/db", summary="Database Health Check")
async def db_health_check(db: Session = Depends(get_db)):
    """Health check endpoint to verify actual database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
            "service": "guest-posting-ai-backend"
        }
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "disconnected",
                "service": "guest-posting-ai-backend",
                "detail": str(e)
            }
        )
