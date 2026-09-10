"""Comprehensive Test Suite for Step 11: URL Processing & Cleaning.

Validates syntactic normalization, validation, tracking parameter stripping,
deduplication, domain extraction, and network-independence.
"""

import asyncio
from app.database import init_db, SessionLocal
from app.models import Search, SearchResult, Website
from app.schemas.search import SearchCreate
from app.services.search_provider import CandidateSearchResult, SerpApiProvider
from app.services.url_processor import (
    normalize_url,
    process_candidate,
    process_candidates,
    ProcessedURLResult,
    TRACKING_QUERY_PARAMS,
)
from app.services.search_service import (
    create_search,
    execute_search_discovery,
    get_search_by_id,
)


def test_basic_url_normalization():
    """Test standard valid HTTP and HTTPS URL normalization."""
    print("Running Test: Basic URL Normalization...")
    res1 = normalize_url("https://example.com/write-for-us")
    assert res1.is_valid is True
    assert res1.normalized_url == "https://example.com/write-for-us"
    assert res1.domain == "example.com"
    assert res1.hostname == "example.com"

    res2 = normalize_url("http://techblog.org/guest-post")
    assert res2.is_valid is True
    assert res2.normalized_url == "http://techblog.org/guest-post"
    assert res2.domain == "techblog.org"

    print("  [PASS] Basic URLs normalize correctly.")


def test_whitespace_handling():
    """Test leading and trailing whitespace stripping."""
    print("Running Test: Whitespace Handling...")
    res = normalize_url("   https://example.com/write-for-us   \n")
    assert res.is_valid is True
    assert res.normalized_url == "https://example.com/write-for-us"
    print("  [PASS] Whitespace stripped cleanly.")


def test_hostname_case_normalization():
    """Test that hostname casing is normalized to lowercase while path casing is preserved."""
    print("Running Test: Hostname Case Normalization...")
    res = normalize_url("HTTPS://WWW.EXAMPLE.COM/Write-For-Us/Article")
    assert res.is_valid is True
    assert res.normalized_url == "https://www.example.com/Write-For-Us/Article"
    assert res.domain == "example.com"
    assert res.hostname == "www.example.com"
    print("  [PASS] Hostnames converted to lowercase.")


def test_fragment_stripping():
    """Test that URL fragments (#section) are stripped."""
    print("Running Test: Fragment Stripping...")
    res = normalize_url("https://example.com/write-for-us#submission-guidelines")
    assert res.is_valid is True
    assert res.normalized_url == "https://example.com/write-for-us"

    res_empty_frag = normalize_url("https://example.com/page#")
    assert res_empty_frag.is_valid is True
    assert res_empty_frag.normalized_url == "https://example.com/page"
    print("  [PASS] Fragments stripped completely.")


def test_default_port_normalization():
    """Test that default ports (80 for http, 443 for https) are omitted while custom ports are preserved."""
    print("Running Test: Default Port Normalization...")
    res_https_443 = normalize_url("https://example.com:443/write-for-us")
    assert res_https_443.normalized_url == "https://example.com/write-for-us"

    res_http_80 = normalize_url("http://example.com:80/write-for-us")
    assert res_http_80.normalized_url == "http://example.com/write-for-us"

    res_custom_port = normalize_url("https://example.com:8443/write-for-us")
    assert res_custom_port.normalized_url == "https://example.com:8443/write-for-us"
    print("  [PASS] Default ports handled safely.")


def test_tracking_parameter_removal():
    """Test that analytics/marketing tracking parameters are removed."""
    print("Running Test: Tracking Parameter Removal...")
    url_with_tracking = "https://example.com/write-for-us?utm_source=google&utm_medium=cpc&utm_campaign=fall2026&gclid=abc123xyz"
    res = normalize_url(url_with_tracking)
    assert res.is_valid is True
    assert res.normalized_url == "https://example.com/write-for-us"

    url_fb = "https://example.com/submit?fbclid=xyz987&ref=sidebar"
    res_fb = normalize_url(url_fb)
    assert res_fb.normalized_url == "https://example.com/submit"
    print("  [PASS] Tracking parameters stripped.")


def test_meaningful_query_parameter_preservation():
    """Test that functional/content query parameters are strictly preserved."""
    print("Running Test: Meaningful Query Parameter Preservation...")
    url_with_content_params = "https://example.com/blog?category=ai&page=2&id=1054"
    res = normalize_url(url_with_content_params)
    assert res.is_valid is True
    assert res.normalized_url == "https://example.com/blog?category=ai&page=2&id=1054"

    # Mixed tracking and functional parameters
    url_mixed = "https://example.com/blog?category=ai&utm_source=twitter&page=2"
    res_mixed = normalize_url(url_mixed)
    assert res_mixed.is_valid is True
    assert res_mixed.normalized_url == "https://example.com/blog?category=ai&page=2"
    print("  [PASS] Non-tracking parameters preserved accurately.")


def test_trailing_slash_normalization():
    """Test consistent trailing slash policy for subpaths vs root domain."""
    print("Running Test: Trailing Slash Policy...")
    # Subpaths have trailing slashes normalized
    res_subpath = normalize_url("https://example.com/write-for-us/")
    assert res_subpath.normalized_url == "https://example.com/write-for-us"

    # Root paths are preserved
    res_root = normalize_url("https://example.com/")
    assert res_root.normalized_url == "https://example.com/"

    res_bare = normalize_url("https://example.com")
    assert res_bare.normalized_url == "https://example.com/"
    print("  [PASS] Trailing slash policy is consistent.")


def test_invalid_urls_rejection():
    """Test rejection of non-web schemes and malformed strings."""
    print("Running Test: Invalid URL Rejection...")
    invalid_cases = [
        ("not-a-url", "Unsupported URL scheme"),
        ("javascript:alert(1)", "Unsupported URL scheme"),
        ("mailto:editor@example.com", "Unsupported URL scheme"),
        ("tel:+1234567890", "Unsupported URL scheme"),
        ("file:///C:/passwords.txt", "Unsupported URL scheme"),
        ("ftp://ftp.example.com/file", "Unsupported URL scheme"),
        ("", "URL is empty or blank"),
        (None, "URL is None"),
        ("http://", "Missing or invalid hostname"),
    ]

    for raw, expected_reason_sub in invalid_cases:
        res = normalize_url(raw)
        assert res.is_valid is False, f"Expected '{raw}' to be rejected as invalid"
        assert res.normalized_url is None
        assert res.error_reason is not None

    print("  [PASS] All invalid and non-web URLs rejected cleanly.")


def test_candidate_deduplication():
    """Test deduplication of CandidateSearchResult objects across multiple queries."""
    print("Running Test: Candidate Deduplication Across Queries...")
    raw_candidates = [
        CandidateSearchResult(
            title="Tech Blog - Write For Us",
            url="https://example.com/write-for-us",
            snippet="We accept AI articles",
            query_used="AI write for us",
            position=1
        ),
        CandidateSearchResult(
            title="Tech Blog - Guest Post",
            url="HTTPS://EXAMPLE.COM/write-for-us#guidelines",
            snippet="Submit your guest post",
            query_used="AI guest post",
            position=2
        ),
        CandidateSearchResult(
            title="Tech Blog - Contributor",
            url="https://example.com:443/write-for-us?utm_source=google",
            snippet="Become a contributor",
            query_used="AI become a contributor",
            position=1
        ),
        # Distinct URL on the same domain
        CandidateSearchResult(
            title="Tech Blog - Editorial Guidelines",
            url="https://example.com/guidelines",
            snippet="Editorial rules",
            query_used="AI editorial guidelines",
            position=3
        ),
        # Another distinct domain
        CandidateSearchResult(
            title="Dev Hub",
            url="https://devhub.io/guest-post/",
            snippet="Dev Hub guest posts",
            query_used="AI guest post",
            position=4
        ),
    ]

    clean_results = process_candidates(raw_candidates)
    
    # 3 duplicate variants of 'example.com/write-for-us' must collapse to 1
    # 1 distinct path 'example.com/guidelines' must be preserved
    # 1 distinct domain 'devhub.io/guest-post' must be preserved
    # Total unique candidates = 3
    assert len(clean_results) == 3

    assert clean_results[0].url == "https://example.com/write-for-us"
    assert clean_results[0].domain == "example.com"
    assert clean_results[0].title == "Tech Blog - Write For Us"

    assert clean_results[1].url == "https://example.com/guidelines"
    assert clean_results[1].domain == "example.com"

    assert clean_results[2].url == "https://devhub.io/guest-post"
    assert clean_results[2].domain == "devhub.io"

    print("  [PASS] Candidate list deduplicated to unique canonical URLs while preserving distinct paths.")


async def test_search_discovery_integration():
    """Test full search discovery workflow with Step 11 URL processing integrated."""
    print("Running Test: Discovery Service + URL Processing DB Integration...")
    init_db()

    db = SessionLocal()
    try:
        search_in = SearchCreate(keyword="Data Science", requested_website_count=10)
        search = create_search(db=db, search_in=search_in)

        # Mock provider returning raw URLs with duplicates, tracking parameters, and uppercase schemes
        class MockStep11Provider(SerpApiProvider):
            def __init__(self):
                super().__init__(api_key="mock_key")

            async def search(self, query: str, num_results: int = 10, client=None):
                return [
                    CandidateSearchResult(
                        title="Data Science Central",
                        url="HTTPS://WWW.DataScienceCentral.COM/Write-For-Us/?utm_source=bing",
                        snippet="Write for our community",
                        query_used=query,
                        position=1
                    ),
                    CandidateSearchResult(
                        title="Data Science Central Duplicate",
                        url="https://datasciencecentral.com/write-for-us#section",
                        snippet="Write for us section",
                        query_used=query,
                        position=2
                    ),
                    CandidateSearchResult(
                        title="Invalid Item",
                        url="mailto:info@datasciencecentral.com",
                        snippet="Email us",
                        query_used=query,
                        position=3
                    ),
                ]

        updated_search = await execute_search_discovery(
            db=db,
            search=search,
            provider=MockStep11Provider()
        )

        assert updated_search.status == "discovered"
        fetched_search = get_search_by_id(db=db, search_id=search.id)
        assert fetched_search is not None
        # Only 1 unique valid URL should be persisted in DB
        assert len(fetched_search.results) == 1
        
        sr = fetched_search.results[0]
        assert sr.website.url == "https://www.datasciencecentral.com/Write-For-Us"
        assert sr.website.domain == "datasciencecentral.com"
        assert sr.status == "discovered"

        print("  [PASS] Database successfully populated with deduplicated and normalized URLs.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 11: URL PROCESSING & CLEANING TEST SUITE")
    print("=" * 60)

    test_basic_url_normalization()
    test_whitespace_handling()
    test_hostname_case_normalization()
    test_fragment_stripping()
    test_default_port_normalization()
    test_tracking_parameter_removal()
    test_meaningful_query_parameter_preservation()
    test_trailing_slash_normalization()
    test_invalid_urls_rejection()
    test_candidate_deduplication()
    await test_search_discovery_integration()

    print("=" * 60)
    print("ALL STEP 11 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
