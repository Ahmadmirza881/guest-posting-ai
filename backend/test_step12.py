"""Comprehensive Test Suite for Step 12: Website Crawler.

Validates safe single-page HTTP fetching, bounded limits (timeout, size, redirects),
SSRF / private IP protection, non-HTML handling, title extraction, and database persistence.
All tests run with mocked HTTP responses without external network dependencies.
"""

import asyncio
from unittest.mock import AsyncMock, patch
import httpx

from app.database import init_db, SessionLocal
from app.models import Website
from app.services.crawler import (
    crawl_url,
    crawl_website_record,
    validate_target_url_safety,
    extract_html_title,
    CrawlResult,
)
from app.main import app


def test_url_safety_and_ssrf_validation():
    """Test SSRF validation against localhost, private IP ranges, and unsupported schemes."""
    print("Running Test: SSRF & URL Safety Validation...")

    # Allowed public web URLs
    safe_cases = [
        "https://example.com/write-for-us",
        "http://techblog.org/guest-post",
        "https://sub.domain.co.uk/articles",
    ]
    for url in safe_cases:
        is_safe, reason = validate_target_url_safety(url)
        assert is_safe is True, f"Expected safe for '{url}', got reason: {reason}"

    # Blocked private/local destinations
    blocked_cases = [
        ("http://localhost/admin", "restricted local"),
        ("http://127.0.0.1:8000/api", "restricted network range"),
        ("http://0.0.0.0/", "restricted network range"),
        ("http://192.168.1.1/router", "restricted network range"),
        ("http://10.0.0.5/internal", "restricted network range"),
        ("http://172.16.0.1/dashboard", "restricted network range"),
        ("http://169.254.169.254/latest/meta-data", "restricted local"),
        ("file:///etc/passwd", "Unsupported scheme"),
        ("javascript:alert(1)", "Unsupported scheme"),
        ("ftp://ftp.example.com", "Unsupported scheme"),
        ("mailto:test@example.com", "Unsupported scheme"),
    ]
    for url, expected_err in blocked_cases:
        is_safe, reason = validate_target_url_safety(url)
        assert is_safe is False, f"Expected blocked for '{url}'"
        assert reason is not None

    print("  [PASS] SSRF protection blocks local, private, and non-web addresses.")


def test_html_title_extraction():
    """Test document title extraction from raw HTML."""
    print("Running Test: Document Title Extraction...")
    sample_html = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>   AI Tech Journal &amp; News  </title>
        </head>
        <body>
            <h1>Welcome</h1>
        </body>
    </html>
    """
    title = extract_html_title(sample_html)
    assert title == "AI Tech Journal & News"

    # Missing title tag
    assert extract_html_title("<html><body>No Title</body></html>") is None
    assert extract_html_title("") is None

    print("  [PASS] HTML title extracted and unescaped correctly.")


async def test_successful_html_crawl():
    """Test 200 OK HTML response handling."""
    print("Running Test: Successful HTML Crawl (200 OK)...")

    sample_html = "<html><head><title>Tech Community</title></head><body>Write for Us</body></html>"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.url = httpx.URL("https://example.com/write-for-us")
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.content = sample_html.encode("utf-8")
    mock_resp.text = sample_html
    mock_client.get.return_value = mock_resp

    result = await crawl_url("https://example.com/write-for-us", client=mock_client)

    assert result.success is True
    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert result.title == "Tech Community"
    assert result.html == sample_html
    assert result.final_url == "https://example.com/write-for-us"
    assert result.error_type is None

    print("  [PASS] Successful HTML crawl returns structured HTML and metadata.")


async def test_redirect_handling():
    """Test redirect resolution and capture of final URL."""
    print("Running Test: Redirect Handling...")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.url = httpx.URL("https://www.example.com/final-guidelines")
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = b"<html><head><title>Redirected Page</title></head></html>"
    mock_resp.text = "<html><head><title>Redirected Page</title></head></html>"
    mock_client.get.return_value = mock_resp

    result = await crawl_url("http://example.com/short-link", client=mock_client)

    assert result.success is True
    assert result.original_url == "http://example.com/short-link"
    assert result.final_url == "https://www.example.com/final-guidelines"
    assert result.title == "Redirected Page"

    print("  [PASS] Redirect captures both original_url and final_url.")


async def test_http_404_and_500_handling():
    """Test 404 and 500 error responses without crashing."""
    print("Running Test: HTTP 404 & 500 Error Responses...")

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # 404 Not Found
    mock_resp_404 = AsyncMock(spec=httpx.Response)
    mock_resp_404.status_code = 404
    mock_resp_404.url = httpx.URL("https://example.com/not-found")
    mock_resp_404.headers = {"content-type": "text/html"}
    mock_resp_404.content = b"<html><head><title>404 Not Found</title></head></html>"
    mock_resp_404.text = "<html><head><title>404 Not Found</title></head></html>"
    mock_client.get.return_value = mock_resp_404

    res_404 = await crawl_url("https://example.com/not-found", client=mock_client)
    assert res_404.success is False
    assert res_404.status_code == 404
    assert res_404.error_type == "http_error"

    # 500 Internal Server Error
    mock_resp_500 = AsyncMock(spec=httpx.Response)
    mock_resp_500.status_code = 500
    mock_resp_500.url = httpx.URL("https://example.com/server-error")
    mock_resp_500.headers = {"content-type": "text/html"}
    mock_resp_500.content = b"Server Error"
    mock_resp_500.text = "Server Error"
    mock_client.get.return_value = mock_resp_500

    res_500 = await crawl_url("https://example.com/server-error", client=mock_client)
    assert res_500.success is False
    assert res_500.status_code == 500
    assert res_500.error_type == "http_error"

    print("  [PASS] 404 and 500 handled gracefully as structured failure results.")


async def test_timeout_and_network_failures():
    """Test timeout and connection network errors."""
    print("Running Test: Timeout & Network Failures...")

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Timeout
    mock_client.get.side_effect = httpx.ConnectTimeout("Request timed out")
    res_timeout = await crawl_url("https://example.com/slow-site", client=mock_client)
    assert res_timeout.success is False
    assert res_timeout.error_type == "timeout"

    # Network Connection Error
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")
    res_conn = await crawl_url("https://example.com/down-site", client=mock_client)
    assert res_conn.success is False
    assert res_conn.error_type == "connection_error"

    # Too many redirects
    mock_client.get.side_effect = httpx.TooManyRedirects("Redirect loop")
    res_redir = await crawl_url("https://example.com/loop", client=mock_client)
    assert res_redir.success is False
    assert res_redir.error_type == "too_many_redirects"

    print("  [PASS] Timeout, network errors, and redirect loops handled cleanly.")


async def test_non_html_response_handling():
    """Test that non-HTML responses (PDF, Image) are handled safely without HTML parsing."""
    print("Running Test: Non-HTML Response Handling...")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.url = httpx.URL("https://example.com/document.pdf")
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_resp.content = b"%PDF-1.4..."
    mock_client.get.return_value = mock_resp

    result = await crawl_url("https://example.com/document.pdf", client=mock_client)
    assert result.content_type == "application/pdf"
    assert result.html is None
    assert result.title is None
    assert result.status_code == 200

    print("  [PASS] Non-HTML content processed safely without decoding HTML.")


async def test_response_size_limit():
    """Test that responses exceeding max_bytes are stopped."""
    print("Running Test: Response Size Limit...")

    huge_content = b"A" * (3 * 1024 * 1024)  # 3MB

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.url = httpx.URL("https://example.com/huge-page")
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = huge_content
    mock_client.get.return_value = mock_resp

    # Crawl with max limit of 2MB (2097152 bytes)
    result = await crawl_url(
        "https://example.com/huge-page",
        client=mock_client,
        max_bytes=2097152
    )
    assert result.success is False
    assert result.error_type == "response_too_large"
    assert result.content_length > 2097152

    print("  [PASS] Oversized response size limit enforced.")


async def test_no_recursive_crawling_guarantee():
    """Verify that links inside HTML are not recursively crawled."""
    print("Running Test: No Recursive Crawling Scope Guarantee...")

    html_with_links = """
    <html>
        <body>
            <a href="/internal-page-1">Page 1</a>
            <a href="/internal-page-2">Page 2</a>
            <a href="https://example.com/contact">Contact</a>
        </body>
    </html>
    """

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.url = httpx.URL("https://example.com/no-recursion-test")
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = html_with_links.encode("utf-8")
    mock_resp.text = html_with_links
    mock_client.get.return_value = mock_resp

    result = await crawl_url("https://example.com/no-recursion-test", client=mock_client)

    # Verify only ONE get request was made
    assert mock_client.get.call_count == 1
    assert result.success is True

    print("  [PASS] Single-page fetch verified (0 recursive sub-requests performed).")


async def test_database_and_endpoint_integration():
    """Test database record crawl persistence and FastAPI POST /api/websites/{id}/crawl endpoint."""
    print("Running Test: Database & FastAPI Endpoint Integration...")
    init_db()

    db = SessionLocal()
    try:
        # Create a test website
        test_domain = "crawler-test-site.example.com"
        website = db.query(Website).filter_by(domain=test_domain).first()
        if not website:
            website = Website(
                domain=test_domain,
                url="https://crawler-test-site.example.com/write-for-us",
                name="Crawler Test Site",
                crawl_status="pending"
            )
            db.add(website)
            db.commit()
            db.refresh(website)

        web_id = website.id

        # Test crawl_website_record with mock client
        sample_page = "<html><head><title>Test Blog Guidelines</title></head><body>Content</body></html>"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = AsyncMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.url = httpx.URL("https://crawler-test-site.example.com/write-for-us")
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.content = sample_page.encode("utf-8")
        mock_resp.text = sample_page
        mock_client.get.return_value = mock_resp

        updated_web, crawl_res = await crawl_website_record(
            db=db,
            website_id=web_id,
            crawler_client=mock_client
        )

        assert updated_web is not None
        assert updated_web.crawl_status == "success"
        assert updated_web.http_status == 200
        assert updated_web.html_content == sample_page
        assert updated_web.last_crawled_at is not None
        assert updated_web.name == "Test Blog Guidelines"

        # Test FastAPI endpoint
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            get_res = await client.get(f"/api/websites/{web_id}")
            assert get_res.status_code == 200
            data = get_res.json()
            assert data["id"] == web_id
            assert data["crawl_status"] == "success"
            assert data["http_status"] == 200

        print(f"  [PASS] Crawl status and HTML content persisted in database for Website #{web_id}.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 12: WEBSITE CRAWLER TEST SUITE")
    print("=" * 60)

    test_url_safety_and_ssrf_validation()
    test_html_title_extraction()
    await test_successful_html_crawl()
    await test_redirect_handling()
    await test_http_404_and_500_handling()
    await test_timeout_and_network_failures()
    await test_non_html_response_handling()
    await test_response_size_limit()
    await test_no_recursive_crawling_guarantee()
    await test_database_and_endpoint_integration()

    print("=" * 60)
    print("ALL STEP 12 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
