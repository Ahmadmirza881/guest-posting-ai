"""Comprehensive Test Suite for Step 15: AI Semantic Verification (Gemini).

Validates Gemini LLM semantic verification, cross-validation of Steps 13 & 14 deterministic outputs,
anti-hallucination guarantees, error handling, missing API key handling, malformed responses,
and database persistence with 100% mocked API calls without network dependencies.
"""

import asyncio
import json
from unittest.mock import AsyncMock
import httpx

from app.database import init_db, SessionLocal
from app.models import Website, GuestPostInformation
from app.services.ai_verifier import (
    AIVerificationInput,
    AIVerificationResult,
    verify_guest_post_opportunity,
    verify_website_record,
    call_gemini_api,
    build_verification_prompt,
    GeminiAPIError,
)
from app.main import app


def build_mock_gemini_client(response_dict: dict, status_code: int = 200) -> AsyncMock:
    """Create an AsyncMock httpx client simulating Google Gemini REST API responses."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.text = json.dumps(response_dict)

    # Structure matches Google Generative Language API
    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(response_dict)
                        }
                    ]
                }
            }
        ]
    }
    mock_resp.json.return_value = gemini_payload
    mock_client.post.return_value = mock_resp
    return mock_client


async def test_verified_positive_opportunity():
    """Test AI verification of an active, authentic guest-post opportunity."""
    print("Running Test: Verified Positive Guest-Post Opportunity...")

    mock_ai_output = {
        "verification_status": "verified",
        "accepts_guest_posts": True,
        "confidence": 95,
        "reason": "The page provides explicit contributor guidelines and an active submission email.",
        "guest_post_evidence": "We welcome guest authors to submit articles to our tech blog.",
        "submission_method": "email",
        "submission_email": "submissions@techblog.org",
        "submission_url": "https://techblog.org/guidelines",
        "guidelines_url": "https://techblog.org/guidelines",
        "pricing": "free",
        "corrections": []
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIVerificationInput(
        website_url="https://techblog.org/write-for-us",
        page_title="Write For Us Guidelines",
        cleaned_page_text="We welcome guest authors to submit articles to our tech blog at submissions@techblog.org.",
        step13_detected=True,
        step13_confidence=90,
        step13_signals=["write for us", "guest author"],
        step13_evidence=["...We welcome guest authors..."],
        step14_submission_methods=["email"],
        step14_email="submissions@techblog.org",
        step14_guidelines_url="https://techblog.org/guidelines",
        step14_pricing="free"
    )

    result = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.verification_status == "verified"
    assert result.accepts_guest_posts is True
    assert result.confidence == 95
    assert result.submission_email == "submissions@techblog.org"
    assert result.pricing == "free"

    print("  [PASS] Positive opportunity successfully verified with high confidence.")


async def test_explicit_rejection_verification():
    """Test AI verification correctly rejecting a page that closed submissions."""
    print("Running Test: Explicit Rejection Verification...")

    mock_ai_output = {
        "verification_status": "rejected",
        "accepts_guest_posts": False,
        "confidence": 92,
        "reason": "The page explicitly states that guest post submissions are closed until next year.",
        "guest_post_evidence": "Guest post submissions are currently closed until further notice.",
        "submission_method": None,
        "submission_email": None,
        "submission_url": None,
        "guidelines_url": None,
        "pricing": None,
        "corrections": ["Deterministic detector had flagged keywords, but submissions are closed."]
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIVerificationInput(
        website_url="https://techblog.org/write-for-us",
        page_title="Write For Us",
        cleaned_page_text="Write For Us. Notice: Guest post submissions are currently closed until further notice.",
        step13_detected=False,
        step13_confidence=20,
        step13_signals=["write for us", "guest post submissions are closed"],
        step13_evidence=["...Guest post submissions are currently closed..."],
        step14_submission_methods=[]
    )

    result = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.verification_status == "rejected"
    assert result.accepts_guest_posts is False
    assert result.submission_email is None

    print("  [PASS] Closed submissions correctly verified as rejected.")


async def test_uncertain_and_ambiguous_case():
    """Test AI verification returning uncertain when content is ambiguous."""
    print("Running Test: Uncertain & Ambiguous Case...")

    mock_ai_output = {
        "verification_status": "uncertain",
        "accepts_guest_posts": None,
        "confidence": 40,
        "reason": "The article discusses the concept of guest posting in SEO without offering a submission channel.",
        "guest_post_evidence": None,
        "submission_method": None,
        "submission_email": None,
        "submission_url": None,
        "guidelines_url": None,
        "pricing": None,
        "corrections": []
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIVerificationInput(
        website_url="https://seo-guide.com/guest-posting-tips",
        page_title="How to Guest Post in 2026",
        cleaned_page_text="In this tutorial we discuss how guest posting helps link building.",
        step13_detected=False,
        step13_confidence=35,
        step13_signals=["guest posting"],
        step13_evidence=["...discuss how guest posting helps..."],
        step14_submission_methods=[]
    )

    result = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.verification_status == "uncertain"
    assert result.accepts_guest_posts is None
    assert result.confidence == 40

    print("  [PASS] Ambiguous informational content classified as uncertain.")


async def test_past_byline_mention_rejection():
    """Test rejection when text only contains a past guest author byline."""
    print("Running Test: Past Byline Mention Rejection...")

    mock_ai_output = {
        "verification_status": "rejected",
        "accepts_guest_posts": False,
        "confidence": 88,
        "reason": "The page merely credits a guest author on a published article and does not invite guest post submissions.",
        "guest_post_evidence": "Written by guest author Alex Smith.",
        "submission_method": None,
        "submission_email": None,
        "submission_url": None,
        "guidelines_url": None,
        "pricing": None,
        "corrections": ["Extracted email alex@smith.com was an author personal contact, not a submission channel."]
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIVerificationInput(
        website_url="https://news.com/article-123",
        page_title="AI in Healthcare",
        cleaned_page_text="Written by guest author Alex Smith. Contact alex@smith.com.",
        step13_detected=False,
        step13_confidence=45,
        step13_signals=["guest author"],
        step13_evidence=["...Written by guest author..."],
        step14_submission_methods=["email"],
        step14_email="alex@smith.com"
    )

    result = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.verification_status == "rejected"
    assert result.accepts_guest_posts is False
    assert result.submission_email is None

    print("  [PASS] Past guest author byline correctly rejected.")


async def test_anti_hallucination_empty_fields():
    """Test that missing fields are strictly returned as None without hallucination."""
    print("Running Test: Anti-Hallucination Null Fields Guarantee...")

    mock_ai_output = {
        "verification_status": "verified",
        "accepts_guest_posts": True,
        "confidence": 85,
        "reason": "Write for us page verified, but no email or price is listed.",
        "guest_post_evidence": "We accept guest articles via our online submission form.",
        "submission_method": "form",
        "submission_email": None,
        "submission_url": "https://example.com/submit",
        "guidelines_url": None,
        "pricing": None,
        "corrections": []
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIVerificationInput(
        website_url="https://example.com/write",
        page_title="Write For Us",
        cleaned_page_text="We accept guest articles via our online submission form at https://example.com/submit.",
        step13_detected=True,
        step13_confidence=85,
        step13_signals=["write for us"],
        step13_evidence=["...accept guest articles..."],
        step14_submission_methods=["form"],
        step14_submission_url="https://example.com/submit"
    )

    result = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.submission_email is None
    assert result.pricing is None
    assert result.guidelines_url is None
    assert result.submission_url == "https://example.com/submit"

    print("  [PASS] Unstated fields returned as None without hallucinated placeholders.")


async def test_malformed_gemini_response_handling():
    """Test graceful fallback when Gemini returns malformed non-JSON output."""
    print("Running Test: Malformed Gemini Response Handling...")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "I am an AI and this is not valid JSON."}]
                }
            }
        ]
    }
    mock_client.post.return_value = mock_resp

    input_data = AIVerificationInput(
        website_url="https://example.com",
        cleaned_page_text="Sample text",
        step13_detected=True,
        step13_confidence=80
    )

    result = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.verification_status == "uncertain"
    assert result.confidence == 0
    assert "AI verification unavailable" in result.reason or "error" in result.reason.lower()

    print("  [PASS] Malformed model output handled cleanly with uncertain status.")


async def test_api_failure_and_missing_key_handling():
    """Test graceful handling of Gemini API 500 errors and missing API keys."""
    print("Running Test: API Failure & Missing Key Handling...")

    # Case 1: Missing API Key
    input_data = AIVerificationInput(
        website_url="https://example.com",
        cleaned_page_text="Sample text",
        step13_detected=True,
        step13_confidence=80
    )
    res_no_key = await verify_guest_post_opportunity(
        input_data=input_data,
        api_key=None
    )
    assert res_no_key.verification_status == "uncertain"
    assert res_no_key.confidence == 0

    # Case 2: API 500 Error
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_client.post.return_value = mock_resp

    res_500 = await verify_guest_post_opportunity(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )
    assert res_500.verification_status == "uncertain"
    assert res_500.confidence == 0

    print("  [PASS] Missing API key and HTTP 500 errors handled gracefully.")


async def test_database_and_api_endpoint():
    """Test database persistence and FastAPI POST /api/websites/{id}/verify endpoint."""
    print("Running Test: Database & FastAPI Endpoint Integration...")
    init_db()

    db = SessionLocal()
    try:
        test_domain = "ai-verification-test.example.com"
        website = db.query(Website).filter_by(domain=test_domain).first()
        if not website:
            sample_html = """
            <html>
                <head><title>Tech Journal Write For Us</title></head>
                <body>
                    <h1>Write For Us</h1>
                    <p>We welcome guest articles from tech enthusiasts. Email your pitch to submissions@ai-verification-test.example.com.</p>
                </body>
            </html>
            """
            website = Website(
                domain=test_domain,
                url="https://ai-verification-test.example.com/write-for-us",
                name="AI Verification Test Journal",
                crawl_status="success",
                html_content=sample_html
            )
            db.add(website)
            db.commit()
            db.refresh(website)

        web_id = website.id

        mock_ai_output = {
            "verification_status": "verified",
            "accepts_guest_posts": True,
            "confidence": 95,
            "reason": "Verified active contributor invitation with editorial submission email.",
            "guest_post_evidence": "We welcome guest articles from tech enthusiasts.",
            "submission_method": "email",
            "submission_email": "submissions@ai-verification-test.example.com",
            "submission_url": None,
            "guidelines_url": "https://ai-verification-test.example.com/write-for-us",
            "pricing": "free",
            "corrections": []
        }
        mock_client = build_mock_gemini_client(mock_ai_output)

        updated_web, result = await verify_website_record(
            db=db,
            website_id=web_id,
            client=mock_client,
            api_key="fake-test-key"
        )

        assert updated_web is not None
        assert result.verification_status == "verified"
        assert result.confidence == 95

        # Check database persistence
        gp_info = db.query(GuestPostInformation).filter_by(website_id=web_id).first()
        assert gp_info is not None
        assert gp_info.verification_status == "verified"
        assert gp_info.ai_confidence == 95
        assert gp_info.ai_reason is not None
        assert gp_info.verified_at is not None
        assert gp_info.accepts_guest_posts is True

        # Test FastAPI endpoint
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Endpoint test (will fallback to uncertain if no key in env, or verify)
            res = await client.post(f"/api/websites/{web_id}/verify")
            assert res.status_code == 200
            data = res.json()
            assert data["website_id"] == web_id
            assert "verification_status" in data

        print(f"  [PASS] AI Verification persisted to GuestPostInformation for Website #{web_id}.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 15: AI SEMANTIC VERIFICATION TEST SUITE")
    print("=" * 60)

    await test_verified_positive_opportunity()
    await test_explicit_rejection_verification()
    await test_uncertain_and_ambiguous_case()
    await test_past_byline_mention_rejection()
    await test_anti_hallucination_empty_fields()
    await test_malformed_gemini_response_handling()
    await test_api_failure_and_missing_key_handling()
    await test_database_and_api_endpoint()

    print("=" * 60)
    print("ALL STEP 15 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
