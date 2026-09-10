"""Comprehensive Test Suite for Step 14: Submission Information Extraction.

Validates deterministic extraction of submission emails, submission form URLs (including Google Forms
and Typeform), guidelines URLs, submission methods, explicit paid/free pricing, and contextual evidence.
All tests run with local/mocked HTML fixtures without external network dependencies.
"""

import asyncio
import httpx

from app.database import init_db, SessionLocal
from app.models import Website, GuestPostInformation
from app.services.submission_extractor import (
    extract_submission_information,
    extract_and_save_submission_info,
    extract_html_links_and_forms,
    extract_submission_emails,
    SubmissionExtractionResult,
)
from app.main import app


def test_email_extraction_and_ranking():
    """Test extraction of submission emails from plain text and mailto links, while ignoring generic emails."""
    print("Running Test: Email Extraction & Ranking...")

    html = """
    <html>
        <body>
            <p>For privacy matters contact privacy@techblog.com.</p>
            <p>To submit your guest post draft, please email our editorial team at submissions@techblog.com or editor@techblog.com.</p>
            <a href="mailto:write@techblog.com?subject=Guest%20Post%20Pitch">Pitch Us by Email</a>
        </body>
    </html>
    """
    result = extract_submission_information(html, base_url="https://techblog.com")

    assert "email" in result.submission_methods
    assert "submissions@techblog.com" in result.submission_emails
    assert "write@techblog.com" in result.submission_emails
    # Privacy email should NOT be prioritized or marked as submission email
    assert "privacy@techblog.com" not in result.submission_emails[:2]
    assert len(result.evidence_snippets) > 0

    print("  [PASS] Submission emails extracted, ranked, and generic emails filtered.")


def test_google_forms_and_typeform_detection():
    """Test extraction and categorization of external Google Forms and Typeform URLs."""
    print("Running Test: Google Forms & Typeform Detection...")

    html = """
    <html>
        <body>
            <h1>Guest Author Application</h1>
            <p>Please submit your article pitch using our <a href="https://docs.google.com/forms/d/e/1FAIpQLSc12345/viewform">Google Submission Form</a>.</p>
            <p>Alternatively, fill out our <a href="https://example.typeform.com/to/xyz789">Typeform Questionnaire</a>.</p>
        </body>
    </html>
    """
    result = extract_submission_information(html, base_url="https://example.com/write-for-us")

    assert "google_form" in result.submission_methods
    assert "typeform" in result.submission_methods
    assert "https://docs.google.com/forms/d/e/1FAIpQLSc12345/viewform" in result.submission_urls
    assert "https://example.typeform.com/to/xyz789" in result.submission_urls
    assert result.has_submission_channel is True

    print("  [PASS] Google Forms and Typeform detected with appropriate submission methods.")


def test_submission_form_and_guidelines_url_resolution():
    """Test extraction of relative submission links and guidelines URLs."""
    print("Running Test: Submission Form & Guidelines URLs Resolution...")

    html = """
    <html>
        <body>
            <h1>Editorial Guidelines</h1>
            <p>Review our <a href="/contributor-guidelines">Detailed Contributor Guidelines</a> before writing.</p>
            <p>Ready to send? Go to our <a href="/submit-article">Online Article Submission Form</a>.</p>
        </body>
    </html>
    """
    base_url = "https://techjournal.org/writers"
    result = extract_submission_information(html, base_url=base_url)

    assert "https://techjournal.org/submit-article" in result.submission_urls
    assert "https://techjournal.org/contributor-guidelines" in result.guidelines_urls
    assert "form" in result.submission_methods

    print("  [PASS] Relative submission and guidelines URLs resolved to absolute links.")


def test_explicit_free_pricing_detection():
    """Test detection of explicit free guest post policy."""
    print("Running Test: Explicit Free Pricing Detection...")

    html = """
    <html>
        <body>
            <h1>Guest Posting Policy</h1>
            <p>We welcome high-quality content. We accept free guest posts with no publishing fees.</p>
        </body>
    </html>
    """
    result = extract_submission_information(html)

    assert result.pricing_model == "free"
    assert result.is_paid is False
    assert result.price_amount is None

    print("  [PASS] Free submission policy detected accurately.")


def test_explicit_paid_pricing_and_amount_extraction():
    """Test detection of paid sponsored posts and currency amount extraction."""
    print("Running Test: Explicit Paid Pricing & Currency Amount...")

    # Case 1: Dollar price with per article suffix
    html_usd = """
    <html>
        <body>
            <h1>Sponsored Post Guidelines</h1>
            <p>All commercial articles are subject to a publishing fee of $150 per article.</p>
        </body>
    </html>
    """
    res_usd = extract_submission_information(html_usd)
    assert res_usd.pricing_model == "paid"
    assert res_usd.is_paid is True
    assert res_usd.price_amount is not None
    assert "$150" in res_usd.price_amount

    # Case 2: Euro pricing
    html_eur = """
    <html>
        <body>
            <h1>Editorial Insertion Fee</h1>
            <p>Paid guest posts incur an editorial review charge of €75.</p>
        </body>
    </html>
    """
    res_eur = extract_submission_information(html_eur)
    assert res_eur.pricing_model == "paid"
    assert res_eur.is_paid is True
    assert res_eur.price_amount is not None
    assert "€75" in res_eur.price_amount

    # Case 3: Sponsored wording without explicit price amount
    html_sponsored = """
    <html>
        <body>
            <h1>Sponsored Articles</h1>
            <p>We accept sponsored posts from SaaS and technology brands.</p>
        </body>
    </html>
    """
    res_sponsored = extract_submission_information(html_sponsored)
    assert res_sponsored.pricing_model == "paid"
    assert res_sponsored.is_paid is True
    assert res_sponsored.price_amount is None  # Must NOT invent a price

    print("  [PASS] Paid status, explicit prices ($150, €75), and unpriced sponsored posts handled correctly.")


def test_html_tag_stripping_and_split_elements():
    """Test that text split across HTML tags and nested markup is parsed cleanly."""
    print("Running Test: HTML Split Elements & Clean Text Parsing...")

    html = """
    <div>
        <h2>Submit</h2>
        <span>Your</span>
        <strong>Guest Post</strong>
        <p>Send your draft to <a href="mailto:pitch@split-elements.org">pitch@split-elements.org</a></p>
    </div>
    """
    result = extract_submission_information(html)

    assert "pitch@split-elements.org" in result.submission_emails
    assert "email" in result.submission_methods

    print("  [PASS] Split elements and nested HTML parsed without loss of context.")


def test_script_and_style_exclusion():
    """Test that emails and forms inside <script> and <style> tags are ignored."""
    print("Running Test: Script & Style Exclusion...")

    html = """
    <html>
        <head>
            <script>var support_email = "hidden_script@example.com";</script>
            <style>/* a[href="https://fake-form.com"] */</style>
        </head>
        <body>
            <p>General tech news article with no submissions.</p>
        </body>
    </html>
    """
    result = extract_submission_information(html)

    assert "hidden_script@example.com" not in result.submission_emails
    assert len(result.submission_urls) == 0

    print("  [PASS] Scripts and styles excluded from extraction.")


def test_false_positive_protection_on_unrelated_pages():
    """Test that generic contact info on unrelated pages does not trigger guest post submission channels."""
    print("Running Test: False Positive Protection on Generic Pages...")

    html = """
    <html>
        <body>
            <h1>About Our Consulting Firm</h1>
            <p>Contact us at info@consulting.com for sales inquiries or fill out our general contact form at /contact.</p>
            <p>Privacy inquiries: privacy@consulting.com</p>
        </body>
    </html>
    """
    result = extract_submission_information(html, base_url="https://consulting.com")

    # Should not produce submission URLs for general contact unless guest-post related
    assert not any("google_form" in m or "typeform" in m for m in result.submission_methods)
    assert result.pricing_model == "unknown"

    print("  [PASS] Generic corporate contact page prevented from generating guest post submission channels.")


def test_empty_and_malformed_html():
    """Test extraction behavior with empty strings, None, and broken HTML."""
    print("Running Test: Empty & Malformed HTML...")

    res_none = extract_submission_information(None)
    assert res_none.has_submission_channel is False

    res_empty = extract_submission_information("")
    assert res_empty.has_submission_channel is False

    res_broken = extract_submission_information("<<<broken<<<<tags><a href='mailto:broken@test.com'>Submit Draft</a>")
    assert "broken@test.com" in res_broken.submission_emails

    print("  [PASS] Empty and broken HTML handled safely without errors.")


async def test_database_and_api_endpoint():
    """Test database persistence and FastAPI POST /api/websites/{id}/extract-submission endpoint."""
    print("Running Test: Database & FastAPI Endpoint Integration...")
    init_db()

    db = SessionLocal()
    try:
        test_domain = "submission-test-site.example.com"
        website = db.query(Website).filter_by(domain=test_domain).first()
        if not website:
            sample_html = """
            <html>
                <head><title>Write For Us</title></head>
                <body>
                    <h1>Contributor Guidelines</h1>
                    <p>We welcome tech writers. Submit your draft to <a href="mailto:submissions@submission-test-site.example.com">submissions@submission-test-site.example.com</a>.</p>
                    <p>You can also use our <a href="https://docs.google.com/forms/d/e/sample-form-123/viewform">Google Form</a>.</p>
                    <p>Sponsored post rate is $120 per article.</p>
                    <a href="https://submission-test-site.example.com/guidelines">Detailed Guidelines</a>
                </body>
            </html>
            """
            website = Website(
                domain=test_domain,
                url="https://submission-test-site.example.com/write-for-us",
                name="Submission Test Site",
                crawl_status="success",
                html_content=sample_html
            )
            db.add(website)
            db.commit()
            db.refresh(website)

        web_id = website.id

        # Test service function
        updated_web, result = extract_and_save_submission_info(db=db, website_id=web_id)
        assert updated_web is not None
        assert result.primary_email == "submissions@submission-test-site.example.com"
        assert result.primary_submission_url == "https://docs.google.com/forms/d/e/sample-form-123/viewform"
        assert result.price_amount == "$120 per article" or "$120" in (result.price_amount or "")
        assert "email" in result.submission_methods
        assert "google_form" in result.submission_methods

        # Verify GuestPostInformation in database
        gp_info = db.query(GuestPostInformation).filter_by(website_id=web_id).first()
        assert gp_info is not None
        assert gp_info.contact_email == "submissions@submission-test-site.example.com"
        assert gp_info.submission_url == "https://docs.google.com/forms/d/e/sample-form-123/viewform"
        assert gp_info.pricing is not None
        assert "$120" in gp_info.pricing
        assert "google_form" in gp_info.submission_method

        # Test FastAPI endpoint
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(f"/api/websites/{web_id}/extract-submission")
            assert res.status_code == 200
            data = res.json()
            assert data["website_id"] == web_id
            assert data["primary_email"] == "submissions@submission-test-site.example.com"
            assert data["primary_submission_url"] == "https://docs.google.com/forms/d/e/sample-form-123/viewform"
            assert data["is_paid"] is True
            assert "$120" in (data["price_amount"] or "")

        print(f"  [PASS] Extracted submission info persisted in GuestPostInformation for Website #{web_id}.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 14: SUBMISSION INFORMATION EXTRACTION TEST SUITE")
    print("=" * 60)

    test_email_extraction_and_ranking()
    test_google_forms_and_typeform_detection()
    test_submission_form_and_guidelines_url_resolution()
    test_explicit_free_pricing_detection()
    test_explicit_paid_pricing_and_amount_extraction()
    test_html_tag_stripping_and_split_elements()
    test_script_and_style_exclusion()
    test_false_positive_protection_on_unrelated_pages()
    test_empty_and_malformed_html()
    await test_database_and_api_endpoint()

    print("=" * 60)
    print("ALL STEP 14 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
