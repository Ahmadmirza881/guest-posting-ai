"""Website Crawler / HTTP Fetcher Module (Step 12).

Provides safe, bounded, asynchronous, single-page HTTP fetching for candidate website URLs.

CRITICAL CONSTRAINTS:
- Single-page fetch ONLY (no recursive link following).
- Strictly bounded by timeout, maximum response size, and redirect limits.
- SSRF / private IP range protection.
- NO guest-post detection or keyword classification (belongs to Step 13).
- NO submission extraction (belongs to Step 14).
- NO AI/LLM analysis (belongs to Step 15/16).
"""

import html as html_lib
import ipaddress
import logging
import re
import socket
import time
from typing import Optional
from urllib.parse import urlsplit
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.models.website import Website
from app.utils.cache import app_cache, generate_cache_key
from app.utils.rate_limiter import get_http_limiter
from app.utils.retry import execute_with_retry, is_transient_status_code

logger = logging.getLogger(__name__)

# Blocked hostnames for SSRF protection
BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "metadata.google.internal",
    "169.254.169.254",  # AWS/GCP instance metadata
    "instance-data",
}

BLOCKED_HOSTNAME_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
    ".lan",
    ".home",
    ".corp",
    ".intranet",
)


class CrawlResult(BaseModel):
    """Structured result of a single-page website crawl."""
    original_url: str
    final_url: Optional[str] = None
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    response_time_ms: Optional[float] = None
    title: Optional[str] = None
    html: Optional[str] = None
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class CrawlerError(Exception):
    """Base exception for crawler failures."""
    pass


class RestrictedAddressError(CrawlerError):
    """Raised when target URL points to a private, loopback, or cloud metadata address."""
    pass


class OversizedResponseError(CrawlerError):
    """Raised when target HTTP response exceeds the configured maximum byte limit."""
    pass


def is_private_or_restricted_ip(ip_str: str) -> bool:
    """Check if an IP string belongs to private, loopback, link-local, or reserved ranges."""
    clean_ip = ip_str.strip("[]")
    try:
        ip = ipaddress.ip_address(clean_ip)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        )
    except ValueError:
        return False


def validate_target_url_safety(url: str) -> tuple[bool, Optional[str]]:
    """Validate that the target URL uses http/https and does not resolve to private/local destinations.

    Args:
        url: Candidate URL to inspect.

    Returns:
        tuple of (is_safe, error_reason)
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid."

    url_clean = url.strip()
    if len(url_clean) > 2048:
        return False, "URL length exceeds maximum limit (2048 characters)."

    try:
        parsed = urlsplit(url_clean)
    except Exception as e:
        return False, f"Failed to parse URL: {str(e)}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Unsupported scheme '{scheme}'. Only http and https are allowed."

    raw_hostname = (parsed.hostname or "").lower().rstrip(".")
    if not raw_hostname:
        return False, "URL missing valid hostname."

    clean_hostname = raw_hostname.strip("[]")

    # Direct blocked hostname check
    if (
        raw_hostname in BLOCKED_HOSTNAMES
        or clean_hostname in BLOCKED_HOSTNAMES
        or any(clean_hostname.endswith(sfx) for sfx in BLOCKED_HOSTNAME_SUFFIXES)
    ):
        return False, f"Target host '{raw_hostname}' is a restricted local or internal address."

    # Direct IP address check (IPv4 and IPv6)
    if is_private_or_restricted_ip(clean_hostname):
        return False, f"Target IP '{raw_hostname}' belongs to a private or restricted network range."

    return True, None


def extract_html_title(html_text: str) -> Optional[str]:
    """Extract document title from raw HTML using lightweight regex."""
    if not html_text:
        return None
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if match:
        raw_title = match.group(1).strip()
        # Clean whitespace and decode HTML entities
        clean_title = re.sub(r"\s+", " ", raw_title)
        return html_lib.unescape(clean_title)
    return None


async def crawl_url(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: Optional[float] = None,
    max_bytes: Optional[int] = None,
    max_redirects: Optional[int] = None
) -> CrawlResult:
    """Fetch web content for a single candidate URL.

    Enforces:
    - In-memory TTL caching (Step 24).
    - Centralized rate limiting / concurrency limits (Step 24).
    - Exponential backoff retry for transient network/status errors (Step 24).
    - SSRF safety checks.
    - Strict timeout.
    - Response byte limit.
    - Max redirect limit.
    - Non-HTML response handling.
    - No recursive crawling / link extraction.

    Args:
        url: Candidate URL to fetch.
        client: Optional shared httpx.AsyncClient instance.
        timeout: Request timeout in seconds.
        max_bytes: Maximum allowed response payload size in bytes.
        max_redirects: Maximum HTTP redirects to follow.

    Returns:
        Structured CrawlResult object.
    """
    clean_url = (url or "").strip()
    timeout_sec = timeout if timeout is not None else settings.CRAWLER_TIMEOUT_SECONDS
    max_size = max_bytes if max_bytes is not None else settings.CRAWLER_MAX_RESPONSE_BYTES
    max_redir = max_redirects if max_redirects is not None else settings.CRAWLER_MAX_REDIRECTS

    # 1. SSRF and Protocol Safety Validation (permanent fail fast - no retry, no cache)
    is_safe, error_reason = validate_target_url_safety(clean_url)
    if not is_safe:
        return CrawlResult(
            original_url=clean_url,
            success=False,
            error_type="blocked_address",
            error_message=error_reason,
        )

    # 2. Cache Lookup (Step 24)
    cache_key = generate_cache_key("crawler", clean_url)
    cached_result = await app_cache.get(cache_key)
    if cached_result is not None and isinstance(cached_result, CrawlResult):
        logger.debug(f"Cache hit for URL crawl: {clean_url}")
        return cached_result

    headers = {
        "User-Agent": settings.CRAWLER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec),
            follow_redirects=True,
            max_redirects=max_redir,
            headers=headers
        )
        should_close = True

    start_time = time.perf_counter()

    async def _fetch_http_response() -> httpx.Response:
        resp = await client.get(clean_url)
        if resp.status_code in (429, 500, 502, 503, 504):
            raise httpx.HTTPStatusError(
                f"HTTP {resp.status_code}",
                request=resp.request,
                response=resp
            )
        return resp

    try:
        # Execute with Step 24 rate limiting and retry handling
        response = await execute_with_retry(
            _fetch_http_response,
            limiter=get_http_limiter(),
            operation_name=f"HTTP GET {clean_url}",
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        final_url = str(response.url)

        # Validate final redirected URL for SSRF protection
        if final_url != clean_url:
            is_redirect_safe, redirect_reason = validate_target_url_safety(final_url)
            if not is_redirect_safe:
                return CrawlResult(
                    original_url=clean_url,
                    final_url=final_url,
                    response_time_ms=elapsed_ms,
                    success=False,
                    error_type="blocked_address",
                    error_message=f"Redirect destination is blocked: {redirect_reason}",
                )

        status_code = response.status_code
        content_type_header = response.headers.get("content-type", "").lower()

        # Extract base content type
        content_type = content_type_header.split(";")[0].strip() if content_type_header else "unknown"

        # Check response content size
        content_bytes = response.content
        content_len = len(content_bytes)

        if content_len > max_size:
            return CrawlResult(
                original_url=clean_url,
                final_url=final_url,
                status_code=status_code,
                content_type=content_type,
                content_length=content_len,
                response_time_ms=elapsed_ms,
                success=False,
                error_type="response_too_large",
                error_message=f"Response size ({content_len} bytes) exceeded limit of {max_size} bytes."
            )

        # Handle Non-HTML responses (e.g. PDF, Image, JSON)
        is_html = "text/html" in content_type or "application/xhtml" in content_type

        if not is_html:
            res = CrawlResult(
                original_url=clean_url,
                final_url=final_url,
                status_code=status_code,
                content_type=content_type,
                content_length=content_len,
                response_time_ms=elapsed_ms,
                html=None,
                success=(200 <= status_code < 300),
                error_type=None if (200 <= status_code < 300) else "http_error",
                error_message=None if (200 <= status_code < 300) else f"HTTP {status_code}"
            )
            if res.success:
                await app_cache.set(cache_key, res)
            return res

        # Decode HTML safely
        html_text = response.text
        title = extract_html_title(html_text)

        success = 200 <= status_code < 300

        crawl_result = CrawlResult(
            original_url=clean_url,
            final_url=final_url,
            status_code=status_code,
            content_type=content_type,
            content_length=content_len,
            response_time_ms=elapsed_ms,
            title=title,
            html=html_text,
            success=success,
            error_type=None if success else "http_error",
            error_message=None if success else f"Server returned HTTP {status_code}"
        )

        # Save successful crawl in cache
        if success and html_text:
            await app_cache.set(cache_key, crawl_result)

        return crawl_result

    except httpx.HTTPStatusError as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        status_code = e.response.status_code if e.response is not None else None
        logger.warning(f"Crawl HTTP status error for URL {clean_url}: {e}")
        return CrawlResult(
            original_url=clean_url,
            status_code=status_code,
            response_time_ms=elapsed_ms,
            success=False,
            error_type="http_error",
            error_message=f"Server returned HTTP {status_code}"
        )

    except httpx.TimeoutException:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Crawl timeout for URL: {clean_url}")
        return CrawlResult(
            original_url=clean_url,
            response_time_ms=elapsed_ms,
            success=False,
            error_type="timeout",
            error_message=f"Request timed out after {timeout_sec} seconds."
        )

    except httpx.TooManyRedirects:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Too many redirects for URL: {clean_url}")
        return CrawlResult(
            original_url=clean_url,
            response_time_ms=elapsed_ms,
            success=False,
            error_type="too_many_redirects",
            error_message=f"Exceeded maximum allowed redirects ({max_redir})."
        )

    except httpx.NetworkError as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Network connection error for URL {clean_url}: {e}")
        return CrawlResult(
            original_url=clean_url,
            response_time_ms=elapsed_ms,
            success=False,
            error_type="connection_error",
            error_message="Failed to establish network connection with target server."
        )

    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"Unexpected crawl error for URL {clean_url}: {e}")
        return CrawlResult(
            original_url=clean_url,
            response_time_ms=elapsed_ms,
            success=False,
            error_type="crawl_error",
            error_message=f"Crawl failed: {str(e)}"
        )

    finally:
        if should_close:
            await client.aclose()


async def crawl_website_record(
    db: Session,
    website_id: int,
    crawler_client: Optional[httpx.AsyncClient] = None
) -> tuple[Optional[Website], CrawlResult]:
    """Crawl a website candidate record from the database and persist the crawl outcome.

    Args:
        db: SQLAlchemy database session.
        website_id: Database ID of the Website record.
        crawler_client: Optional shared httpx client.

    Returns:
        tuple of (Website entity, CrawlResult)
    """
    website = db.get(Website, website_id)
    if not website:
        return None, CrawlResult(
            original_url="",
            success=False,
            error_type="not_found",
            error_message=f"Website #{website_id} not found in database."
        )

    # Mark as currently crawling
    website.crawl_status = "crawling"
    db.commit()

    # Execute safe HTTP fetch
    crawl_res = await crawl_url(url=website.url, client=crawler_client)

    # Update database record
    website.last_crawled_at = datetime.now(timezone.utc)
    website.http_status = crawl_res.status_code
    website.final_url = crawl_res.final_url
    website.content_type = crawl_res.content_type

    if crawl_res.success:
        website.crawl_status = "success"
        if crawl_res.html:
            website.html_content = crawl_res.html
        if crawl_res.title:
            website.name = crawl_res.title
    else:
        website.crawl_status = "failed"

    db.commit()
    db.refresh(website)

    return website, crawl_res
