"""Comprehensive Test Suite for Step 13: Deterministic Guest Post Detection.

Validates rule-based heuristic signal matching, HTML normalization, script/style exclusion,
evidence snippet extraction, confidence scoring, false positive protection, conflict resolution,
and database/API integration without external network dependencies.
"""

import asyncio
from app.database import init_db, SessionLocal
from app.models import Website, GuestPostInformation
from app.services.guest_post_detector import (
    detect_guest_post_opportunity,
    detect_guest_post_for_website,
    normalize_html_for_detection,
    extract_evidence_snippets,
    STRONG_SIGNALS,
    MEDIUM_SIGNALS,
    WEAK_SIGNALS,
    NEGATIVE_SIGNALS,
    GuestPostDetectionResult,
)
from app.main import app
import httpx


def test_html_normalization_and_tag_stripping():
    """Test that scripts, styles, and tags are cleanly removed while preserving text structure."""
    print("Running Test: HTML Normalization & Tag Stripping...")

    raw_html = """
    <html>
        <head>
            <style>body { color: red; } /* write for us */</style>
            <script>console.log("submit a guest post");</script>
        </head>
        <body>
            <h1>Write</h1>
            <span>For</span>
            <strong>Us</strong>
            <p>We are currently welcoming new writers to join our team.</p>
        </body>
    </html>
    """
    clean_text = normalize_html_for_detection(raw_html)

    # Verify script and style contents were completely excluded
    assert "console.log" not in clean_text
    assert "color: red" not in clean_text

    # Verify split tags were reconstituted into readable text
    assert "Write For Us" in clean_text or "Write For Us We" in clean_text
    assert "welcoming new writers" in clean_text

    print("  [PASS] HTML normalized, script/style stripped, text words preserved.")


def test_strong_positive_detection():
    """Test detection with a single strong positive signal."""
    print("Running Test: Strong Positive Detection...")
    html = "<html><body><h1>Write For Us</h1><p>We accept guest contributions on tech and AI.</p></body></html>"
    result = detect_guest_post_opportunity(html, url="https://example.com/write-for-us")

    assert result.detected is True
    assert result.confidence >= 85
    assert "write for us" in result.strong_signals
    assert len(result.evidence_snippets) > 0
    assert "write for us" in result.evidence_snippets[0].lower()
    assert result.has_conflicts is False

    print(f"  [PASS] Strong positive detected with confidence {result.confidence}%.")


def test_multiple_positive_signals():
    """Test detection with multiple strong and medium signals."""
    print("Running Test: Multiple Positive Signals...")
    html = """
    <html>
        <body>
            <h1>Write For Our Blog</h1>
            <p>Review our contributor guidelines before sending an article.</p>
            <p>You can submit a guest post directly to our editorial board.</p>
        </body>
    </html>
    """
    result = detect_guest_post_opportunity(html, url="https://example.com/contribute")

    assert result.detected is True
    assert result.confidence == 95
    assert len(result.strong_signals) >= 2
    assert "write for our blog" in result.strong_signals
    assert "contributor guidelines" in result.strong_signals
    assert "submit a guest post" in result.strong_signals
    assert len(result.evidence_snippets) >= 2

    print(f"  [PASS] Multiple positive signals detected with max confidence {result.confidence}%.")


def test_case_insensitive_matching():
    """Test case insensitivity for all signal variations."""
    print("Running Test: Case Insensitive Matching...")
    cases = [
        "<html><body>WRITE FOR US</body></html>",
        "<html><body>write for us</body></html>",
        "<html><body>Write For Us</body></html>",
        "<html><body>wRiTe fOr uS</body></html>",
    ]
    for c in cases:
        res = detect_guest_post_opportunity(c)
        assert res.detected is True, f"Failed for case: {c}"
        assert "write for us" in res.strong_signals

    print("  [PASS] Signal matching is strictly case-insensitive.")


def test_html_split_across_elements():
    """Test detection when words are split across multiple nested HTML tags."""
    print("Running Test: HTML Split Across Elements...")
    html = "<div><h1>Write</h1> <span>For</span> <strong>Us</strong></div>"
    result = detect_guest_post_opportunity(html)

    assert result.detected is True
    assert "write for us" in result.strong_signals

    print("  [PASS] Words split across tags detected accurately.")


def test_script_style_exclusion():
    """Test that mentions inside <script> and <style> tags do not trigger false detections."""
    print("Running Test: Script & Style Exclusion...")
    html = """
    <html>
        <head>
            <script>var action = "write for us";</script>
            <style>/* submit a guest post */</style>
        </head>
        <body>
            <p>Welcome to our tech news website. Here are today's latest updates.</p>
        </body>
    </html>
    """
    result = detect_guest_post_opportunity(html)

    assert result.detected is False
    assert result.confidence == 0
    assert len(result.strong_signals) == 0

    print("  [PASS] Script and style contents ignored by detector.")


def test_weak_signal_and_false_positive_protection():
    """Test that weak contextual words alone do NOT mark a site as accepting guest posts."""
    print("Running Test: False Positive Protection (Weak Signals)...")
    html = "<html><body><p>Our guest author published an interesting article about cloud storage.</p></body></html>"
    result = detect_guest_post_opportunity(html)

    assert result.detected is False
    assert result.confidence < 50
    assert len(result.strong_signals) == 0

    print("  [PASS] Weak contextual words avoided false positive classification.")


def test_negative_signal_detection():
    """Test detection when a page explicitly states guest posts are closed or not accepted."""
    print("Running Test: Negative Signal Detection...")
    html = "<html><body><p>We do not accept guest posts or unsolicited contributor submissions.</p></body></html>"
    result = detect_guest_post_opportunity(html)

    assert result.detected is False
    assert result.confidence == 0
    assert "we do not accept guest posts" in result.negative_signals

    print("  [PASS] Negative closed signals classified as not accepting.")


def test_positive_and_negative_conflict_resolution():
    """Test conflict handling when a page mentions guest posts but says submissions are closed."""
    print("Running Test: Positive & Negative Conflict Resolution...")
    html = """
    <html>
        <body>
            <h1>Write for Us</h1>
            <p>Welcome to our tech publication guidelines.</p>
            <p>Important Announcement: Guest post submissions are currently closed until further notice.</p>
        </body>
    </html>
    """
    result = detect_guest_post_opportunity(html)

    assert result.detected is False
    assert result.has_conflicts is True
    assert result.confidence == 20
    assert "write for us" in result.strong_signals
    assert "guest post submissions are closed" in result.negative_signals
    assert len(result.evidence_snippets) >= 1
    combined_evidence = " ".join(result.evidence_snippets).lower()
    assert "write for us" in combined_evidence
    assert "closed" in combined_evidence

    print("  [PASS] Conflicted signals resolved deterministically to negative.")


def test_no_signals():
    """Test clean negative result on standard article content with no contributor terms."""
    print("Running Test: No Signals (Standard Content)...")
    html = "<html><body><h1>Python Tutorial</h1><p>In this guide, we learn about list comprehensions.</p></body></html>"
    result = detect_guest_post_opportunity(html)

    assert result.detected is False
    assert result.confidence == 0
    assert len(result.all_positive_signals) == 0
    assert len(result.evidence_snippets) == 0

    print("  [PASS] Standard article content returns detected=False and 0 confidence.")


def test_evidence_bounding_and_snippets():
    """Test that extracted evidence snippets are bounded in count and size."""
    print("Running Test: Evidence Bounding & Context...")
    html = """
    <html>
        <body>
            <p>1. We are glad you want to write for us on our blog.</p>
            <p>2. Please check our guest post guidelines for formatting.</p>
            <p>3. Submit a guest post through the online editor.</p>
            <p>4. Become a contributor by filling out the form.</p>
            <p>5. Guest article guidelines require 1500+ words.</p>
            <p>6. Article submissions are reviewed weekly.</p>
        </body>
    </html>
    """
    result = detect_guest_post_opportunity(html)

    # Max 5 snippets allowed per spec
    assert 0 < len(result.evidence_snippets) <= 5
    for snip in result.evidence_snippets:
        assert len(snip) < 300
        assert "..." in snip or len(snip) > 0

    print("  [PASS] Evidence snippets extracted and strictly bounded.")


def test_duplicate_signals_deduplicated():
    """Test that identical phrases repeated across the page appear only once in signal list."""
    print("Running Test: Duplicate Signals Deduplication...")
    html = """
    <html>
        <body>
            <h1>Write for Us</h1>
            <p>Interested in tech? Write for us today!</p>
            <footer>Write for us footer link</footer>
        </body>
    </html>
    """
    result = detect_guest_post_opportunity(html)

    assert result.detected is True
    # "write for us" should only appear once in strong_signals
    assert result.strong_signals.count("write for us") == 1

    print("  [PASS] Repeated signals deduplicated in results list.")


def test_url_only_signal():
    """Test that a matching URL path alone does not produce positive detection without HTML signals."""
    print("Running Test: URL-Only Signal Protection...")
    html = "<html><body><h1>About Our Company</h1><p>We are a software development agency.</p></body></html>"
    result = detect_guest_post_opportunity(html, url="https://example.com/write-for-us")

    assert result.detected is False
    assert result.confidence <= 25
    assert result.url_signal_matched == "write-for-us"

    print("  [PASS] Matching URL without HTML body signals correctly rejected.")


def test_empty_and_malformed_html():
    """Test graceful handling of empty strings, None, and broken HTML."""
    print("Running Test: Empty & Malformed HTML...")
    res_none = detect_guest_post_opportunity(None)
    assert res_none.detected is False
    assert res_none.confidence == 0

    res_empty = detect_guest_post_opportunity("")
    assert res_empty.detected is False

    res_broken = detect_guest_post_opportunity("<<<broken<<<<tags><>>>Write For Us<<<<//>>")
    assert res_broken.detected is True
    assert "write for us" in res_broken.strong_signals

    print("  [PASS] Empty and broken HTML handled without exceptions.")


async def test_database_and_api_endpoint():
    """Test database persistence and FastAPI POST /api/websites/{id}/detect-guest-post endpoint."""
    print("Running Test: Database & FastAPI Endpoint Integration...")
    init_db()

    db = SessionLocal()
    try:
        test_domain = "detector-test.example.com"
        website = db.query(Website).filter_by(domain=test_domain).first()
        if not website:
            website = Website(
                domain=test_domain,
                url="https://detector-test.example.com/write-for-us",
                name="Detector Test Blog",
                crawl_status="success",
                html_content="<html><head><title>Guidelines</title></head><body><h1>Write For Us</h1><p>We accept guest contributions.</p></body></html>"
            )
            db.add(website)
            db.commit()
            db.refresh(website)

        web_id = website.id

        # Test service function
        updated_web, result = detect_guest_post_for_website(db=db, website_id=web_id)
        assert updated_web is not None
        assert result.detected is True

        # Verify GuestPostInformation in database
        gp_info = db.query(GuestPostInformation).filter_by(website_id=web_id).first()
        assert gp_info is not None
        assert gp_info.accepts_guest_posts is True
        assert gp_info.confidence >= 85
        assert gp_info.evidence is not None
        assert "write for us" in gp_info.evidence.lower()

        # Test FastAPI endpoint
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(f"/api/websites/{web_id}/detect-guest-post")
            assert res.status_code == 200
            data = res.json()
            assert data["website_id"] == web_id
            assert data["detected"] is True
            assert data["confidence"] >= 85
            assert "write for us" in data["strong_signals"]

        print(f"  [PASS] Guest post detection persisted to GuestPostInformation for Website #{web_id}.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 13: GUEST POST DETECTION TEST SUITE")
    print("=" * 60)

    test_html_normalization_and_tag_stripping()
    test_strong_positive_detection()
    test_multiple_positive_signals()
    test_case_insensitive_matching()
    test_html_split_across_elements()
    test_script_style_exclusion()
    test_weak_signal_and_false_positive_protection()
    test_negative_signal_detection()
    test_positive_and_negative_conflict_resolution()
    test_no_signals()
    test_evidence_bounding_and_snippets()
    test_duplicate_signals_deduplicated()
    test_url_only_signal()
    test_empty_and_malformed_html()
    await test_database_and_api_endpoint()

    print("=" * 60)
    print("ALL STEP 13 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
