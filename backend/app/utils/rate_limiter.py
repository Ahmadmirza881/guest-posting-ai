"""External Service Rate Limiting and Concurrency Guard Module for Step 24.

Manages centralized, shared asyncio.Semaphore instances to protect external services
(Target Websites, Gemini API, Search APIs) from excessive concurrent load.
"""

import asyncio
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class ServiceLimiterManager:
    """Manages shared concurrency limiters for external service operations."""

    def __init__(self):
        self._http_semaphore: Optional[asyncio.Semaphore] = None
        self._ai_semaphore: Optional[asyncio.Semaphore] = None
        self._http_limit: int = settings.MAX_CONCURRENT_HTTP_REQUESTS
        self._ai_limit: int = settings.MAX_CONCURRENT_AI_REQUESTS
        self._active_http_requests: int = 0
        self._active_ai_requests: int = 0
        self._lock = asyncio.Lock()

    def get_http_limit(self) -> int:
        return self._http_limit

    def get_ai_limit(self) -> int:
        return self._ai_limit

    def get_active_http_count(self) -> int:
        return self._active_http_requests

    def get_active_ai_count(self) -> int:
        return self._active_ai_requests

    def get_http_semaphore(self) -> asyncio.Semaphore:
        """Get or lazily initialize the shared HTTP request semaphore."""
        if self._http_semaphore is None:
            self._http_semaphore = asyncio.Semaphore(self._http_limit)
        return self._http_semaphore

    def get_ai_semaphore(self) -> asyncio.Semaphore:
        """Get or lazily initialize the shared AI request semaphore."""
        if self._ai_semaphore is None:
            self._ai_semaphore = asyncio.Semaphore(self._ai_limit)
        return self._ai_semaphore

    def reset_limiters(
        self,
        http_limit: Optional[int] = None,
        ai_limit: Optional[int] = None,
    ) -> None:
        """Re-initialize semaphores with updated concurrency limits (useful in testing)."""
        if http_limit is not None:
            self._http_limit = max(1, http_limit)
        else:
            self._http_limit = settings.MAX_CONCURRENT_HTTP_REQUESTS

        if ai_limit is not None:
            self._ai_limit = max(1, ai_limit)
        else:
            self._ai_limit = settings.MAX_CONCURRENT_AI_REQUESTS

        self._http_semaphore = asyncio.Semaphore(self._http_limit)
        self._ai_semaphore = asyncio.Semaphore(self._ai_limit)
        self._active_http_requests = 0
        self._active_ai_requests = 0


# Global singleton instance
service_limiters = ServiceLimiterManager()


def get_http_limiter() -> asyncio.Semaphore:
    """Convenience getter for global HTTP concurrency semaphore."""
    return service_limiters.get_http_semaphore()


def get_ai_limiter() -> asyncio.Semaphore:
    """Convenience getter for global AI concurrency semaphore."""
    return service_limiters.get_ai_semaphore()


def reset_service_limiters(
    http_limit: Optional[int] = None,
    ai_limit: Optional[int] = None,
) -> None:
    """Convenience function to reset global service limiters."""
    service_limiters.reset_limiters(http_limit=http_limit, ai_limit=ai_limit)
