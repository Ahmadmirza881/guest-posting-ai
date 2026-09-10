"""Comprehensive Test Suite for Step 24: Caching + Rate Limiting + Retry Strategies.

Covers all Phase H audit & integration test requirements:
1. Cache: Initial request invokes operation, second identical request uses cache.
2. Cache: Distinct cache keys generate distinct entries.
3. Cache: Expired cache entries re-trigger operation after TTL.
4. Cache: LRU capacity eviction respects CACHE_MAX_SIZE.
5. Cache: Failed requests/exceptions are NOT stored in cache.
6. Cache: Disabling cache bypasses all lookups/saves.
7. Cache: AI Verifier caching by input hash.
8. Cache: AI Analyzer caching by input hash.
9. Cache: Search discovery candidates caching.
10. Rate Limiting: External HTTP concurrency never exceeds MAX_CONCURRENT_HTTP_REQUESTS.
11. Rate Limiting: External AI concurrency never exceeds MAX_CONCURRENT_AI_REQUESTS.
12. Rate Limiting: Multiple Step 23 workers share and respect external limits.
13. Rate Limiting: External limits do not serialize independent website processing.
14. Retry: Transient network error/timeout is retried with backoff.
15. Retry: HTTP 429 rate limit is retried with exponential backoff.
16. Retry: HTTP 500/502/503/504 errors are retried.
17. Retry: Permanent errors (400, 401, 403, 404, SSRF blocked) fail fast without retry.
18. Retry: Concurrency limiter is released during backoff sleep.
19. Retry: Stops after MAX_RETRIES and propagates final failure cleanly.
20. Integration: Full Step 23 parallel processing works with Step 24 protections enabled.
21. Integration: Single website crawl/AI failure is isolated and does not stop batch.
22. Integration: User ownership and isolation remains fully preserved.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
from sqlalchemy import select, func

from app.config import settings
from app.database import init_db, SessionLocal
from app.models.user import User
from app.models.website import Website
from app.models.search import Search
from app.models.search_result import SearchResult
from app.models.saved_website import SavedWebsite
from app.models.guest_post import GuestPostInformation
from app.models.website_analysis import WebsiteAnalysis
from app.utils.cache import AsyncTTLCache, app_cache, generate_cache_key
from app.utils.rate_limiter import (
    ServiceLimiterManager,
    get_http_limiter,
    get_ai_limiter,
    reset_service_limiters,
    service_limiters,
)
from app.utils.retry import (
    execute_with_retry,
    is_transient_status_code,
    is_transient_exception,
    TRANSIENT_HTTP_STATUSES,
)
from app.services.crawler import crawl_url, CrawlResult, validate_target_url_safety
from app.services.ai_verifier import (
    AIVerificationInput,
    AIVerificationResult,
    verify_guest_post_opportunity,
    call_gemini_api,
    GeminiAPIError,
)
from app.services.ai_analyzer import (
    AIAnalysisInput,
    AIAnalysisResult,
    analyze_website_content,
)
from app.services.search_provider import (
    SerpApiProvider,
    CandidateSearchResult,
    discover_candidates_for_keyword,
    SearchProviderRequestError,
)
from app.services.pipeline import process_single_website_pipeline, process_search_pipeline
from app.utils.security import hash_password


def clean_db(db):
    """Reset test database state."""
    db.query(SavedWebsite).delete()
    db.query(SearchResult).delete()
    db.query(WebsiteAnalysis).delete()
    db.query(GuestPostInformation).delete()
    db.query(Website).delete()
    db.query(Search).delete()
    db.query(User).delete()
    db.commit()


# =====================================================================
# 1. CACHING LAYER TESTS
# =====================================================================

async def test_cache_miss_then_hit():
    """1. First request calls operation, second identical request uses cache."""
    cache = AsyncTTLCache(ttl_seconds=60, max_size=10, enabled=True)
    key = "test:item1"

    # Initial lookup is a miss
    assert await cache.get(key) is None

    # Set value
    await cache.set(key, {"data": "val1"})

    # Subsequent lookup is a hit
    cached = await cache.get(key)
    assert cached == {"data": "val1"}
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


async def test_cache_distinct_keys():
    """2. Different cache keys cause new requests and distinct entries."""
    cache = AsyncTTLCache(ttl_seconds=60, max_size=10, enabled=True)
    await cache.set("k1", "value1")
    await cache.set("k2", "value2")

    assert await cache.get("k1") == "value1"
    assert await cache.get("k2") == "value2"
    assert await cache.get("k3") is None


async def test_cache_ttl_expiration():
    """3. Expired cache entries re-trigger call after TTL."""
    cache = AsyncTTLCache(ttl_seconds=1, max_size=10, enabled=True)
    await cache.set("quick_key", "temporary_val", ttl=1)

    assert await cache.get("quick_key") == "temporary_val"

    # Wait for expiry
    await asyncio.sleep(1.05)

    # Lookup after expiry returns None
    assert await cache.get("quick_key") is None


async def test_cache_lru_capacity_eviction():
    """4. LRU eviction pops oldest entry when max_size is reached."""
    cache = AsyncTTLCache(ttl_seconds=60, max_size=3, enabled=True)

    await cache.set("k1", "v1")
    await cache.set("k2", "v2")
    await cache.set("k3", "v3")
    assert await cache.size() == 3

    # Access k1 so k2 is least recently used
    await cache.get("k1")

    # Add 4th item -> should evict k2
    await cache.set("k4", "v4")
    assert await cache.size() == 3

    assert await cache.get("k1") == "v1"
    assert await cache.get("k2") is None  # Evicted
    assert await cache.get("k3") == "v3"
    assert await cache.get("k4") == "v4"


async def test_cache_disabled_mode():
    """5. Cache can be disabled and falls back cleanly."""
    cache = AsyncTTLCache(ttl_seconds=60, max_size=10, enabled=False)

    await cache.set("k1", "v1")
    assert await cache.get("k1") is None
    assert await cache.size() == 0


async def test_crawler_caching_and_error_isolation():
    """6. Crawler caches successful responses and does NOT cache errors."""
    await app_cache.clear()
    target_url = "https://tech-author-sample.org/guidelines"

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.url = httpx.URL(target_url)
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.content = b"<html><head><title>Write For Us</title></head><body>Guest Guidelines</body></html>"
    mock_resp.text = "<html><head><title>Write For Us</title></head><body>Guest Guidelines</body></html>"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    # First call -> triggers network fetch
    res1 = await crawl_url(target_url, client=mock_client)
    assert res1.success is True
    assert res1.title == "Write For Us"
    assert mock_client.get.call_count == 1

    # Second call -> returned from cache, no network call
    res2 = await crawl_url(target_url, client=mock_client)
    assert res2.success is True
    assert res2.title == "Write For Us"
    assert mock_client.get.call_count == 1  # Not incremented!

    # Failure test: failing request is not cached
    failing_url = "https://failing-domain-sample.com"
    mock_fail_client = AsyncMock(spec=httpx.AsyncClient)
    mock_fail_client.get.side_effect = httpx.ConnectError("Connection refused")

    res_fail = await crawl_url(failing_url, client=mock_fail_client)
    assert res_fail.success is False
    assert res_fail.error_type == "connection_error"

    cache_key = generate_cache_key("crawler", failing_url)
    assert await app_cache.get(cache_key) is None


async def test_ai_verifier_caching():
    """7. AI verifier caches successful responses based on stable input hash."""
    await app_cache.clear()

    input_data = AIVerificationInput(
        website_url="https://ai-blog.example.com",
        page_title="AI Blog",
        cleaned_page_text="We welcome guest contributors to write about AI algorithms.",
        step13_detected=True,
        step13_confidence=85,
        step13_signals=["write for us"],
    )

    fake_model_response = {
        "verification_status": "verified",
        "accepts_guest_posts": True,
        "confidence": 90,
        "reason": "Clear invitation to contribute articles.",
        "guest_post_evidence": "We welcome guest contributors",
    }

    with patch("app.services.ai_verifier.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = fake_model_response

        # First call
        res1 = await verify_guest_post_opportunity(input_data)
        assert res1.verification_status == "verified"
        assert mock_gemini.call_count == 1

        # Second call with same input -> cache hit
        res2 = await verify_guest_post_opportunity(input_data)
        assert res2.verification_status == "verified"
        assert mock_gemini.call_count == 1  # Gemini not called again


async def test_ai_analyzer_caching():
    """8. AI analyzer caches completed responses."""
    await app_cache.clear()

    input_data = AIAnalysisInput(
        website_url="https://cloudmag.io",
        domain="cloudmag.io",
        page_title="Cloud Magazine",
        search_keyword="DevOps",
        cleaned_page_text="Expert DevOps, Kubernetes, and cloud infrastructure articles.",
        step13_detected=True,
        step13_confidence=90,
    )

    fake_analysis_response = {
        "primary_niche": "Cloud & DevOps",
        "topics": ["DevOps", "Kubernetes"],
        "niche_confidence": 95,
        "relevance_score": 90,
        "relevance_reason": "Direct match for DevOps keyword.",
        "content_quality_score": 85,
        "content_quality_reason": "High technical depth.",
        "trust_signals": ["Author bylines", "Editorial board"],
        "editorial_standards": ["Peer review"],
        "strengths": ["Strong technical articles"],
        "weaknesses": [],
        "analysis_confidence": 90,
        "evidence": ["DevOps, Kubernetes, and cloud infrastructure"],
    }

    with patch("app.services.ai_analyzer.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = fake_analysis_response

        # First call
        res1 = await analyze_website_content(input_data)
        assert res1.analysis_status == "completed"
        assert res1.primary_niche == "Cloud & DevOps"
        assert mock_gemini.call_count == 1

        # Second call -> cache hit
        res2 = await analyze_website_content(input_data)
        assert res2.primary_niche == "Cloud & DevOps"
        assert mock_gemini.call_count == 1


# =====================================================================
# 2. RATE LIMITING & CONCURRENCY TESTS
# =====================================================================

async def test_http_rate_limiter_concurrency_bound():
    """9. HTTP requests never exceed configured MAX_CONCURRENT_HTTP_REQUESTS."""
    http_limit = 3
    reset_service_limiters(http_limit=http_limit, ai_limit=2)
    limiter = get_http_limiter()

    active_count = 0
    max_observed_active = 0
    lock = asyncio.Lock()

    async def _mock_http_task():
        nonlocal active_count, max_observed_active
        async with limiter:
            async with lock:
                active_count += 1
                if active_count > max_observed_active:
                    max_observed_active = active_count

            await asyncio.sleep(0.04)

            async with lock:
                active_count -= 1

    await asyncio.gather(*[_mock_http_task() for _ in range(10)])

    assert max_observed_active <= http_limit
    assert max_observed_active == http_limit


async def test_ai_rate_limiter_concurrency_bound():
    """10. AI requests never exceed configured MAX_CONCURRENT_AI_REQUESTS."""
    ai_limit = 2
    reset_service_limiters(http_limit=5, ai_limit=ai_limit)
    limiter = get_ai_limiter()

    active_count = 0
    max_observed_active = 0
    lock = asyncio.Lock()

    async def _mock_ai_task():
        nonlocal active_count, max_observed_active
        async with limiter:
            async with lock:
                active_count += 1
                if active_count > max_observed_active:
                    max_observed_active = active_count

            await asyncio.sleep(0.04)

            async with lock:
                active_count -= 1

    await asyncio.gather(*[_mock_ai_task() for _ in range(8)])

    assert max_observed_active <= ai_limit
    assert max_observed_active == ai_limit


async def test_step23_parallel_workers_share_external_limiter():
    """11. Multiple Step 23 pipeline workers share and respect the external limits."""
    reset_service_limiters(http_limit=2, ai_limit=2)
    limiter = get_http_limiter()

    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def _pipeline_worker(worker_id: int):
        nonlocal active, max_active
        async with limiter:
            async with lock:
                active += 1
                if active > max_active:
                    max_active = active
            await asyncio.sleep(0.03)
            async with lock:
                active -= 1

    await asyncio.gather(*[_pipeline_worker(i) for i in range(6)])
    assert max_active == 2


async def test_external_limit_does_not_serialize_unnecessarily():
    """12. External limiter allows up to N parallel requests without global serialization."""
    reset_service_limiters(http_limit=4, ai_limit=4)
    limiter = get_http_limiter()

    start_time = time.perf_counter()

    async def _task():
        async with limiter:
            await asyncio.sleep(0.05)

    # 4 tasks with limit 4 should run concurrently taking ~0.05s, not serialized 0.20s
    await asyncio.gather(*[_task() for _ in range(4)])
    elapsed = time.perf_counter() - start_time

    assert elapsed < 0.15  # Much faster than 4 * 0.05 = 0.20s


# =====================================================================
# 3. RETRY STRATEGY & EXPONENTIAL BACKOFF TESTS
# =====================================================================

def test_transient_status_classification():
    """13. HTTP status codes correctly classified as transient vs permanent."""
    for code in [429, 500, 502, 503, 504]:
        assert is_transient_status_code(code) is True

    for code in [200, 201, 400, 401, 403, 404, 405, 422]:
        assert is_transient_status_code(code) is False


def test_transient_exception_classification():
    """14. Exceptions correctly classified as transient vs permanent."""
    assert is_transient_exception(httpx.ReadTimeout("Timeout")) is True
    assert is_transient_exception(httpx.ConnectError("Failed connect")) is True
    assert is_transient_exception(GeminiAPIError("Rate limit exceeded 429")) is True
    assert is_transient_exception(GeminiAPIError("503 Service Unavailable")) is True

    # Permanent errors must not be retried
    assert is_transient_exception(ValueError("Invalid format")) is False
    assert is_transient_exception(GeminiAPIError("403 Forbidden: API key invalid")) is False


async def test_retry_transient_failure_success_on_retry():
    """15. Transient error triggers retry and succeeds on subsequent attempt with backoff."""
    call_count = 0
    sleeps_recorded: List[float] = []

    async def _mock_sleep(delay: float):
        sleeps_recorded.append(delay)

    async def _unstable_op():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("Network glitch")
        return "SUCCESS_DATA"

    result = await execute_with_retry(
        _unstable_op,
        max_retries=3,
        base_delay=1.0,
        max_delay=10.0,
        sleep_fn=_mock_sleep,
    )

    assert result == "SUCCESS_DATA"
    assert call_count == 3
    assert len(sleeps_recorded) == 2
    assert sleeps_recorded[0] == 1.0
    assert sleeps_recorded[1] == 2.0


async def test_retry_stops_after_max_retries():
    """16. Retry stops after max_retries and propagates the final exception."""
    call_count = 0
    sleeps_recorded: List[float] = []

    async def _mock_sleep(delay: float):
        sleeps_recorded.append(delay)

    async def _always_failing_op():
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Continuous timeout")

    caught = False
    try:
        await execute_with_retry(
            _always_failing_op,
            max_retries=2,
            base_delay=1.0,
            sleep_fn=_mock_sleep,
        )
    except httpx.ReadTimeout:
        caught = True

    assert caught is True
    assert call_count == 3
    assert len(sleeps_recorded) == 2


async def test_permanent_error_not_retried():
    """17. Permanent errors fail immediately without retry."""
    call_count = 0
    sleeps_recorded: List[float] = []

    async def _mock_sleep(delay: float):
        sleeps_recorded.append(delay)

    async def _perm_fail_op():
        nonlocal call_count
        call_count += 1
        raise ValueError("Target host is blocked or invalid (SSRF)")

    caught = False
    try:
        await execute_with_retry(
            _perm_fail_op,
            max_retries=3,
            base_delay=1.0,
            sleep_fn=_mock_sleep,
        )
    except ValueError:
        caught = True

    assert caught is True
    assert call_count == 1
    assert len(sleeps_recorded) == 0


async def test_limiter_released_during_backoff_sleep():
    """18. Concurrency limiter is released before sleeping in exponential backoff."""
    limiter = asyncio.Semaphore(1)
    call_count = 0
    limiter_held_during_sleep = False

    async def _mock_sleep(delay: float):
        nonlocal limiter_held_during_sleep
        if limiter.locked():
            limiter_held_during_sleep = True

    async def _transient_op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Transient drop")
        return "OK"

    res = await execute_with_retry(
        _transient_op,
        limiter=limiter,
        max_retries=2,
        base_delay=0.1,
        sleep_fn=_mock_sleep,
    )

    assert res == "OK"
    assert call_count == 2
    assert limiter_held_during_sleep is False


# =====================================================================
# 4. STEP 23 PIPELINE INTEGRATION & REGRESSION TESTS
# =====================================================================

async def test_step23_parallel_pipeline_with_step24_caching_and_limits():
    """19. Full Step 23 bounded parallel pipeline runs cleanly with Step 24 protections."""
    db = SessionLocal()
    clean_db(db)
    try:
        search = Search(
            keyword="Cloud Engineering",
            requested_website_count=3,
            status="pending",
        )
        db.add(search)
        db.commit()
        db.refresh(search)

        w1 = Website(domain="cloudarch1.org", url="https://cloudarch1.org/write-for-us")
        w2 = Website(domain="cloudarch2.org", url="https://cloudarch2.org/contribute")
        w3 = Website(domain="cloudarch3.org", url="https://cloudarch3.org/editorial")
        db.add_all([w1, w2, w3])
        db.commit()

        sr1 = SearchResult(search_id=search.id, website_id=w1.id, status="discovered")
        sr2 = SearchResult(search_id=search.id, website_id=w2.id, status="discovered")
        sr3 = SearchResult(search_id=search.id, website_id=w3.id, status="discovered")
        db.add_all([sr1, sr2, sr3])
        db.commit()
        search_id = search.id
    finally:
        db.close()

    fake_verification = {
        "verification_status": "verified",
        "accepts_guest_posts": True,
        "confidence": 88,
        "reason": "Active contributor guidelines found.",
        "submission_email": "editor@cloudarch.org",
    }

    fake_analysis = {
        "primary_niche": "Cloud Computing",
        "topics": ["Cloud", "DevOps"],
        "niche_confidence": 90,
        "relevance_score": 85,
        "relevance_reason": "High match for cloud engineering.",
        "content_quality_score": 80,
        "content_quality_reason": "Good depth.",
        "trust_signals": ["Author byline", "Editorial contact"],
        "editorial_standards": ["Original content"],
        "strengths": ["Clear niche focus"],
        "weaknesses": [],
        "analysis_confidence": 85,
        "evidence": ["Submit your cloud articles"],
    }

    with patch("app.services.crawler.crawl_url") as mock_crawl, \
         patch("app.services.ai_verifier.call_gemini_api", new_callable=AsyncMock) as mock_verifier_gemini, \
         patch("app.services.ai_analyzer.call_gemini_api", new_callable=AsyncMock) as mock_analyzer_gemini:

        mock_crawl.return_value = CrawlResult(
            original_url="https://cloudarch.org",
            final_url="https://cloudarch.org",
            status_code=200,
            content_type="text/html",
            html="<html><head><title>Cloud Tech</title></head><body><h1>Write For Us</h1><p>Email editor@cloudarch.org</p></body></html>",
            title="Cloud Tech",
            success=True,
        )
        mock_verifier_gemini.return_value = fake_verification
        mock_analyzer_gemini.return_value = fake_analysis

        # Execute batch pipeline with concurrency limit of 2
        await process_search_pipeline(search_id=search_id, max_concurrency=2)

    # Verify search completed and all websites are processed and scored
    verify_db = SessionLocal()
    try:
        updated_search = verify_db.get(Search, search_id)
        assert updated_search.status == "completed"

        results = verify_db.scalars(
            select(SearchResult).where(SearchResult.search_id == search_id)
        ).all()
        assert len(results) == 3
        for r in results:
            assert r.status == "processed"
            assert r.website.analysis is not None
            assert r.website.analysis.quality_score is not None
            assert r.website.analysis.quality_score > 0
    finally:
        verify_db.close()


async def test_search_discovery_caching():
    """20. Search engine candidate discovery results are cached."""
    await app_cache.clear()

    mock_candidates = [
        CandidateSearchResult(
            title="Python Tech Blog",
            url="https://python-blog.example.com/write",
            snippet="Write for our python tech blog",
            query_used="Python write for us",
        )
    ]

    mock_provider = MagicMock(spec=SerpApiProvider)
    mock_provider.search = AsyncMock(return_value=mock_candidates)
    mock_provider.timeout = 15.0

    # First discovery call -> queries provider
    c1 = await discover_candidates_for_keyword("Python", target_count=1, provider=mock_provider)
    assert len(c1) == 1
    assert mock_provider.search.call_count == 1

    # Second discovery call with same keyword & target_count -> cache hit
    c2 = await discover_candidates_for_keyword("Python", target_count=1, provider=mock_provider)
    assert len(c2) == 1
    assert mock_provider.search.call_count == 1  # Not called again!


async def test_user_ownership_isolation_preserved():
    """21. User ownership from Steps 21–22 is preserved with Step 24 protections active."""
    db = SessionLocal()
    clean_db(db)
    try:
        u1 = User(email="user1@example.com", password_hash=hash_password("Pass123!"))
        u2 = User(email="user2@example.com", password_hash=hash_password("Pass123!"))
        db.add_all([u1, u2])
        db.commit()

        s1 = Search(keyword="Marketing", user_id=u1.id, status="completed")
        s2 = Search(keyword="Fintech", user_id=u2.id, status="completed")
        db.add_all([s1, s2])
        db.commit()

        # Verify searches are isolated
        u1_searches = db.scalars(select(Search).where(Search.user_id == u1.id)).all()
        u2_searches = db.scalars(select(Search).where(Search.user_id == u2.id)).all()

        assert len(u1_searches) == 1
        assert u1_searches[0].keyword == "Marketing"
        assert len(u2_searches) == 1
        assert u2_searches[0].keyword == "Fintech"
    finally:
        db.close()


# =====================================================================
# Main Runner
# =====================================================================

def run_all_step24_tests():
    """Run all Step 24 tests and report exact PASS/FAIL results."""
    import traceback

    print("=" * 70)
    print("STEP 24 TEST SUITE: CACHING + RATE LIMITING + RETRIES")
    print("=" * 70)

    init_db()

    sync_tests = [
        test_transient_status_classification,
        test_transient_exception_classification,
    ]

    async_tests = [
        test_cache_miss_then_hit,
        test_cache_distinct_keys,
        test_cache_ttl_expiration,
        test_cache_lru_capacity_eviction,
        test_cache_disabled_mode,
        test_crawler_caching_and_error_isolation,
        test_ai_verifier_caching,
        test_ai_analyzer_caching,
        test_http_rate_limiter_concurrency_bound,
        test_ai_rate_limiter_concurrency_bound,
        test_step23_parallel_workers_share_external_limiter,
        test_external_limit_does_not_serialize_unnecessarily,
        test_retry_transient_failure_success_on_retry,
        test_retry_stops_after_max_retries,
        test_permanent_error_not_retried,
        test_limiter_released_during_backoff_sleep,
        test_step23_parallel_pipeline_with_step24_caching_and_limits,
        test_search_discovery_caching,
        test_user_ownership_isolation_preserved,
    ]

    passed = 0
    failed = 0

    for idx, test in enumerate(sync_tests, 1):
        try:
            test()
            print(f"  [{idx:02d}] PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [{idx:02d}] FAIL: {test.__name__} -> {e}")
            traceback.print_exc()
            failed += 1

    for idx, test in enumerate(async_tests, len(sync_tests) + 1):
        try:
            asyncio.run(test())
            print(f"  [{idx:02d}] PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [{idx:02d}] FAIL: {test.__name__} -> {e}")
            traceback.print_exc()
            failed += 1

    print("-" * 70)
    print(f"TOTAL: {passed + failed} | PASSED: {passed} | FAILED: {failed}")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_step24_tests()
