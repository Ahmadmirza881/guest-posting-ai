"""Comprehensive Test Suite for Step 16: AI Semantic Website Analysis (Gemini).

Validates Gemini LLM website niche detection, content quality analysis, keyword relevance,
trust signals, editorial standards, score clamping, anti-hallucination guarantees, error handling,
missing API key handling, malformed responses, and database persistence with 100% mocked API calls.
"""

import asyncio
import json
from unittest.mock import AsyncMock
import httpx

from app.database import init_db, SessionLocal
from app.models import Website, WebsiteAnalysis, Search, SearchResult
from app.services.ai_analyzer import (
    AIAnalysisInput,
    AIAnalysisResult,
    analyze_website_content,
    analyze_website_record,
    build_analysis_prompt,
    clamp_score,
)
from app.main import app


def build_mock_gemini_client(response_dict: dict, status_code: int = 200) -> AsyncMock:
    """Create an AsyncMock httpx client simulating Google Gemini REST API responses."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.text = json.dumps(response_dict)

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


def test_score_clamping():
    """Test score clamping and normalization helper."""
    print("Running Test: Score Clamping & Normalization...")
    assert clamp_score(95) == 95
    assert clamp_score(150) == 100
    assert clamp_score(-20) == 0
    assert clamp_score("85") == 85
    assert clamp_score(None, default=0) == 0
    assert clamp_score("invalid", default=50) == 50
    print("  [PASS] Score clamping normalizes all inputs safely to 0-100.")


async def test_positive_niche_and_relevant_website():
    """Test AI analysis of a highly relevant website with clear niche and topics."""
    print("Running Test: Positive Analysis & Relevant Website...")

    mock_ai_output = {
        "primary_niche": "Artificial Intelligence",
        "topics": ["Machine Learning", "Deep Learning", "Neural Networks", "NLP"],
        "niche_confidence": 95,
        "relevance_score": 92,
        "relevance_reason": "The website focuses deeply on artificial intelligence research and applications, exactly matching the search keyword.",
        "content_quality_score": 88,
        "content_quality_reason": "High-depth technical articles with clear structure, code snippets, and citations.",
        "trust_signals": ["Author bylines with PhD credentials", "About page with editorial board", "Contact email listed"],
        "editorial_standards": ["Peer review process", "Strict original research requirements"],
        "strengths": ["Deep domain expertise", "Consistent publishing schedule", "Active author community"],
        "weaknesses": ["Advanced topics may be inaccessible to beginners"],
        "analysis_confidence": 90,
        "evidence": ["We publish state-of-the-art AI research and practical machine learning tutorials."],
        "warnings": []
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIAnalysisInput(
        website_url="https://ai-insights.org",
        domain="ai-insights.org",
        page_title="AI Insights — Deep Learning Journal",
        search_keyword="Artificial Intelligence",
        cleaned_page_text="We publish state-of-the-art AI research and practical machine learning tutorials written by verified PhD researchers.",
        step13_detected=True,
        step13_confidence=90,
        step15_status="verified",
        step15_confidence=95
    )

    result = await analyze_website_content(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.primary_niche == "Artificial Intelligence"
    assert "Machine Learning" in result.topics
    assert result.relevance_score == 92
    assert result.content_quality_score == 88
    assert len(result.trust_signals) == 3
    assert len(result.strengths) >= 1
    assert result.analysis_status == "completed"

    print("  [PASS] Highly relevant AI website analyzed accurately.")


async def test_irrelevant_website_analysis():
    """Test AI analysis of a website whose niche does not match the search keyword."""
    print("Running Test: Irrelevant Website Niche Matching...")

    mock_ai_output = {
        "primary_niche": "Home Gardening & Landscaping",
        "topics": ["Organic Gardening", "Plant Care", "Lawn Maintenance"],
        "niche_confidence": 90,
        "relevance_score": 15,
        "relevance_reason": "The website covers gardening and landscaping, which is not relevant to the searched keyword 'Cloud Computing'.",
        "content_quality_score": 75,
        "content_quality_reason": "Decent gardening how-to guides, but irrelevant to enterprise IT.",
        "trust_signals": ["Author bio on about page"],
        "editorial_standards": ["Standard submission guidelines"],
        "strengths": ["Well-organized plant guides"],
        "weaknesses": ["Zero coverage of tech or cloud computing"],
        "analysis_confidence": 85,
        "evidence": ["Your guide to organic gardening and backyard flowers."],
        "warnings": ["Mismatched niche relative to search keyword."]
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIAnalysisInput(
        website_url="https://green-gardens.example.com",
        domain="green-gardens.example.com",
        page_title="Green Gardens Blog",
        search_keyword="Cloud Computing",
        cleaned_page_text="Your guide to organic gardening and backyard flowers. Tips for planting roses and growing tomatoes.",
        step13_detected=False,
        step13_confidence=20
    )

    result = await analyze_website_content(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.primary_niche == "Home Gardening & Landscaping"
    assert result.relevance_score == 15
    assert "irrelevant" in result.relevance_reason.lower() or "not relevant" in result.relevance_reason.lower()

    print("  [PASS] Irrelevant niche accurately identified with low relevance score.")


async def test_poor_and_limited_content():
    """Test AI analysis when website has insufficient or empty text."""
    print("Running Test: Poor & Limited Content Fallback...")

    input_data = AIAnalysisInput(
        website_url="https://empty-site.com",
        domain="empty-site.com",
        page_title="Empty Site",
        search_keyword="Marketing",
        cleaned_page_text=""
    )

    result = await analyze_website_content(
        input_data=input_data,
        api_key="fake-test-key"
    )

    assert result.primary_niche is None
    assert result.analysis_status == "failed"
    assert result.relevance_score == 0
    assert result.content_quality_score == 0

    print("  [PASS] Empty content safely handled with failed status.")


async def test_trust_signals_and_editorial_standards():
    """Test detailed extraction of trust signals and editorial guidelines."""
    print("Running Test: Trust Signals & Editorial Standards Extraction...")

    mock_ai_output = {
        "primary_niche": "Fintech & Personal Finance",
        "topics": ["Investing", "Cryptocurrency", "Retirement"],
        "niche_confidence": 92,
        "relevance_score": 85,
        "relevance_reason": "Strong focus on personal finance matching 'Financial Advice' query.",
        "content_quality_score": 90,
        "content_quality_reason": "In-depth financial analysis with verified data tables and disclaimer notices.",
        "trust_signals": [
            "Certified Financial Planner (CFP) review disclosure",
            "SEC compliance disclaimer present",
            "Full corporate contact address in footer"
        ],
        "editorial_standards": [
            "Strict editorial independence policy",
            "Advertiser disclosure guidelines",
            "Mandatory source fact-checking"
        ],
        "strengths": ["High trust disclosure", "Expert contributor oversight"],
        "weaknesses": [],
        "analysis_confidence": 94,
        "evidence": ["All investment articles are reviewed by a Certified Financial Planner."],
        "warnings": []
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIAnalysisInput(
        website_url="https://smart-money.org",
        domain="smart-money.org",
        page_title="Smart Money Advisory",
        search_keyword="Financial Advice",
        cleaned_page_text="All investment articles are reviewed by a Certified Financial Planner. SEC disclosure and full contact address available.",
        step13_detected=True,
        step13_confidence=85
    )

    result = await analyze_website_content(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert len(result.trust_signals) == 3
    assert any("CFP" in s or "Certified" in s for s in result.trust_signals)
    assert len(result.editorial_standards) == 3
    assert result.content_quality_score == 90

    print("  [PASS] Trust signals and editorial standards extracted cleanly.")


async def test_anti_hallucination_empty_fields():
    """Test that missing or unsupported information returns None/empty lists without hallucination."""
    print("Running Test: Anti-Hallucination & Empty Fields Guarantee...")

    mock_ai_output = {
        "primary_niche": None,
        "topics": [],
        "niche_confidence": 0,
        "relevance_score": 30,
        "relevance_reason": "Page contains a generic greeting without enough text to establish a specific niche.",
        "content_quality_score": 40,
        "content_quality_reason": "Minimal text.",
        "trust_signals": [],
        "editorial_standards": [],
        "strengths": [],
        "weaknesses": ["No visible author info", "No editorial guidelines"],
        "analysis_confidence": 40,
        "evidence": [],
        "warnings": []
    }
    mock_client = build_mock_gemini_client(mock_ai_output)

    input_data = AIAnalysisInput(
        website_url="https://minimal.com",
        domain="minimal.com",
        page_title="Welcome",
        search_keyword="Technology",
        cleaned_page_text="Welcome to our website. We write about various things occasionally.",
        step13_detected=False
    )

    result = await analyze_website_content(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.primary_niche is None
    assert result.topics == []
    assert result.trust_signals == []
    assert result.editorial_standards == []

    print("  [PASS] Unsupported facts returned as empty/null without hallucinated filler.")


async def test_malformed_json_handling():
    """Test graceful fallback when Gemini returns broken non-JSON text."""
    print("Running Test: Malformed Gemini JSON Handling...")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "Not valid JSON output."}]}}
        ]
    }
    mock_client.post.return_value = mock_resp

    input_data = AIAnalysisInput(
        website_url="https://example.com",
        domain="example.com",
        cleaned_page_text="Sample text content for analysis."
    )

    result = await analyze_website_content(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )

    assert result.analysis_status == "failed"
    assert result.relevance_score == 0
    assert result.content_quality_score == 0

    print("  [PASS] Malformed JSON handled safely without exceptions.")


async def test_api_failure_and_missing_key():
    """Test graceful handling of Gemini HTTP 500 errors and missing API keys."""
    print("Running Test: API Failure & Missing Key Handling...")

    input_data = AIAnalysisInput(
        website_url="https://example.com",
        domain="example.com",
        cleaned_page_text="Sample text content for analysis."
    )

    # 1. Missing API Key
    res_no_key = await analyze_website_content(input_data=input_data, api_key=None)
    assert res_no_key.analysis_status == "failed"

    # 2. HTTP 500 Error
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_client.post.return_value = mock_resp

    res_500 = await analyze_website_content(
        input_data=input_data,
        client=mock_client,
        api_key="fake-test-key"
    )
    assert res_500.analysis_status == "failed"

    print("  [PASS] Missing API key and HTTP 500 handled cleanly.")


async def test_database_and_fastapi_endpoint():
    """Test database persistence and FastAPI POST /api/websites/{id}/analyze endpoint."""
    print("Running Test: Database & FastAPI Endpoint Integration...")
    init_db()

    db = SessionLocal()
    try:
        test_domain = "ai-analyzer-test.example.com"
        website = db.query(Website).filter_by(domain=test_domain).first()
        if not website:
            sample_html = """
            <html>
                <head><title>Cloud DevOps Engineering Portal</title></head>
                <body>
                    <h1>Kubernetes and Cloud Infrastructure</h1>
                    <p>Comprehensive guides on Terraform, AWS architectures, and CI/CD automation pipelines.</p>
                    <p>Written by Senior Site Reliability Engineers.</p>
                </body>
            </html>
            """
            website = Website(
                domain=test_domain,
                url="https://ai-analyzer-test.example.com/devops",
                name="Cloud DevOps Portal",
                crawl_status="success",
                html_content=sample_html
            )
            db.add(website)
            db.commit()
            db.refresh(website)

        web_id = website.id

        # Associate with a Search keyword
        search = Search(keyword="DevOps and Kubernetes", requested_website_count=50, status="completed")
        db.add(search)
        db.commit()
        db.refresh(search)

        sr = SearchResult(search_id=search.id, website_id=web_id, status="discovered")
        db.add(sr)
        db.commit()

        mock_ai_output = {
            "primary_niche": "DevOps & Cloud Engineering",
            "topics": ["Kubernetes", "AWS", "Terraform", "CI/CD"],
            "niche_confidence": 95,
            "relevance_score": 94,
            "relevance_reason": "Deep technical coverage of Kubernetes and DevOps matching search keyword.",
            "content_quality_score": 90,
            "content_quality_reason": "Professional infrastructure engineering guides with clear technical depth.",
            "trust_signals": ["Written by Senior SREs", "Architecture code samples provided"],
            "editorial_standards": ["Technical review by platform engineers"],
            "strengths": ["Enterprise-grade engineering guides", "Strong practical focus"],
            "weaknesses": [],
            "analysis_confidence": 92,
            "evidence": ["Comprehensive guides on Terraform, AWS architectures, and CI/CD automation pipelines."],
            "warnings": []
        }
        mock_client = build_mock_gemini_client(mock_ai_output)

        updated_web, result = await analyze_website_record(
            db=db,
            website_id=web_id,
            search_keyword="DevOps and Kubernetes",
            client=mock_client,
            api_key="fake-test-key"
        )

        assert updated_web is not None
        assert result.primary_niche == "DevOps & Cloud Engineering"
        assert result.relevance_score == 94
        assert result.content_quality_score == 90

        # Check database persistence in WebsiteAnalysis table
        wa = db.query(WebsiteAnalysis).filter_by(website_id=web_id).first()
        assert wa is not None
        assert wa.primary_niche == "DevOps & Cloud Engineering"
        assert wa.relevance_score == 94
        assert wa.content_quality_score == 90
        assert "Kubernetes" in wa.topics
        assert wa.analyzed_at is not None

        # Test FastAPI endpoint with patched Gemini call
        from unittest.mock import patch
        with patch("app.services.ai_analyzer.call_gemini_api", new=AsyncMock(return_value=mock_ai_output)):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(f"/api/websites/{web_id}/analyze?keyword=DevOps")
                assert res.status_code == 200
                data = res.json()
                assert data["website_id"] == web_id
                assert "primary_niche" in data
                assert data["primary_niche"] == "DevOps & Cloud Engineering"
                assert data["relevance_score"] == 94
                assert data["content_quality_score"] == 90

                # Verify GET /api/websites/{id} exposes analysis
                res_get = await client.get(f"/api/websites/{web_id}")
                assert res_get.status_code == 200
                get_data = res_get.json()
                assert get_data["analysis"] is not None
                assert get_data["analysis"]["primary_niche"] == "DevOps & Cloud Engineering"
                assert get_data["analysis"]["relevance_score"] == 94

        print(f"  [PASS] WebsiteAnalysis successfully persisted for Website #{web_id} and verified via API.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 16: AI SEMANTIC WEBSITE ANALYSIS TEST SUITE")
    print("=" * 60)

    test_score_clamping()
    await test_positive_niche_and_relevant_website()
    await test_irrelevant_website_analysis()
    await test_poor_and_limited_content()
    await test_trust_signals_and_editorial_standards()
    await test_anti_hallucination_empty_fields()
    await test_malformed_json_handling()
    await test_api_failure_and_missing_key()
    await test_database_and_fastapi_endpoint()

    print("=" * 60)
    print("ALL STEP 16 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
