"""Comprehensive Test Suite for Step 17: Deterministic Website Scoring Engine.

Validates multi-factor scoring formula (Guest Post 25, Relevance 25, Content Quality 20,
Trust 15, Editorial 10, AI Verification 5 = 100 total), score bounding [0, 100],
missing data handling, conflict/rejection zeroing, breakdown structure, DB persistence, and API endpoints.
"""

import asyncio
import json
import httpx

from app.database import init_db, SessionLocal
from app.models import Website, WebsiteAnalysis, GuestPostInformation
from app.services.scoring import (
    SCORING_WEIGHTS,
    calculate_guest_post_score,
    calculate_relevance_score,
    calculate_content_quality_score,
    calculate_trust_score,
    calculate_editorial_score,
    calculate_ai_verification_score,
    calculate_website_score,
    score_website_record,
)
from app.main import app


def test_weights_sum_100():
    """Verify that scoring configuration weights sum to exactly 100."""
    print("Running Test: Scoring Weights Total 100...")
    total_weights = sum(SCORING_WEIGHTS.values())
    assert total_weights == 100, f"Weights sum to {total_weights}, expected 100"
    print("  [PASS] SCORING_WEIGHTS sums to exactly 100 points.")


def test_perfect_website_scoring():
    """Test scoring a website that achieves full marks across all 6 dimensions."""
    print("Running Test: Perfect Website Scoring (100 Points)...")

    gp_info = GuestPostInformation(
        website_id=1,
        accepts_guest_posts=True,
        confidence=100,
        verification_status="verified",
        ai_confidence=100
    )

    analysis = WebsiteAnalysis(
        website_id=1,
        relevance_score=100,
        content_quality_score=100,
        trust_signals=json.dumps(["Author with PhD", "About page", "Contact email listed"]),
        editorial_standards=json.dumps(["Editorial peer review", "Contributor guidelines"]),
        analysis_confidence=100
    )

    result = calculate_website_score(website_id=1, gp_info=gp_info, analysis=analysis)

    assert result.quality_score == 100
    assert result.breakdown["guest_post_acceptance"].points == 25.0
    assert result.breakdown["niche_relevance"].points == 25.0
    assert result.breakdown["content_quality"].points == 20.0
    assert result.breakdown["trust_signals"].points == 15.0
    assert result.breakdown["editorial_standards"].points == 10.0
    assert result.breakdown["ai_verification"].points == 5.0
    print("  [PASS] Perfect website achieved exactly 100 quality score.")


def test_zero_website_scoring():
    """Test scoring a website where all dimensions evaluate to zero."""
    print("Running Test: Zero Website Scoring (0 Points)...")

    gp_info = GuestPostInformation(
        website_id=2,
        accepts_guest_posts=False,
        confidence=0,
        verification_status="rejected",
        ai_confidence=0
    )

    analysis = WebsiteAnalysis(
        website_id=2,
        relevance_score=0,
        content_quality_score=0,
        trust_signals=json.dumps([]),
        editorial_standards=json.dumps([]),
        analysis_confidence=0
    )

    result = calculate_website_score(website_id=2, gp_info=gp_info, analysis=analysis)

    assert result.quality_score == 0
    assert result.breakdown["guest_post_acceptance"].points == 0.0
    assert result.breakdown["niche_relevance"].points == 0.0
    assert result.breakdown["content_quality"].points == 0.0
    assert result.breakdown["trust_signals"].points == 0.0
    assert result.breakdown["editorial_standards"].points == 0.0
    assert result.breakdown["ai_verification"].points == 0.0
    print("  [PASS] Zero website scored exactly 0 points.")


def test_relevance_calculation():
    """Test niche relevance 0-25 normalization formula."""
    print("Running Test: Relevance Score Calculation...")
    pts_100, _ = calculate_relevance_score(100)
    pts_50, _ = calculate_relevance_score(50)
    pts_0, _ = calculate_relevance_score(0)
    pts_none, _ = calculate_relevance_score(None)

    assert pts_100 == 25.0
    assert pts_50 == 12.5
    assert pts_0 == 0.0
    assert pts_none == 0.0
    print("  [PASS] Relevance normalized correctly to 0-25.")


def test_content_quality_calculation():
    """Test content quality 0-20 normalization formula."""
    print("Running Test: Content Quality Calculation...")
    pts_100, _ = calculate_content_quality_score(100)
    pts_75, _ = calculate_content_quality_score(75)
    pts_0, _ = calculate_content_quality_score(0)
    pts_none, _ = calculate_content_quality_score(None)

    assert pts_100 == 20.0
    assert pts_75 == 15.0
    assert pts_0 == 0.0
    assert pts_none == 0.0
    print("  [PASS] Content quality normalized correctly to 0-20.")


def test_guest_post_acceptance_confidence_and_rejection():
    """Test guest post acceptance score mapping and explicit rejection override."""
    print("Running Test: Guest Post Confidence & Rejection Zeroing...")

    # Verified acceptance mapping
    pts_100, _ = calculate_guest_post_score(True, 100, "verified")
    pts_80, _ = calculate_guest_post_score(True, 80, "verified")
    pts_40, _ = calculate_guest_post_score(True, 40, "verified")
    assert pts_100 == 25.0
    assert pts_80 == 20.0
    assert pts_40 == 10.0

    # Explicit rejection
    pts_rej_1, _ = calculate_guest_post_score(False, 90, "rejected")
    pts_rej_2, _ = calculate_guest_post_score(False, None, None)
    pts_rej_3, _ = calculate_guest_post_score(True, 90, "rejected")  # conflict resolves to rejected
    assert pts_rej_1 == 0.0
    assert pts_rej_2 == 0.0
    assert pts_rej_3 == 0.0

    # Uncertain partial score
    pts_unc, _ = calculate_guest_post_score(None, 80, "uncertain")
    assert pts_unc == 10.0  # 80% of 25 is 20, 50% partial credit is 10.0

    print("  [PASS] Guest post confidence mapped and rejections strictly zeroed.")


def test_trust_signals_scoring():
    """Test trust signals category scoring up to 15 max points."""
    print("Running Test: Trust Signals Scoring...")
    pts_3, _ = calculate_trust_score(["Signal 1", "Signal 2", "Signal 3"])
    pts_2, _ = calculate_trust_score(["Signal 1", "Signal 2"])
    pts_1, _ = calculate_trust_score(["Signal 1"])
    pts_0, _ = calculate_trust_score([])
    pts_none, _ = calculate_trust_score(None)

    assert pts_3 == 15.0
    assert pts_2 == 10.0
    assert pts_1 == 5.0
    assert pts_0 == 0.0
    assert pts_none == 0.0
    print("  [PASS] Trust signals mapped deterministically up to 15 max.")


def test_editorial_standards_scoring():
    """Test editorial standards category scoring up to 10 max points."""
    print("Running Test: Editorial Standards Scoring...")
    pts_2, _ = calculate_editorial_score(["Rule 1", "Rule 2"])
    pts_1, _ = calculate_editorial_score(["Rule 1"])
    pts_0, _ = calculate_editorial_score([])
    pts_none, _ = calculate_editorial_score(None)

    assert pts_2 == 10.0
    assert pts_1 == 5.0
    assert pts_0 == 0.0
    assert pts_none == 0.0
    print("  [PASS] Editorial standards mapped deterministically up to 10 max.")


def test_ai_verification_scoring():
    """Test AI verification category scoring up to 5 max points."""
    print("Running Test: AI Verification Scoring...")
    pts_ver, _ = calculate_ai_verification_score("verified", 100)
    pts_unc, _ = calculate_ai_verification_score("uncertain", 100)
    pts_rej, _ = calculate_ai_verification_score("rejected", 90)
    pts_unv, _ = calculate_ai_verification_score("unverified", 0)

    assert pts_ver == 5.0
    assert pts_unc == 2.5
    assert pts_rej == 0.0
    assert pts_unv == 0.0
    print("  [PASS] AI verification mapped up to 5 max.")


def test_missing_data_and_invalid_values():
    """Test that missing analysis records, invalid/out-of-bounds numbers, and bad JSON do not crash."""
    print("Running Test: Missing Data & Invalid Values Handling...")

    # Missing both records
    res_empty = calculate_website_score(website_id=99, gp_info=None, analysis=None)
    assert res_empty.quality_score == 0
    assert res_empty.breakdown["guest_post_acceptance"].points == 0.0
    assert res_empty.breakdown["niche_relevance"].points == 0.0

    # Malformed data
    gp_info_bad = GuestPostInformation(
        website_id=99,
        accepts_guest_posts=True,
        confidence=999,  # out of bounds
        verification_status="verified",
        ai_confidence=-50  # negative
    )
    analysis_bad = WebsiteAnalysis(
        website_id=99,
        relevance_score=200,  # out of bounds
        content_quality_score=-20,  # negative
        trust_signals="invalid non-json string",  # bad json
        editorial_standards=None
    )

    res_clamped = calculate_website_score(website_id=99, gp_info=gp_info_bad, analysis=analysis_bad)
    assert 0 <= res_clamped.quality_score <= 100
    assert res_clamped.breakdown["niche_relevance"].points == 25.0  # clamped to 100 -> 25
    assert res_clamped.breakdown["content_quality"].points == 0.0  # clamped to 0 -> 0

    print("  [PASS] Missing and malformed values handled safely without errors.")


def test_breakdown_structure_and_bounds():
    """Test that all 6 required breakdown categories contain points, max_points, and reason."""
    print("Running Test: Breakdown Structure & Final Bounds...")
    res = calculate_website_score(website_id=10, gp_info=None, analysis=None)

    required_categories = [
        "guest_post_acceptance",
        "niche_relevance",
        "content_quality",
        "trust_signals",
        "editorial_standards",
        "ai_verification"
    ]

    for cat in required_categories:
        assert cat in res.breakdown
        item = res.breakdown[cat]
        assert hasattr(item, "points")
        assert hasattr(item, "max_points")
        assert hasattr(item, "reason")
        assert isinstance(item.reason, str) and len(item.reason) > 0

    assert 0 <= res.quality_score <= 100
    assert isinstance(res.quality_score, int)
    print("  [PASS] Breakdown structure is complete, typed, and explainable.")


async def test_database_persistence_and_api_endpoint():
    """Test database persistence and FastAPI POST /api/websites/{id}/score endpoint."""
    print("Running Test: Database Persistence & FastAPI Endpoint...")
    init_db()

    db = SessionLocal()
    try:
        test_domain = "scoring-test.example.com"
        website = db.query(Website).filter_by(domain=test_domain).first()
        if not website:
            sample_html = "<html><head><title>Scoring Portal</title></head><body><h1>Scoring Test</h1></body></html>"
            website = Website(
                domain=test_domain,
                url="https://scoring-test.example.com",
                name="Scoring Test Portal",
                crawl_status="success",
                html_content=sample_html
            )
            db.add(website)
            db.commit()
            db.refresh(website)

        web_id = website.id

        # Add GP Info
        gp_info = db.query(GuestPostInformation).filter_by(website_id=web_id).first()
        if not gp_info:
            gp_info = GuestPostInformation(
                website_id=web_id,
                accepts_guest_posts=True,
                confidence=90,
                verification_status="verified",
                ai_confidence=90
            )
            db.add(gp_info)
            db.commit()

        # Add Analysis
        analysis = db.query(WebsiteAnalysis).filter_by(website_id=web_id).first()
        if not analysis:
            analysis = WebsiteAnalysis(
                website_id=web_id,
                relevance_score=80,
                content_quality_score=85,
                trust_signals=json.dumps(["Author Bio", "Contact Address"]),
                editorial_standards=json.dumps(["Submission Guidelines"]),
                analysis_confidence=85
            )
            db.add(analysis)
            db.commit()

        # Run Score Record function
        updated_web, score_res = score_website_record(db=db, website_id=web_id)
        assert updated_web is not None
        assert 0 <= score_res.quality_score <= 100
        assert score_res.scoring_status == "scored"

        # Verify DB persistence
        db_analysis = db.query(WebsiteAnalysis).filter_by(website_id=web_id).first()
        assert db_analysis.quality_score == score_res.quality_score
        assert db_analysis.scoring_status == "scored"
        assert db_analysis.score_breakdown is not None
        assert db_analysis.scored_at is not None

        # Test FastAPI POST /api/websites/{id}/score endpoint
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res_post = await client.post(f"/api/websites/{web_id}/score")
            assert res_post.status_code == 200
            data = res_post.json()
            assert data["website_id"] == web_id
            assert "quality_score" in data
            assert "breakdown" in data
            assert data["breakdown"]["guest_post_acceptance"]["points"] > 0

            # Test GET /api/websites/{id} exposes quality score and analysis
            res_get = await client.get(f"/api/websites/{web_id}")
            assert res_get.status_code == 200
            web_data = res_get.json()
            assert web_data["analysis"] is not None
            assert web_data["analysis"]["quality_score"] == score_res.quality_score

        print(f"  [PASS] Website #{web_id} scored ({score_res.quality_score}/100) and verified via API.")
    finally:
        db.close()


async def main():
    print("=" * 60)
    print("STEP 17: DETERMINISTIC WEBSITE SCORING TEST SUITE")
    print("=" * 60)

    test_weights_sum_100()
    test_perfect_website_scoring()
    test_zero_website_scoring()
    test_relevance_calculation()
    test_content_quality_calculation()
    test_guest_post_acceptance_confidence_and_rejection()
    test_trust_signals_scoring()
    test_editorial_standards_scoring()
    test_ai_verification_scoring()
    test_missing_data_and_invalid_values()
    test_breakdown_structure_and_bounds()
    await test_database_persistence_and_api_endpoint()

    print("=" * 60)
    print("ALL STEP 17 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
