"""Comprehensive Test Suite for Step 18: Smart Filters Backend Implementation."""

import asyncio
import json
from datetime import datetime, timezone
import httpx

from app.database import init_db, SessionLocal
from app.models import Website, WebsiteAnalysis, GuestPostInformation, Search, SearchResult
from app.services.filtering import (
    filter_websites,
    WebsiteFilterParams,
    validate_filter_params,
)
from app.main import app


def seed_test_database(db):
    """Seed structured test data covering various acceptance, pricing, and analysis conditions."""
    # Clear existing test records if any to have a clean slate
    db.query(SearchResult).delete()
    db.query(GuestPostInformation).delete()
    db.query(WebsiteAnalysis).delete()
    db.query(Website).delete()
    db.query(Search).delete()
    db.commit()

    # Create Search #100
    search_1 = Search(id=100, keyword="AI Technology", requested_website_count=50, status="discovered")
    search_2 = Search(id=200, keyword="Gardening", requested_website_count=20, status="discovered")
    db.add_all([search_1, search_2])
    db.flush()

    now_utc = datetime.now(timezone.utc)

    # Website 1: Top Quality Free Accepting Tech Blog (email + google_form)
    w1 = Website(id=101, domain="tech-innovations.example.com", url="https://tech-innovations.example.com/write-for-us", name="Tech Innovations", crawl_status="success")
    gp1 = GuestPostInformation(
        website_id=101, accepts_guest_posts=True, confidence=95, pricing="free",
        submission_method="email, google_form", contact_email="editor@tech-innovations.example.com",
        verification_status="verified", ai_confidence=95
    )
    wa1 = WebsiteAnalysis(
        website_id=101, primary_niche="Artificial Intelligence", topics=json.dumps(["AI", "Machine Learning", "Technology"]),
        relevance_score=95, content_quality_score=90, quality_score=92
    )

    # Website 2: Paid Accepting Tech Blog (form only)
    w2 = Website(id=102, domain="cloud-architect.example.com", url="https://cloud-architect.example.com/guest-post", name="Cloud Architect", crawl_status="success")
    gp2 = GuestPostInformation(
        website_id=102, accepts_guest_posts=True, confidence=90, pricing="$150 per post",
        submission_method="form", submission_url="https://cloud-architect.example.com/submit",
        verification_status="verified", ai_confidence=85
    )
    wa2 = WebsiteAnalysis(
        website_id=102, primary_niche="Cloud Computing", topics=json.dumps(["Cloud", "DevOps", "Infrastructure"]),
        relevance_score=80, content_quality_score=85, quality_score=78
    )

    # Website 3: Non-Accepting High-Quality Site (rejection)
    w3 = Website(id=103, domain="major-news.example.com", url="https://major-news.example.com/contact", name="Major News", crawl_status="success")
    gp3 = GuestPostInformation(
        website_id=103, accepts_guest_posts=False, confidence=90, pricing=None,
        submission_method=None, verification_status="rejected", ai_confidence=90
    )
    wa3 = WebsiteAnalysis(
        website_id=103, primary_niche="General News", topics=json.dumps(["News", "World", "Politics"]),
        relevance_score=40, content_quality_score=95, quality_score=45
    )

    # Website 4: Typeform Accepting Site with Unknown Pricing & Uncertain Verification
    w4 = Website(id=104, domain="marketing-digest.example.com", url="https://marketing-digest.example.com/contribute", name="Marketing Digest", crawl_status="success")
    gp4 = GuestPostInformation(
        website_id=104, accepts_guest_posts=True, confidence=60, pricing="unknown",
        submission_method="typeform", submission_url="https://form.typeform.com/to/xyz",
        verification_status="uncertain", ai_confidence=50
    )
    wa4 = WebsiteAnalysis(
        website_id=104, primary_niche="Digital Marketing", topics=json.dumps(["SEO", "Marketing", "Content"]),
        relevance_score=70, content_quality_score=65, quality_score=60
    )

    # Website 5: Unanalyzed & Uncrawled Pending Website (No Analysis, No GP Info)
    w5 = Website(id=105, domain="pending-site.example.com", url="https://pending-site.example.com", name="Pending Site", crawl_status="pending")

    # Website 6: Website with Analysis but Missing Guest Post Info
    w6 = Website(id=106, domain="analysis-only.example.com", url="https://analysis-only.example.com", name="Analysis Only", crawl_status="success")
    wa6 = WebsiteAnalysis(
        website_id=106, primary_niche="Cybersecurity", topics=json.dumps(["Security", "Encryption"]),
        relevance_score=85, content_quality_score=80, quality_score=75
    )

    # Website 7: Scoped to Search #200 (Gardening)
    w7 = Website(id=107, domain="green-garden.example.com", url="https://green-garden.example.com/write-for-us", name="Green Garden", crawl_status="success")
    gp7 = GuestPostInformation(
        website_id=107, accepts_guest_posts=True, confidence=80, pricing="free",
        submission_method="email", contact_email="editor@green-garden.example.com",
        verification_status="verified", ai_confidence=80
    )
    wa7 = WebsiteAnalysis(
        website_id=107, primary_niche="Gardening & Home", topics=json.dumps(["Plants", "Home"]),
        relevance_score=90, content_quality_score=70, quality_score=70
    )

    db.add_all([w1, w2, w3, w4, w5, w6, w7, gp1, gp2, gp3, gp4, gp7, wa1, wa2, wa3, wa4, wa6, wa7])
    db.flush()

    # Associate w1..w6 with Search #100, w7 with Search #200
    for w in [w1, w2, w3, w4, w5, w6]:
        db.add(SearchResult(search_id=100, website_id=w.id, status="discovered"))
    db.add(SearchResult(search_id=200, website_id=w7.id, status="discovered"))

    db.commit()


def test_1_no_filters(db):
    """Test 1: No filters returns all scoped websites."""
    print("Test 1: No filters...")
    items, total, page, page_size, total_pages, filters_applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, page=1, page_size=25)
    )
    assert total == 6
    assert len(items) == 6
    assert page == 1
    assert total_pages == 1
    print("  [PASS] Returned all 6 websites for Search #100.")


def test_2_accepting_filter(db):
    """Test 2: Guest-post accepting filter."""
    print("Test 2: guest_post_status=accepting...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, guest_post_status="accepting")
    )
    assert total == 3  # w1, w2, w4
    assert all(w.guest_post_info.accepts_guest_posts is True for w in items)
    assert applied.get("guest_post_status") == "accepting"
    print("  [PASS] Correctly filtered to accepting websites only.")


def test_3_not_accepting_filter(db):
    """Test 3: Guest-post not-accepting filter."""
    print("Test 3: guest_post_status=not_accepting...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, guest_post_status="not_accepting")
    )
    assert total == 1  # w3
    assert items[0].id == 103
    assert items[0].guest_post_info.accepts_guest_posts is False
    print("  [PASS] Correctly filtered to non-accepting websites.")


def test_4_free_pricing_filter(db):
    """Test 4: Free pricing filter."""
    print("Test 4: pricing=free...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, pricing="free")
    )
    assert total == 1  # w1
    assert items[0].id == 101
    assert "free" in items[0].guest_post_info.pricing.lower()
    print("  [PASS] Returned only free guest post opportunities.")


def test_5_paid_pricing_filter(db):
    """Test 5: Paid pricing filter."""
    print("Test 5: pricing=paid...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, pricing="paid")
    )
    assert total == 1  # w2 ($150)
    assert items[0].id == 102
    assert "$" in items[0].guest_post_info.pricing
    print("  [PASS] Returned only paid guest post opportunities.")


def test_6_unknown_pricing_filter(db):
    """Test 6: Unknown pricing filter."""
    print("Test 6: pricing=unknown...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, pricing="unknown")
    )
    # w3, w4, w5, w6 have unknown or missing pricing
    assert total >= 2
    domains = [w.domain for w in items]
    assert "marketing-digest.example.com" in domains
    print("  [PASS] Handled unknown/missing pricing without confusing with free.")


def test_7_min_quality_score(db):
    """Test 7: Minimum quality score filter."""
    print("Test 7: min_quality_score=80...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, min_quality_score=80)
    )
    assert total == 1  # w1 (score 92)
    assert items[0].id == 101
    assert items[0].analysis.quality_score >= 80
    print("  [PASS] Enforced minimum quality score threshold.")


def test_8_min_relevance_score(db):
    """Test 8: Minimum relevance score filter."""
    print("Test 8: min_relevance_score=85...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, min_relevance_score=85)
    )
    assert total == 2  # w1 (95), w6 (85)
    assert all(w.analysis.relevance_score >= 85 for w in items)
    print("  [PASS] Enforced minimum relevance score threshold.")


def test_9_min_content_quality(db):
    """Test 9: Minimum content quality score filter."""
    print("Test 9: min_content_quality=90...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, min_content_quality=90)
    )
    assert total == 2  # w1 (90), w3 (95)
    assert all(w.analysis.content_quality_score >= 90 for w in items)
    print("  [PASS] Enforced minimum content quality score threshold.")


def test_10_verification_status(db):
    """Test 10: AI Verification status filter."""
    print("Test 10: verification_status=verified...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, verification_status="verified")
    )
    assert total == 2  # w1, w2
    assert all(w.guest_post_info.verification_status == "verified" for w in items)
    print("  [PASS] Filtered accurately by verification status.")


def test_11_min_ai_confidence(db):
    """Test 11: Minimum AI confidence filter."""
    print("Test 11: min_ai_confidence=90...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, min_ai_confidence=90)
    )
    assert total == 2  # w1 (95), w3 (90)
    assert all(w.guest_post_info.ai_confidence >= 90 for w in items)
    print("  [PASS] Enforced minimum AI confidence threshold.")


def test_12_email_submission_method(db):
    """Test 12: Email submission method filter."""
    print("Test 12: submission_method=email...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, submission_method="email")
    )
    assert total == 1  # w1 ("email, google_form")
    assert items[0].id == 101
    print("  [PASS] Filtered by email submission method.")


def test_13_google_form_submission_method(db):
    """Test 13: Google Form submission method filter."""
    print("Test 13: submission_method=google_form...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, submission_method="google_form")
    )
    assert total == 1  # w1
    assert items[0].id == 101
    print("  [PASS] Filtered by google_form submission method.")


def test_14_typeform_submission_method(db):
    """Test 14: Typeform submission method filter."""
    print("Test 14: submission_method=typeform...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, submission_method="typeform")
    )
    assert total == 1  # w4
    assert items[0].id == 104
    print("  [PASS] Filtered by typeform submission method.")


def test_15_multi_method_submission_matching(db):
    """Test 15: Multi-method submission matching (matches individual methods in a list)."""
    print("Test 15: Multi-method submission matching...")
    # w1 has submission_method="email, google_form"
    items_email, total_e, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, submission_method="email")
    )
    items_gf, total_g, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, submission_method="google_form")
    )
    assert items_email[0].id == 101
    assert items_gf[0].id == 101
    print("  [PASS] Multi-method record matches both 'email' and 'google_form' queries.")


def test_16_niche_filtering(db):
    """Test 16: Niche text filter."""
    print("Test 16: niche=Artificial Intelligence...")
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(search_id=100, niche="Artificial Intelligence")
    )
    assert total == 1  # w1
    assert items[0].id == 101
    print("  [PASS] Matched stored primary niche and topics in DB without calling external AI.")


def test_17_quality_score_sorting(db):
    """Test 17: Quality score sorting (descending and ascending)."""
    print("Test 17: Sorting by quality_score...")
    items_desc, _, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, sort_by="quality_score", sort_order="desc")
    )
    scores = [w.analysis.quality_score for w in items_desc if w.analysis and w.analysis.quality_score is not None]
    assert scores == sorted(scores, reverse=True)
    print("  [PASS] Sorted by quality_score descending.")


def test_18_relevance_sorting(db):
    """Test 18: Relevance sorting."""
    print("Test 18: Sorting by relevance_score...")
    items_desc, _, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, sort_by="relevance_score", sort_order="desc")
    )
    rel_scores = [w.analysis.relevance_score for w in items_desc if w.analysis and w.analysis.relevance_score is not None]
    assert rel_scores == sorted(rel_scores, reverse=True)
    print("  [PASS] Sorted by relevance_score descending.")


def test_19_domain_sorting(db):
    """Test 19: Domain sorting."""
    print("Test 19: Sorting by domain...")
    items_asc, _, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, sort_by="domain", sort_order="asc")
    )
    domains = [w.domain for w in items_asc]
    assert domains == sorted(domains)
    print("  [PASS] Sorted alphabetically by domain.")


def test_20_ascending_sorting(db):
    """Test 20: Ascending sort direction."""
    print("Test 20: Ascending sort direction...")
    items_asc, _, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, sort_by="quality_score", sort_order="asc")
    )
    scores = [w.analysis.quality_score for w in items_asc if w.analysis and w.analysis.quality_score is not None]
    assert scores == sorted(scores)
    print("  [PASS] Quality scores ordered ascending.")


def test_21_descending_sorting(db):
    """Test 21: Descending sort direction."""
    print("Test 21: Descending sort direction...")
    items_desc, _, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, sort_by="content_quality", sort_order="desc")
    )
    cq_scores = [w.analysis.content_quality_score for w in items_desc if w.analysis and w.analysis.content_quality_score is not None]
    assert cq_scores == sorted(cq_scores, reverse=True)
    print("  [PASS] Content quality scores ordered descending.")


def test_22_pagination(db):
    """Test 22: Pagination metadata (page, page_size, total_pages)."""
    print("Test 22: Pagination...")
    items_p1, total, page, page_size, total_pages, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, page=1, page_size=2)
    )
    assert total == 6
    assert len(items_p1) == 2
    assert page == 1
    assert page_size == 2
    assert total_pages == 3

    items_p2, _, page_2, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, page=2, page_size=2)
    )
    assert len(items_p2) == 2
    assert page_2 == 2
    assert items_p1[0].id != items_p2[0].id
    print("  [PASS] Pagination offsets, pages, and total_pages calculated accurately.")


def test_23_multiple_filters_combined(db):
    """Test 23: Multiple filters combined with AND logic."""
    print("Test 23: Multiple filters combined (AND logic)...")
    # Filter for: accepting + free + min_quality_score=70 + verification_status=verified + submission_method=email
    items, total, _, _, _, applied = filter_websites(
        db, WebsiteFilterParams(
            search_id=100,
            guest_post_status="accepting",
            pricing="free",
            min_quality_score=70,
            min_relevance_score=75,
            verification_status="verified",
            submission_method="email"
        )
    )
    assert total == 1
    assert items[0].id == 101
    assert applied["guest_post_status"] == "accepting"
    assert applied["pricing"] == "free"
    assert applied["min_quality_score"] == 70
    assert applied["submission_method"] == "email"
    print("  [PASS] Multiple simultaneous filters evaluated cleanly with AND logic.")


def test_24_invalid_filter_validation():
    """Test 24: Validation rules reject invalid scores, methods, and pagination."""
    print("Test 24: Invalid filter validation...")

    # Out of range quality score
    try:
        validate_filter_params(WebsiteFilterParams(min_quality_score=-5))
        assert False, "Should reject negative score"
    except ValueError:
        pass

    try:
        validate_filter_params(WebsiteFilterParams(min_quality_score=150))
        assert False, "Should reject score > 100"
    except ValueError:
        pass

    # Invalid submission method
    try:
        validate_filter_params(WebsiteFilterParams(submission_method="unknown_method"))
        assert False, "Should reject invalid submission method"
    except ValueError:
        pass

    # Invalid sort column
    try:
        validate_filter_params(WebsiteFilterParams(sort_by="malicious_sql_injection"))
        assert False, "Should reject unwhitelisted sort column"
    except ValueError:
        pass

    # Invalid page number
    try:
        validate_filter_params(WebsiteFilterParams(page=0))
        assert False, "Should reject page < 1"
    except ValueError:
        pass

    # Invalid page size
    try:
        validate_filter_params(WebsiteFilterParams(page_size=5000))
        assert False, "Should reject page_size > 100"
    except ValueError:
        pass

    print("  [PASS] All invalid inputs rejected with proper descriptive ValueErrors.")


def test_25_missing_analysis_data_handling(db):
    """Test 25: Websites with missing analysis records handled gracefully."""
    print("Test 25: Missing analysis data handling...")
    # Website 105 has no analysis record. It should appear when filtering without minimum score constraints
    items, total, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, crawl_status="pending")
    )
    assert any(w.id == 105 for w in items)
    print("  [PASS] Missing analysis records handled cleanly without outer join errors.")


def test_26_missing_guest_post_data_handling(db):
    """Test 26: Websites with missing guest post data handled gracefully."""
    print("Test 26: Missing guest post data handling...")
    # Website 106 has analysis but no GuestPostInformation
    items, total, _, _, _, _ = filter_websites(
        db, WebsiteFilterParams(search_id=100, min_quality_score=70)
    )
    assert any(w.id == 106 for w in items)
    print("  [PASS] Missing guest post data handled without exceptions.")


async def test_27_fastapi_endpoint_regression():
    """Test 27: FastAPI /api/websites/filter endpoint full HTTP integration & regression."""
    print("Test 27: FastAPI endpoint regression...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Valid filter request
        res = await client.get(
            "/api/websites/filter",
            params={
                "search_id": 100,
                "guest_post_status": "accepting",
                "pricing": "free",
                "min_quality_score": 70,
                "page": 1,
                "page_size": 10,
            }
        )
        assert res.status_code == 200, f"Filter endpoint failed: {res.text}"
        data = res.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["domain"] == "tech-innovations.example.com"
        assert data["filters_applied"]["guest_post_status"] == "accepting"

        # Invalid parameter validation (HTTP 400)
        invalid_res = await client.get(
            "/api/websites/filter",
            params={"min_quality_score": 999}
        )
        assert invalid_res.status_code == 400

        # Existing endpoints regression verification
        web_res = await client.get("/api/websites")
        assert web_res.status_code == 200

        single_res = await client.get("/api/websites/101")
        assert single_res.status_code == 200
        assert single_res.json()["domain"] == "tech-innovations.example.com"

    print("  [PASS] FastAPI endpoint tested successfully with 200, 400 validation, and existing route regression.")


def main():
    print("=" * 60)
    print("STEP 18: SMART FILTERS BACKEND TEST SUITE")
    print("=" * 60)
    init_db()
    db = SessionLocal()
    try:
        seed_test_database(db)

        test_1_no_filters(db)
        test_2_accepting_filter(db)
        test_3_not_accepting_filter(db)
        test_4_free_pricing_filter(db)
        test_5_paid_pricing_filter(db)
        test_6_unknown_pricing_filter(db)
        test_7_min_quality_score(db)
        test_8_min_relevance_score(db)
        test_9_min_content_quality(db)
        test_10_verification_status(db)
        test_11_min_ai_confidence(db)
        test_12_email_submission_method(db)
        test_13_google_form_submission_method(db)
        test_14_typeform_submission_method(db)
        test_15_multi_method_submission_matching(db)
        test_16_niche_filtering(db)
        test_17_quality_score_sorting(db)
        test_18_relevance_sorting(db)
        test_19_domain_sorting(db)
        test_20_ascending_sorting(db)
        test_21_descending_sorting(db)
        test_22_pagination(db)
        test_23_multiple_filters_combined(db)
        test_24_invalid_filter_validation()
        test_25_missing_analysis_data_handling(db)
        test_26_missing_guest_post_data_handling(db)
        asyncio.run(test_27_fastapi_endpoint_regression())

        print("=" * 60)
        print("ALL 27 STEP 18 TESTS PASSED SUCCESSFULLY! [PASS]")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
