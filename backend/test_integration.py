"""Integration test script for Step 9 and Step 10 API verification."""

import asyncio
import httpx
from app.main import app
from app.database import init_db, SessionLocal
from app.models import Website, WebsiteAnalysis, GuestPostInformation, SearchResult

async def run_tests():
    print("1. Initializing database schema...")
    init_db()
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("2. Testing Health Endpoints...")
        health_res = await client.get("/api/health")
        assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
        assert health_res.json()["status"] == "ok"
        print("   [PASS] /api/health -> 200 OK")

        db_health_res = await client.get("/api/health/db")
        assert db_health_res.status_code == 200, f"DB Health check failed: {db_health_res.text}"
        assert db_health_res.json()["status"] == "ok"
        print("   [PASS] /api/health/db -> 200 OK (Database Connected)")

        print("3. Testing Search Creation (POST /api/searches)...")
        create_payload = {
            "keyword": "Artificial Intelligence",
            "requested_website_count": 50,
            "user_id": None
        }
        create_res = await client.post("/api/searches", json=create_payload)
        assert create_res.status_code == 201, f"Create search failed: {create_res.text}"
        search_data = create_res.json()
        assert search_data["keyword"] == "Artificial Intelligence"
        assert search_data["requested_website_count"] == 50
        assert search_data["status"] in ("pending", "discovered", "no_results")
        search_id = search_data["id"]
        print(f"   [PASS] POST /api/searches -> 201 Created (Search ID: {search_id})")

        print("4. Testing Search Listing (GET /api/searches)...")
        list_res = await client.get("/api/searches")
        assert list_res.status_code == 200, f"List searches failed: {list_res.text}"
        list_data = list_res.json()
        assert list_data["total"] >= 1
        found_search = next((s for s in list_data["searches"] if s["id"] == search_id), None)
        assert found_search is not None, "Created search not found in list"
        print(f"   [PASS] GET /api/searches -> 200 OK (Total: {list_data['total']} searches)")

        print(f"5. Testing Search Details by ID (GET /api/searches/{search_id})...")
        get_res = await client.get(f"/api/searches/{search_id}")
        assert get_res.status_code == 200, f"Get search failed: {get_res.text}"
        get_data = get_res.json()
        assert get_data["id"] == search_id
        assert get_data["keyword"] == "Artificial Intelligence"
        assert isinstance(get_data["results"], list)
        print(f"   [PASS] GET /api/searches/{search_id} -> 200 OK (Results: {len(get_data['results'])})")

        print("6. Testing Website Endpoints (GET /api/websites)...")
        web_res = await client.get("/api/websites")
        assert web_res.status_code == 200, f"List websites failed: {web_res.text}"
        print(f"   [PASS] GET /api/websites -> 200 OK (Found {len(web_res.json())} websites)")

        print("7. Testing Website 404 for non-existent ID...")
        not_found_res = await client.get("/api/websites/999999")
        assert not_found_res.status_code == 404, f"Expected 404, got {not_found_res.status_code}"
        print("   [PASS] GET /api/websites/999999 -> 404 Not Found as expected")

        print("8. Testing Website Details with sample website entity...")
        db = SessionLocal()
        try:
            test_domain = "ai-news-hub.example.com"
            existing = db.query(Website).filter_by(domain=test_domain).first()
            if not existing:
                website = Website(
                    domain=test_domain,
                    url=f"https://{test_domain}",
                    name="AI News Hub"
                )
                db.add(website)
                db.commit()
                db.refresh(website)
                
                analysis = WebsiteAnalysis(
                    website_id=website.id,
                    niche_relevance=92,
                    content_quality=88,
                    website_trust=85,
                    guest_post_quality=90,
                    website_activity=86,
                    quality_score=91
                )
                db.add(analysis)
                
                gp_info = GuestPostInformation(
                    website_id=website.id,
                    accepts_guest_posts=True,
                    confidence=95,
                    pricing="Free",
                    submission_method="Email",
                    submission_url=None,
                    contact_email="editor@ai-news-hub.example.com",
                    guidelines_url=f"https://{test_domain}/write-for-us",
                    dofollow=True,
                    evidence="Detected active Write For Us page and guest author guidelines."
                )
                db.add(gp_info)
                test_web_id = website.id
            else:
                test_web_id = existing.id

            # Always associate test website with the current search_id if not present
            existing_sr = db.query(SearchResult).filter_by(search_id=search_id, website_id=test_web_id).first()
            if not existing_sr:
                search_result = SearchResult(
                    search_id=search_id,
                    website_id=test_web_id,
                    status="verified"
                )
                db.add(search_result)
                db.commit()
        finally:
            db.close()

        web_detail_res = await client.get(f"/api/websites/{test_web_id}")
        assert web_detail_res.status_code == 200, f"Get website details failed: {web_detail_res.text}"
        web_detail = web_detail_res.json()
        assert web_detail["id"] == test_web_id
        assert web_detail["domain"] == test_domain
        assert web_detail["analysis"] is not None
        assert web_detail["analysis"]["quality_score"] == 91
        assert web_detail["guest_post_info"]["accepts_guest_posts"] is True
        print(f"   [PASS] GET /api/websites/{test_web_id} -> 200 OK (Domain: {web_detail['domain']}, Quality: {web_detail['analysis']['quality_score']})")

        # Verify search details now include the associated website
        search_with_res = await client.get(f"/api/searches/{search_id}")
        assert search_with_res.status_code == 200
        search_res_data = search_with_res.json()
        assert search_res_data["total_results"] >= 1
        found_item = next((r for r in search_res_data["results"] if r["domain"] == test_domain), None)
        assert found_item is not None, f"Domain {test_domain} not found in results"
        assert found_item["quality_score"] == 91
        print(f"   [PASS] GET /api/searches/{search_id} -> 200 OK (Verified associated result item with domain '{test_domain}')")

        print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
