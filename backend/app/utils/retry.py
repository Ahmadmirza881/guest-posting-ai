"""Reusable Retry Mechanism with Exponential Backoff for Step 24.

Handles transient failures (timeouts, network drops, HTTP 429, HTTP 5xx, Gemini rate limits)
while rejecting deterministic errors (400, 401, 403, 404, SSRF blocked, invalid input).

Enforces critical rate limiter interaction:
- Rate limiter is acquired for the request.
- Rate limiter is immediately released upon failure.
- Backoff sleep occurs OUTSIDE the limiter.
- Rate limiter is re-acquired for subsequent retry attempts.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional, TypeVar
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
PERMANENT_HTTP_STATUSES = {400, 401, 403, 404, 405, 410, 422}


def is_transient_status_code(status_code: Optional[int]) -> bool:
    """Check if an HTTP status code indicates a temporary, retryable condition."""
    if status_code is None:
        return False
    return status_code in TRANSIENT_HTTP_STATUSES


def is_transient_exception(exc: Exception) -> bool:
    """Determine whether an exception represents a transient failure eligible for retry.

    Retryable:
    - httpx.TimeoutException (ReadTimeout, ConnectTimeout, etc.)
    - httpx.NetworkError (ConnectError, RemoteProtocolError, etc.)
    - Transient API error messages mentioning 429, 500, 502, 503, 504, or timeout.

    Non-retryable:
    - SSRF / blocked addresses
    - Oversized responses
    - Permanent 4xx HTTP responses (400, 401, 403, 404)
    - Value / Type / Validation errors
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True

    exc_str = str(exc).lower()

    # Check for permanent error signatures (credentials, account verification, blocked URLs, etc.)
    if any(perm in exc_str for perm in [
        "blocked", "restricted", "too large", "oversized", "400", "401", "403", "404",
        "not configured", "verified email", "invalid api key", "configuration error",
        "account needs to have a verified email", "serpapi configuration error",
        "exceeded your current quota", "check your plan and billing", "quota exceeded"
    ]):
        return False

    # Check for transient error signatures
    if any(trans in exc_str for trans in ["429", "500", "502", "503", "504", "timeout", "timed out", "connection reset", "temporarily unavailable", "rate limit"]):
        return True

    return False


async def execute_with_retry(
    coro_fn: Callable[[], Awaitable[T]],
    limiter: Optional[asyncio.Semaphore] = None,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    is_transient_fn: Optional[Callable[[Exception], bool]] = None,
    operation_name: str = "External Request",
    sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
) -> T:
    """Execute an asynchronous operation with retry logic and exponential backoff.

    Args:
        coro_fn: Factory function returning the coroutine to execute.
        limiter: Optional shared asyncio.Semaphore to acquire during the request.
        max_retries: Maximum retry attempts (defaults to settings.MAX_RETRIES).
        base_delay: Base backoff delay in seconds (defaults to settings.RETRY_BASE_DELAY_SECONDS).
        max_delay: Maximum delay cap in seconds (defaults to settings.RETRY_MAX_DELAY_SECONDS).
        is_transient_fn: Custom predicate function to identify retryable exceptions.
        operation_name: Name of the operation for structured logging.
        sleep_fn: Optional custom sleep function for test mocking.

    Returns:
        Result of the coroutine execution upon success.

    Raises:
        The last encountered exception if all retries are exhausted or error is non-retryable.
    """
    retries_limit = max_retries if max_retries is not None else settings.MAX_RETRIES
    b_delay = base_delay if base_delay is not None else settings.RETRY_BASE_DELAY_SECONDS
    m_delay = max_delay if max_delay is not None else settings.RETRY_MAX_DELAY_SECONDS
    checker = is_transient_fn or is_transient_exception
    sleeper = sleep_fn or asyncio.sleep

    last_exception: Optional[Exception] = None

    for attempt in range(retries_limit + 1):
        try:
            if limiter is not None:
                async with limiter:
                    return await coro_fn()
            else:
                return await coro_fn()

        except Exception as e:
            last_exception = e

            # Check if exception is transient and retries remain
            is_transient = checker(e)
            if not is_transient or attempt >= retries_limit:
                if not is_transient:
                    logger.info(
                        f"[{operation_name}] Permanent error encountered on attempt {attempt + 1}: {e}. Not retrying."
                    )
                else:
                    logger.warning(
                        f"[{operation_name}] All {retries_limit} retries exhausted. Final error: {e}"
                    )
                raise e

            # Calculate exponential backoff delay: base_delay * 2^attempt
            backoff_delay = min(m_delay, b_delay * (2 ** attempt))

            logger.warning(
                f"[{operation_name}] Transient error on attempt {attempt + 1}/{retries_limit + 1}: {e}. "
                f"Retrying in {backoff_delay:.2f}s..."
            )

            # NOTE: Backoff sleep happens OUTSIDE the limiter lock so other tasks are not blocked
            await sleeper(backoff_delay)

    # Should not reach here, but if so, raise last exception
    if last_exception:
        raise last_exception
    raise RuntimeError(f"[{operation_name}] Unexpected execution failure.")
