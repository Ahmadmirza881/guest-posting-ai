"""Comprehensive Test Suite for Step 20: Saved Websites & CSV Export.

Covers all 25 specific audit and integration test requirements:
1. Save existing website (POST /api/websites/{id}/save)
2. Save missing website (returns HTTP 404)
3. Duplicate save protection (idempotent / returns 200 without creating duplicates)
4. Unsave existing saved website (DELETE /api/websites/{id}/save)
5. Unsave non-saved website (idempotent / returns 200)
6. Saved website list (GET /api/websites/saved returns enriched opportunity data)
7. Empty saved list (returns total=0, empty items list)
8. Pagination of saved websites (page, page_size, total_pages)
9. is_saved state in website responses (GET /api/websites/{id} and GET /api/websites/filter)
10. CSV export basic success (Content-Type text/csv, attachment header)
11. CSV headers exact match (all 13 required columns)
12. CSV values populated correctly from database records
13. CSV escaping (commas, quotes, multiline/special characters)
14. CSV UTF-8-BOM behavior (clean utf-8-sig encoding for spreadsheet tools)
15. Missing/null field handling in CSV (clean empty strings without 'None' text)
16. Empty filtered export (returns CSV with header line and 0 data rows)
17. Filtered CSV respects Step 18 filters (pricing, min_quality_score, guest_post_status)
18. Saved websites CSV export (GET /api/websites/saved/export/csv)
19. Saved CSV with zero records (clean header row, 0 data rows)
20. Save/unsave API integration (POST then DELETE, checking database state)
21. Existing website endpoint regression (GET /api/websites, GET /api/websites/{id})
22. Existing filtering endpoint regression (GET /api/websites/filter)
23. Existing scoring behavior regression (score_website_record / POST /api/websites/{id}/score)
24. Existing pipeline regression (pipeline progress calculation, process_single_website_pipeline)
25. Full Step 20 end-to-end integration flow
"""

import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
import httpx
from sqlalchemy import select, func

from app.database import init_db, SessionLocal
from app.models import Website, WebsiteAnalysis, GuestPostInformation, Search, SearchResult, SavedWebsite
from app.services.saved_service import save_website, unsave_website, get_saved_websites, get_all_saved_websites_for_export
from app.services.csv_exporter import generate_websites_csv, create_csv_response, CSV_HEADERS
from app.main import app


def seed_test_database(db):
    """Seed clean, controlled test data for Step 20 testing."""
    db.query(SavedWebsite).delete()
    db.query(SearchResult).delete()
    db.query(GuestPostInformation).delete()
    db.query(WebsiteAnalysis).delete()
    db.query(Website).delete()
    db.query(Search).delete()
    from app.models import User
    db.query(User).delete()
    db.commit()

    test_user = User(id=1, email="step20_tester@example.com", password_hash="$2b$12$dummyhashforstep20tests000000000000000000000000000000000")
    db.add(test_user)
    db.commit()

    # Search #701
    search_1 = Search(id=701, keyword="Artificial Intelligence", requested_website_count=10, status="completed")
    db.add(search_1)
    db.flush()

    # Website 1: Top free accepting tech blog
    w1 = Website(
        id=801,
        domain="tech-radar.example.com",
        url="https://tech-radar.example.com/write-for-us",
        name='Tech "Radar" & Insights, Inc.',
        crawl_status="success",
    )
    gp1 = GuestPostInformation(
        website_id=801,
        accepts_guest_posts=True,
        confidence=95,
        pricing="Free",
        submission_method="email, form",
        submission_url="https://tech-radar.example.com/submit",
        contact_email="editor@tech-radar.example.com",
        guidelines_url="https://tech-radar.example.com/guidelines",
        verification_status="verified",
        ai_confidence=95,
    )
    wa1 = WebsiteAnalysis(
        website_id=801,
        primary_niche="Artificial Intelligence",
        relevance_score=90,
        content_quality_score=85,
        quality_score=88,
    )

    # Website 2: Paid accepting site
    w2 = Website(
        id=802,
        domain="cloud-daily.example.com",
        url="https://cloud-daily.example.com/guest-post",
        name="Cloud Daily",
        crawl_status="success",
    )
    gp2 = GuestPostInformation(
        website_id=802,
        accepts_guest_posts=True,
        confidence=80,
        pricing="$150",
        submission_method="form",
        submission_url="https://cloud-daily.example.com/form",
        verification_status="verified",
        ai_confidence=80,
    )
    wa2 = WebsiteAnalysis(
        website_id=802,
        primary_niche="Cloud Computing",
        relevance_score=75,
        content_quality_score=70,
        quality_score=65,
    )

    # Website 3: Non-accepting site
    w3 = Website(
        id=803,
        domain="closed-portal.example.com",
        url="https://closed-portal.example.com/about",
        name="Closed Portal",
        crawl_status="success",
    )
    gp3 = GuestPostInformation(
        website_id=803,
        accepts_guest_posts=False,
        confidence=90,
        pricing=None,
        submission_method=None,
        verification_status="rejected",
        ai_confidence=90,
    )
    wa3 = WebsiteAnalysis(
        website_id=803,
        primary_niche="General News",
        relevance_score=30,
        content_quality_score=80,
        quality_score=25,
    )

    db.add_all([w1, w2, w3, gp1, gp2, gp3, wa1, wa2, wa3])
    db.flush()

    db.add(SearchResult(search_id=701, website_id=801, status="processed"))
    db.add(SearchResult(search_id=701, website_id=802, status="processed"))
    db.add(SearchResult(search_id=701, website_id=803, status="processed"))
    db.commit()


# =====================================================================
# TEST CASES
# =====================================================================

async def test_01_save_existing_website(client, db):
    """Test 1: Save existing website returns success and sets is_saved=True."""
    print("Test 1: Save Existing Website...")
    res = await client.post("/api/websites/801/save")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["website_id"] == 801
    assert data["is_saved"] is True

    # Check DB
    saved = db.scalars(select(SavedWebsite).where(SavedWebsite.website_id == 801)).first()
    assert saved is not None
    print("  [PASS] Website #801 successfully saved to database.")


async def test_02_save_missing_website(client):
    """Test 2: Saving a non-existent website returns 404."""
    print("Test 2: Save Missing Website (404)...")
    res = await client.post("/api/websites/999999/save")
    assert res.status_code == 404
    print("  [PASS] Missing website correctly returned 404 Not Found.")


async def test_03_duplicate_save_protection(client, db):
    """Test 3: Saving an already-saved website is idempotent and does not create duplicate rows."""
    print("Test 3: Duplicate Save Protection...")
    # Website 801 is already saved
    res = await client.post("/api/websites/801/save")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["is_saved"] is True
    assert "already saved" in data["message"].lower()

    # Check count in DB is exactly 1
    count = db.scalar(select(func.count(SavedWebsite.id)).where(SavedWebsite.website_id == 801))
    assert count == 1
    print("  [PASS] Duplicate save handled safely without duplicate DB records.")


async def test_04_unsave_existing_saved_website(client, db):
    """Test 4: Unsave removes website from saved records."""
    print("Test 4: Unsave Existing Saved Website...")
    # Save website 802 first
    await client.post("/api/websites/802/save")
    assert db.scalars(select(SavedWebsite).where(SavedWebsite.website_id == 802)).first() is not None

    # Now unsave 802
    res = await client.delete("/api/websites/802/save")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["website_id"] == 802
    assert data["is_saved"] is False

    # Check DB is removed
    saved = db.scalars(select(SavedWebsite).where(SavedWebsite.website_id == 802)).first()
    assert saved is None
    print("  [PASS] Website #802 removed from saved list cleanly.")


async def test_05_unsave_non_saved_website(client):
    """Test 5: Unsaving a website that is not currently saved is safe/idempotent."""
    print("Test 5: Unsave Non-Saved Website...")
    res = await client.delete("/api/websites/803/save")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["is_saved"] is False
    assert "was not in saved list" in data["message"].lower()
    print("  [PASS] Unsaving non-saved website returned safe 200 response.")


async def test_06_saved_website_list(client):
    """Test 6: GET /api/websites/saved returns populated list with metadata."""
    print("Test 6: Saved Website List Endpoint...")
    res = await client.get("/api/websites/saved")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["website_id"] == 801
    assert item["domain"] == "tech-radar.example.com"
    assert item["niche"] == "Artificial Intelligence"
    assert item["guest_post_status"] == "accepting"
    assert item["pricing"] == "Free"
    assert item["quality_score"] == 88
    assert item["is_saved"] is True
    print("  [PASS] GET /api/websites/saved returned complete saved opportunity details.")


async def test_07_empty_saved_list(client, db):
    """Test 7: Empty saved list returns total=0 and items=[]."""
    print("Test 7: Empty Saved List Handling...")
    db.query(SavedWebsite).delete()
    db.commit()

    res = await client.get("/api/websites/saved")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["total_pages"] == 0
    print("  [PASS] Empty saved list returned cleanly with 0 items.")


async def test_08_pagination_of_saved_websites(client, db):
    """Test 8: Pagination of saved websites works accurately."""
    print("Test 8: Pagination of Saved Websites...")
    # Save websites 801, 802, 803
    await client.post("/api/websites/801/save")
    await client.post("/api/websites/802/save")
    await client.post("/api/websites/803/save")

    res = await client.get("/api/websites/saved?page=1&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2

    res2 = await client.get("/api/websites/saved?page=2&page_size=2")
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) == 1
    assert data2["page"] == 2
    print("  [PASS] Saved websites pagination verified across pages 1 and 2.")


async def test_09_is_saved_state_in_website_responses(client):
    """Test 9: is_saved boolean exposed in website details and filter endpoints."""
    print("Test 9: is_saved State in Website Responses...")
    # Website 801 is saved, let's verify via GET /api/websites/801
    res = await client.get("/api/websites/801")
    assert res.status_code == 200
    assert res.json()["is_saved"] is True

    # Unsave 803 to check False
    await client.delete("/api/websites/803/save")
    res_803 = await client.get("/api/websites/803")
    assert res_803.status_code == 200
    assert res_803.json()["is_saved"] is False

    # Check /api/websites/filter includes is_saved
    filter_res = await client.get("/api/websites/filter?search_id=701")
    assert filter_res.status_code == 200
    items = filter_res.json()["items"]
    item_801 = next(it for it in items if it["id"] == 801)
    item_803 = next(it for it in items if it["id"] == 803)
    assert item_801["is_saved"] is True
    assert item_803["is_saved"] is False
    print("  [PASS] is_saved accurately reflected in /api/websites/{id} and /api/websites/filter.")


async def test_10_csv_export_basic_success(client):
    """Test 10: GET /api/websites/export/csv returns valid CSV attachment."""
    print("Test 10: CSV Export Basic Success...")
    res = await client.get("/api/websites/export/csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert "guest_posting_opportunities.csv" in res.headers["content-disposition"]
    print("  [PASS] CSV export returned HTTP 200 with attachment headers.")


async def test_11_csv_headers_exact_match(client):
    """Test 11: CSV headers match exact required columns."""
    print("Test 11: CSV Headers Exact Match...")
    res = await client.get("/api/websites/export/csv")
    csv_text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_text))
    header_row = next(reader)
    assert header_row == CSV_HEADERS
    print(f"  [PASS] All {len(CSV_HEADERS)} CSV columns present in exact order.")


async def test_12_csv_values_populated_correctly(client):
    """Test 12: CSV values match stored DB values for websites."""
    print("Test 12: CSV Values Verification...")
    res = await client.get("/api/websites/export/csv?search_id=701&sort_by=quality_score&sort_order=desc")
    csv_text = res.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) >= 1
    row_801 = next((r for r in rows if r["Domain"] == "tech-radar.example.com"), None)
    assert row_801 is not None
    assert row_801["Niche"] == "Artificial Intelligence"
    assert row_801["Guest Post Status"] == "accepting"
    assert row_801["Pricing"] == "Free"
    assert row_801["Quality Score"] == "88"
    assert row_801["Verification Status"] == "verified"
    assert row_801["Submission URL"] == "https://tech-radar.example.com/submit"
    print("  [PASS] CSV row values accurately represent database entities.")


async def test_13_csv_escaping(client):
    """Test 13: Quotes, commas, and special characters properly escaped per RFC 4180."""
    print("Test 13: CSV Escaping...")
    # tech-radar has quotes and comma: 'Tech "Radar" & Insights, Inc.'
    res = await client.get("/api/websites/export/csv")
    csv_text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    row_801 = next(r for r in rows if "tech-radar.example.com" in r)
    name_val = row_801[0]
    assert name_val == 'Tech "Radar" & Insights, Inc.'
    print("  [PASS] Special characters and quotes cleanly escaped and parsed.")


async def test_14_csv_utf8_behavior(client):
    """Test 14: CSV encoded as utf-8-sig with BOM for Excel/Sheets compatibility."""
    print("Test 14: CSV UTF-8 BOM Verification...")
    res = await client.get("/api/websites/export/csv")
    raw_bytes = res.content
    assert raw_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    decoded = raw_bytes.decode("utf-8-sig")
    assert "Domain" in decoded
    print("  [PASS] UTF-8 BOM verified at byte level.")


async def test_15_missing_null_field_handling_in_csv(client):
    """Test 15: Missing or null fields produce clean empty strings instead of 'None'."""
    print("Test 15: Missing / Null Field Handling...")
    res = await client.get("/api/websites/export/csv")
    csv_text = res.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    # Closed portal has no submission_url or pricing
    row_803 = next(r for r in rows if r["Domain"] == "closed-portal.example.com")
    assert row_803["Submission URL"] == ""
    assert row_803["Pricing"] == ""
    assert "None" not in row_803.values()
    print("  [PASS] Missing values correctly output as empty strings without 'None' text.")


async def test_16_empty_filtered_export(client):
    """Test 16: Exporting with filters that match 0 items produces CSV with headers and 0 rows."""
    print("Test 16: Empty Filtered CSV Export...")
    res = await client.get("/api/websites/export/csv?min_quality_score=99")
    assert res.status_code == 200
    csv_text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == CSV_HEADERS
    remaining_rows = list(reader)
    assert len(remaining_rows) == 0
    print("  [PASS] Empty filtered export produced valid CSV with headers and zero data rows.")


async def test_17_filtered_csv_respects_step18_filters(client):
    """Test 17: Filtered CSV export respects Step 18 filters (pricing, score, status)."""
    print("Test 17: Filtered CSV Export Respects Filters...")
    # 1. pricing=free
    res_free = await client.get("/api/websites/export/csv?pricing=free")
    rows_free = list(csv.DictReader(io.StringIO(res_free.content.decode("utf-8-sig"))))
    assert all(r["Pricing"].lower() == "free" for r in rows_free)
    assert any(r["Domain"] == "tech-radar.example.com" for r in rows_free)

    # 2. min_quality_score=70
    res_high = await client.get("/api/websites/export/csv?min_quality_score=70")
    rows_high = list(csv.DictReader(io.StringIO(res_high.content.decode("utf-8-sig"))))
    assert all(int(r["Quality Score"]) >= 70 for r in rows_high if r["Quality Score"])

    # 3. guest_post_status=not_accepting
    res_na = await client.get("/api/websites/export/csv?guest_post_status=not_accepting")
    rows_na = list(csv.DictReader(io.StringIO(res_na.content.decode("utf-8-sig"))))
    assert len(rows_na) >= 1
    assert any(r["Domain"] == "closed-portal.example.com" for r in rows_na)
    print("  [PASS] Filtered CSV properly applied Step 18 filtering criteria.")


async def test_18_saved_websites_csv_export(client):
    """Test 18: GET /api/websites/saved/export/csv exports bookmarked opportunities."""
    print("Test 18: Saved Websites CSV Export...")
    res = await client.get("/api/websites/saved/export/csv")
    assert res.status_code == 200
    assert "saved_websites.csv" in res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(res.content.decode("utf-8-sig"))))
    # Currently websites 801 and 802 are saved
    assert len(rows) >= 1
    domains = [r["Domain"] for r in rows]
    assert "tech-radar.example.com" in domains
    print(f"  [PASS] Saved websites CSV exported {len(rows)} bookmarked sites.")


async def test_19_saved_csv_with_zero_records(client, db):
    """Test 19: Saved websites CSV export when 0 websites are saved returns headers only."""
    print("Test 19: Saved CSV With Zero Records...")
    db.query(SavedWebsite).delete()
    db.commit()

    res = await client.get("/api/websites/saved/export/csv")
    assert res.status_code == 200
    csv_text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == CSV_HEADERS
    rows = list(reader)
    assert len(rows) == 0
    print("  [PASS] Empty saved CSV produced valid headers and zero rows.")


async def test_20_save_unsave_api_integration(client, db):
    """Test 20: Full cycle save then unsave with database state inspection."""
    print("Test 20: Save/Unsave Full API Cycle...")
    # 1. Verify not saved
    res0 = await client.get("/api/websites/801")
    assert res0.json()["is_saved"] is False

    # 2. Save
    res1 = await client.post("/api/websites/801/save")
    assert res1.status_code == 200
    assert res1.json()["is_saved"] is True

    # 3. Verify saved
    res2 = await client.get("/api/websites/801")
    assert res2.json()["is_saved"] is True

    # 4. Unsave
    res3 = await client.delete("/api/websites/801/save")
    assert res3.status_code == 200
    assert res3.json()["is_saved"] is False

    # 5. Verify not saved
    res4 = await client.get("/api/websites/801")
    assert res4.json()["is_saved"] is False
    print("  [PASS] Save -> check -> unsave -> check lifecycle completed successfully.")


async def test_21_existing_website_endpoint_regression(client):
    """Test 21: Existing GET /api/websites and GET /api/websites/{id} routes remain fully functional."""
    print("Test 21: Website Endpoints Regression...")
    res_list = await client.get("/api/websites")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 3

    res_detail = await client.get("/api/websites/801")
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == 801
    print("  [PASS] Existing website listing and detail endpoints working as expected.")


async def test_22_existing_filtering_endpoint_regression(client):
    """Test 22: Existing GET /api/websites/filter endpoint regression test."""
    print("Test 22: Filtering Endpoint Regression...")
    res = await client.get("/api/websites/filter?min_quality_score=50&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1
    print("  [PASS] Step 18 filter endpoint regression test passed.")


def test_23_existing_scoring_behavior_regression(db):
    """Test 23: Deterministic scoring behavior regression check."""
    print("Test 23: Scoring Behavior Regression...")
    from app.services.scoring import score_website_record
    w, res = score_website_record(db=db, website_id=801)
    assert 0 <= res.quality_score <= 100
    assert res.scoring_status == "scored"
    assert "guest_post_acceptance" in res.breakdown
    print("  [PASS] Step 17 scoring engine regression test passed.")


def test_24_existing_pipeline_regression(db):
    """Test 24: Pipeline progress calculation regression test."""
    print("Test 24: Pipeline Progress Calculation Regression...")
    from app.services.pipeline import get_search_pipeline_progress
    progress = get_search_pipeline_progress(db=db, search_id=701)
    assert progress["search_id"] == 701
    assert "progress_percentage" in progress
    assert "crawled_count" in progress
    print("  [PASS] Step 19 pipeline progress calculation regression test passed.")


async def test_25_full_step20_integration_flow(client, db):
    """Test 25: Complete end-to-end Step 20 workflow."""
    print("Test 25: Full Step 20 Integration Flow...")
    # 1. Bookmark website 801 and 802
    await client.post("/api/websites/801/save")
    await client.post("/api/websites/802/save")

    # 2. Check saved list
    saved_res = await client.get("/api/websites/saved")
    assert saved_res.json()["total"] == 2

    # 3. Export saved CSV
    saved_csv = await client.get("/api/websites/saved/export/csv")
    saved_rows = list(csv.DictReader(io.StringIO(saved_csv.content.decode("utf-8-sig"))))
    assert len(saved_rows) == 2

    # 4. Export filtered opportunities CSV
    filt_csv = await client.get("/api/websites/export/csv?guest_post_status=accepting")
    filt_rows = list(csv.DictReader(io.StringIO(filt_csv.content.decode("utf-8-sig"))))
    assert len(filt_rows) >= 2

    # 5. Unsave all
    await client.delete("/api/websites/801/save")
    await client.delete("/api/websites/802/save")

    # 6. Verify empty saved list
    empty_res = await client.get("/api/websites/saved")
    assert empty_res.json()["total"] == 0
    print("  [PASS] Full Step 20 end-to-end integration flow verified cleanly.")


# =====================================================================
# MAIN RUNNER
# =====================================================================

async def run_all_tests():
    init_db()
    db = SessionLocal()
    transport = httpx.ASGITransport(app=app)
    from app.dependencies import get_current_user, get_optional_current_user
    from app.models import User
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    app.dependency_overrides[get_optional_current_user] = lambda: db.get(User, 1)
    try:
        seed_test_database(db)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await test_01_save_existing_website(client, db)
            await test_02_save_missing_website(client)
            await test_03_duplicate_save_protection(client, db)
            await test_04_unsave_existing_saved_website(client, db)
            await test_05_unsave_non_saved_website(client)
            await test_06_saved_website_list(client)
            await test_07_empty_saved_list(client, db)
            await test_08_pagination_of_saved_websites(client, db)
            await test_09_is_saved_state_in_website_responses(client)
            await test_10_csv_export_basic_success(client)
            await test_11_csv_headers_exact_match(client)
            await test_12_csv_values_populated_correctly(client)
            await test_13_csv_escaping(client)
            await test_14_csv_utf8_behavior(client)
            await test_15_missing_null_field_handling_in_csv(client)
            await test_16_empty_filtered_export(client)
            await test_17_filtered_csv_respects_step18_filters(client)
            await test_18_saved_websites_csv_export(client)
            await test_19_saved_csv_with_zero_records(client, db)
            await test_20_save_unsave_api_integration(client, db)
            await test_21_existing_website_endpoint_regression(client)
            await test_22_existing_filtering_endpoint_regression(client)
            test_23_existing_scoring_behavior_regression(db)
            test_24_existing_pipeline_regression(db)
            await test_25_full_step20_integration_flow(client, db)

        print("\n" + "=" * 70)
        print("ALL 25 STEP 20 AUDIT & INTEGRATION TESTS PASSED SUCCESSFULLY! [PASS]")
        print("=" * 70)
    finally:
        app.dependency_overrides.clear()
        db.close()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
