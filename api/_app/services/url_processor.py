"""URL Processing, Normalization, Validation, and Deduplication Module (Step 11).

Provides pure, deterministic, network-independent syntactic normalization and deduplication
for candidate website URLs discovered from search engines.

CRITICAL: This module performs NO network requests, NO crawling, and NO HTTP calls.
"""

import logging
import posixpath
from typing import Optional, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pydantic import BaseModel

from app.services.search_provider import CandidateSearchResult

logger = logging.getLogger(__name__)

# Recognized marketing/analytics tracking query parameters to safely strip
TRACKING_QUERY_PARAMS: Set[str] = {
    # Google Analytics & Ads
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "gclsrc",
    "dclid",
    "_ga",
    "_gl",
    # Facebook / Meta
    "fbclid",
    "fbc",
    "fbp",
    # Microsoft / Bing
    "msclkid",
    # Twitter / X
    "twclid",
    # Mailchimp & Email Newsletters
    "mc_cid",
    "mc_eid",
    # HubSpot & Marketo
    "_hsenc",
    "_hsmi",
    "mkt_tok",
    # Generic referral & campaign tags
    "ref",
    "ref_src",
    "source",
    "campaign",
    # Affiliate / Ad tracking
    "aff_id",
    "affiliate_id",
    "yclid",
}

# Supported web URL schemes
SUPPORTED_SCHEMES: Set[str] = {"http", "https"}


class ProcessedURLResult(BaseModel):
    """Result of syntactic URL validation and normalization."""
    original_url: str
    normalized_url: Optional[str] = None
    domain: Optional[str] = None
    hostname: Optional[str] = None
    is_valid: bool = False
    error_reason: Optional[str] = None


def normalize_url(raw_url: Optional[str]) -> ProcessedURLResult:
    """Syntactically validate and normalize a candidate web URL without network requests.

    Normalization policy:
    1. Strips leading and trailing whitespace.
    2. Validates scheme (only http and https are allowed).
    3. Normalizes scheme and hostname to lowercase.
    4. Strips default ports (:80 for http, :443 for https).
    5. Strips client-side URL fragments (#...).
    6. Strips known marketing/tracking query parameters (utm_*, gclid, fbclid, etc.)
       while strictly preserving non-tracking functional query parameters.
    7. Normalizes path segments and applies consistent trailing slash policy
       (root path is '/', subpaths have trailing slashes trimmed).

    Args:
        raw_url: Raw URL string from search results.

    Returns:
        ProcessedURLResult containing is_valid, normalized_url, domain, and error_reason.
    """
    if raw_url is None:
        return ProcessedURLResult(
            original_url="",
            is_valid=False,
            error_reason="URL is None."
        )

    clean_raw = str(raw_url).strip()
    if not clean_raw:
        return ProcessedURLResult(
            original_url=clean_raw,
            is_valid=False,
            error_reason="URL is empty or blank."
        )

    try:
        parsed = urlsplit(clean_raw)
    except Exception as e:
        return ProcessedURLResult(
            original_url=clean_raw,
            is_valid=False,
            error_reason=f"URL parsing syntax error: {str(e)}"
        )

    # 1. Validate Scheme
    scheme = (parsed.scheme or "").lower().strip()
    if scheme not in SUPPORTED_SCHEMES:
        return ProcessedURLResult(
            original_url=clean_raw,
            is_valid=False,
            error_reason=f"Unsupported URL scheme '{scheme or 'none'}'. Only http and https are permitted."
        )

    # 2. Validate and Normalize Hostname
    hostname = parsed.hostname
    if not hostname:
        return ProcessedURLResult(
            original_url=clean_raw,
            is_valid=False,
            error_reason="Missing or invalid hostname in URL."
        )

    hostname = hostname.lower().rstrip(".")
    if not hostname or " " in hostname:
        return ProcessedURLResult(
            original_url=clean_raw,
            is_valid=False,
            error_reason=f"Invalid hostname '{hostname}'."
        )

    # 3. Handle Port Normalization
    port = parsed.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = hostname
    elif port is not None:
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    # 4. Canonical Domain Extraction (strip leading www. for clean domain entity representation)
    domain = hostname[4:] if hostname.startswith("www.") else hostname

    # 5. Path Normalization
    path = parsed.path or "/"
    try:
        # Normalize relative path segments like '/a/b/../c' -> '/a/c'
        normalized_path = posixpath.normpath(path)
    except Exception:
        normalized_path = path

    # Trailing slash policy: keep '/' for root, trim trailing '/' on subpaths
    if normalized_path != "/" and normalized_path.endswith("/"):
        normalized_path = normalized_path.rstrip("/")
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path

    # 6. Tracking Query Parameter Stripping
    query_string = ""
    if parsed.query:
        try:
            query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
            # Filter out known tracking parameters
            filtered_pairs = [
                (k, v) for k, v in query_pairs
                if k.lower() not in TRACKING_QUERY_PARAMS
            ]
            if filtered_pairs:
                query_string = urlencode(filtered_pairs)
        except Exception:
            query_string = parsed.query

    # 7. Reconstruct Normalized URL (fragments are stripped by omitting the 5th tuple element)
    normalized_url = urlunsplit((scheme, netloc, normalized_path, query_string, ""))

    return ProcessedURLResult(
        original_url=clean_raw,
        normalized_url=normalized_url,
        domain=domain,
        hostname=hostname,
        is_valid=True,
        error_reason=None,
    )


def process_candidate(candidate: CandidateSearchResult) -> Optional[CandidateSearchResult]:
    """Process, validate, and normalize a single CandidateSearchResult.

    Args:
        candidate: Raw candidate search result.

    Returns:
        Updated CandidateSearchResult with normalized URL and domain, or None if invalid.
    """
    res = normalize_url(candidate.url)
    if not res.is_valid or not res.normalized_url:
        logger.debug(f"Candidate URL rejected: {candidate.url} (Reason: {res.error_reason})")
        return None

    return CandidateSearchResult(
        title=candidate.title,
        url=res.normalized_url,
        snippet=candidate.snippet,
        query_used=candidate.query_used,
        domain=res.domain or candidate.domain,
        position=candidate.position,
    )


def process_candidates(
    candidates: list[CandidateSearchResult]
) -> list[CandidateSearchResult]:
    """Process, normalize, validate, and deduplicate a list of candidate search results.

    Deduplication rules:
    - Normalizes each candidate URL according to standard normalization rules.
    - Invalid URLs are discarded cleanly.
    - Duplicate normalized URLs (e.g. across multiple search queries) are deduplicated,
      preserving the first-seen instance and its search metadata.
    - Note: Different unique URL paths on the same domain (e.g. example.com/page-a vs
      example.com/page-b) are distinct URLs and are BOTH preserved.

    Args:
        candidates: List of raw candidate search results from Step 10 discovery.

    Returns:
        List of unique, valid, normalized CandidateSearchResult objects.
    """
    seen_normalized_urls: Set[str] = set()
    cleaned_candidates: list[CandidateSearchResult] = []

    for item in candidates:
        processed = process_candidate(item)
        if processed is None:
            continue

        if processed.url in seen_normalized_urls:
            logger.debug(f"Deduplicating duplicate normalized URL: {processed.url}")
            continue

        seen_normalized_urls.add(processed.url)
        cleaned_candidates.append(processed)

    return cleaned_candidates
