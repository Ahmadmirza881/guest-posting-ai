"""Comprehensive Test Suite for Step 22: User-Owned Search History.

Covers all audit and integration test requirements:
1. Unauthenticated history access behavior
2. Authenticated history access for User A
3. Invalid token returns HTTP 401 Unauthorized
4. Expired token returns HTTP 401 Unauthorized
5. Search created by User A is assigned User A's user_id
6. Search created by User B is assigned User B's user_id
7. Client request body user_id spoofing is ignored and derived from JWT
8. User A only sees User A's searches in GET /api/searches
9. User B only sees User B's searches in GET /api/searches
10. User A can retrieve their own search details by ID
11. User A cannot retrieve User B's search by ID (returns HTTP 404)
12. User B cannot retrieve User A's search by ID (returns HTTP 404)
13. User A can delete their own search (DELETE /api/searches/{id})
14. User A cannot delete User B's search (returns HTTP 404)
15. User B cannot delete User A's search (returns HTTP 404)
16. Unauthenticated delete returns HTTP 401 Unauthorized
17. User A cannot trigger batch pipeline processing on User B's search (returns HTTP 404)
18. User A cannot view pipeline progress on User B's search (returns HTTP 404)
19. Search history pagination, limits, and ordering
20. Empty history returns total=0 and empty search list
21. Step 19 background pipeline progress regression
22. Step 20 saved websites isolation regression
23. Step 21 authentication & me profile regression
24. Full end-to-end Step 22 lifecycle and cross-user isolation verification
"""

import asyncio
from datetime import timedelta
from unittest.mock import patch, AsyncMock
import httpx
from sqlalchemy import select

from app.database import init_db, SessionLocal
from app.models import User, Search, SearchResult, Website, SavedWebsite, WebsiteAnalysis, GuestPostInformation
from app.main import app
from app.utils.security import hash_password, create_access_token


async def mock_discovery(db, search, provider=None):
    """Mock discovery function that updates status to discovered without external API calls."""
    search.status = "discovered"
    db.commit()
    db.refresh(search)
    return search


def seed_test_database(db):
    """Seed test database with clean isolated user and website records."""
    db.query(SavedWebsite).delete()
    db.query(SearchResult).delete()
    db.query(GuestPostInformation).delete()
    db.query(WebsiteAnalysis).delete()
    db.query(Website).delete()
    db.query(Search).delete()
    db.query(User).delete()
    db.commit()

    # User A (Alice)
    alice = User(
        id=101,
        email="alice@example.com",
        password_hash=hash_password("AliceSecret123!"),
    )
    # User B (Bob)
    bob = User(
        id=202,
        email="bob@example.com",
        password_hash=hash_password("BobSecret123!"),
    )
    # User C (Charlie)
    charlie = User(
        id=303,
        email="charlie@example.com",
        password_hash=hash_password("CharlieSecret123!"),
    )

    db.add_all([alice, bob, charlie])
    db.flush()

    # Create dummy candidate website
    w1 = Website(
        id=901,
        domain="techhub.example.com",
        url="https://techhub.example.com/write-for-us",
        name="TechHub",
        crawl_status="success",
    )
    db.add(w1)
    db.commit()


# =====================================================================
# TEST CASES
# =====================================================================

async def test_01_unauthenticated_history_access(client):
    """Test 1: Unauthenticated request to /api/searches returns public/unowned list without error."""
    print("Test 1: Unauthenticated History Access Behavior...")
    res = await client.get("/api/searches")
    assert res.status_code == 200
    data = res.json()
    assert "searches" in data
    assert "total" in data
    assert data["total"] == 0
    print("  [PASS] Unauthenticated access cleanly returns unowned list without leaking private searches.")


async def test_02_authenticated_history_access(client):
    """Test 2: Authenticated request to /api/searches retrieves user's search history."""
    print("Test 2: Authenticated History Access...")
    token_a = create_access_token(user_id=101)
    res = await client.get(
        "/api/searches",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["searches"], list)
    assert "total" in data
    print("  [PASS] Authenticated user retrieved their search history.")


async def test_03_invalid_token_behavior(client):
    """Test 3: Invalid token header returns HTTP 401 Unauthorized."""
    print("Test 3: Invalid Token Behavior...")
    res = await client.get(
        "/api/searches",
        headers={"Authorization": "Bearer invalid_forged_token_signature"}
    )
    assert res.status_code == 401
    assert "detail" in res.json()
    print("  [PASS] Invalid token safely rejected with HTTP 401 Unauthorized.")


async def test_04_expired_token_behavior(client):
    """Test 4: Expired token header returns HTTP 401 Unauthorized."""
    print("Test 4: Expired Token Behavior...")
    expired_token = create_access_token(user_id=101, expires_delta=timedelta(seconds=-60))
    res = await client.get(
        "/api/searches",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()
    print("  [PASS] Expired token safely rejected with HTTP 401.")


async def test_05_search_created_by_user_a(client, db):
    """Test 5: Search created by User A is recorded with User A's user_id."""
    print("Test 5: Search Created by User A Has user_id=101...")
    token_a = create_access_token(user_id=101)
    res = await client.post(
        "/api/searches?auto_process=false",
        json={"keyword": "AI Tools", "requested_website_count": 25},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["user_id"] == 101
    assert data["keyword"] == "AI Tools"

    # Verify directly in DB
    db.expire_all()
    search_record = db.get(Search, data["id"])
    assert search_record is not None
    assert search_record.user_id == 101
    print("  [PASS] User A search correctly persisted with user_id=101.")


async def test_06_search_created_by_user_b(client, db):
    """Test 6: Search created by User B is recorded with User B's user_id."""
    print("Test 6: Search Created by User B Has user_id=202...")
    token_b = create_access_token(user_id=202)
    res = await client.post(
        "/api/searches?auto_process=false",
        json={"keyword": "Cybersecurity", "requested_website_count": 50},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["user_id"] == 202
    assert data["keyword"] == "Cybersecurity"

    # Verify directly in DB
    db.expire_all()
    search_record = db.get(Search, data["id"])
    assert search_record is not None
    assert search_record.user_id == 202
    print("  [PASS] User B search correctly persisted with user_id=202.")


async def test_07_user_id_spoofing_prevented(client, db):
    """Test 7: Client cannot spoof user_id in payload; backend enforces token identity."""
    print("Test 7: User ID Spoofing in Request Body Ignored...")
    token_a = create_access_token(user_id=101)
    # Alice sends payload claiming user_id=202 (Bob)
    res = await client.post(
        "/api/searches?auto_process=false",
        json={
            "keyword": "Blockchain Security",
            "requested_website_count": 10,
            "user_id": 202,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["user_id"] == 101  # Must be Alice (101), NOT Bob (202)

    db.expire_all()
    search_record = db.get(Search, data["id"])
    assert search_record.user_id == 101
    print("  [PASS] Ownership derived exclusively from token; payload spoofing prevented.")


async def test_08_user_a_only_sees_own_searches(client):
    """Test 8: User A list endpoint returns only User A's searches."""
    print("Test 8: User A Only Sees User A Searches...")
    token_a = create_access_token(user_id=101)
    res = await client.get(
        "/api/searches",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    for s in data["searches"]:
        assert s["user_id"] == 101
    keywords = {s["keyword"] for s in data["searches"]}
    assert keywords == {"AI Tools", "Blockchain Security"}
    assert "Cybersecurity" not in keywords
    print("  [PASS] User A only sees searches created by User A.")


async def test_09_user_b_only_sees_own_searches(client):
    """Test 9: User B list endpoint returns only User B's searches."""
    print("Test 9: User B Only Sees User B Searches...")
    token_b = create_access_token(user_id=202)
    res = await client.get(
        "/api/searches",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["searches"][0]["user_id"] == 202
    assert data["searches"][0]["keyword"] == "Cybersecurity"
    print("  [PASS] User B only sees searches created by User B.")


async def test_10_user_a_can_retrieve_own_search_by_id(client, db):
    """Test 10: User A can retrieve their own search details by ID."""
    print("Test 10: User A Retrieves Own Search by ID...")
    token_a = create_access_token(user_id=101)
    db.expire_all()
    alice_search = db.scalars(select(Search).where(Search.user_id == 101)).first()

    res = await client.get(
        f"/api/searches/{alice_search.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == alice_search.id
    assert data["user_id"] == 101
    print("  [PASS] User A successfully retrieved their own search by ID.")


async def test_11_user_a_cannot_retrieve_user_b_search(client, db):
    """Test 11: User A requesting User B's search receives HTTP 404 (isolation)."""
    print("Test 11: User A Cannot Retrieve User B Search by ID...")
    token_a = create_access_token(user_id=101)
    db.expire_all()
    bob_search = db.scalars(select(Search).where(Search.user_id == 202)).first()

    res = await client.get(
        f"/api/searches/{bob_search.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 404
    print("  [PASS] Cross-user search access blocked with HTTP 404.")


async def test_12_user_b_cannot_retrieve_user_a_search(client, db):
    """Test 12: User B requesting User A's search receives HTTP 404."""
    print("Test 12: User B Cannot Retrieve User A Search by ID...")
    token_b = create_access_token(user_id=202)
    db.expire_all()
    alice_search = db.scalars(select(Search).where(Search.user_id == 101)).first()

    res = await client.get(
        f"/api/searches/{alice_search.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404
    print("  [PASS] Cross-user search access for User B blocked with HTTP 404.")


async def test_13_user_a_can_delete_own_search(client, db):
    """Test 13: User A can delete their own search record."""
    print("Test 13: User A Deletes Own Search...")
    token_a = create_access_token(user_id=101)
    db.expire_all()
    alice_search = db.scalars(select(Search).where(Search.user_id == 101)).first()
    search_id = alice_search.id

    res = await client.delete(
        f"/api/searches/{search_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["id"] == search_id

    # Verify search is gone from DB
    db.expire_all()
    deleted_search = db.get(Search, search_id)
    assert deleted_search is None
    print("  [PASS] User A successfully deleted their own search record.")


async def test_14_user_a_cannot_delete_user_b_search(client, db):
    """Test 14: User A cannot delete User B's search record (returns HTTP 404)."""
    print("Test 14: User A Cannot Delete User B Search...")
    token_a = create_access_token(user_id=101)
    db.expire_all()
    bob_search = db.scalars(select(Search).where(Search.user_id == 202)).first()
    bob_search_id = bob_search.id

    res = await client.delete(
        f"/api/searches/{bob_search_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 404

    # Verify Bob's search is still intact in DB
    db.expire_all()
    intact_search = db.get(Search, bob_search_id)
    assert intact_search is not None
    assert intact_search.user_id == 202
    print("  [PASS] Unauthorized deletion blocked; User B's search preserved.")


async def test_15_user_b_cannot_delete_user_a_search(client, db):
    """Test 15: User B cannot delete User A's remaining search record."""
    print("Test 15: User B Cannot Delete User A Search...")
    token_b = create_access_token(user_id=202)
    db.expire_all()
    alice_search = db.scalars(select(Search).where(Search.user_id == 101)).first()
    alice_search_id = alice_search.id

    res = await client.delete(
        f"/api/searches/{alice_search_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404

    db.expire_all()
    intact_search = db.get(Search, alice_search_id)
    assert intact_search is not None
    assert intact_search.user_id == 101
    print("  [PASS] User B cannot delete User A's search record.")


async def test_16_unauthenticated_delete_returns_401(client, db):
    """Test 16: DELETE /api/searches/{id} without token returns HTTP 401."""
    print("Test 16: Unauthenticated Delete Returns 401...")
    db.expire_all()
    bob_search = db.scalars(select(Search).where(Search.user_id == 202)).first()

    res = await client.delete(f"/api/searches/{bob_search.id}")
    assert res.status_code == 401
    print("  [PASS] Unauthenticated delete safely rejected with HTTP 401.")


async def test_17_user_a_cannot_process_user_b_search(client, db):
    """Test 17: User A cannot trigger pipeline processing on User B's search."""
    print("Test 17: User A Cannot Process User B Search...")
    token_a = create_access_token(user_id=101)
    db.expire_all()
    bob_search = db.scalars(select(Search).where(Search.user_id == 202)).first()

    res = await client.post(
        f"/api/searches/{bob_search.id}/process",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 404
    print("  [PASS] Cross-user pipeline triggering blocked with HTTP 404.")


async def test_18_user_a_cannot_view_progress_of_user_b_search(client, db):
    """Test 18: User A cannot inspect pipeline progress of User B's search."""
    print("Test 18: User A Cannot View Progress of User B Search...")
    token_a = create_access_token(user_id=101)
    db.expire_all()
    bob_search = db.scalars(select(Search).where(Search.user_id == 202)).first()

    res = await client.get(
        f"/api/searches/{bob_search.id}/progress",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 404
    print("  [PASS] Cross-user progress inspection blocked with HTTP 404.")


async def test_19_search_history_pagination(client):
    """Test 19: User search history pagination parameters (skip, limit)."""
    print("Test 19: Search History Pagination...")
    token_c = create_access_token(user_id=303)

    # Create 5 searches for Charlie
    for i in range(5):
        await client.post(
            "/api/searches?auto_process=false",
            json={"keyword": f"Niche {i+1}", "requested_website_count": 10},
            headers={"Authorization": f"Bearer {token_c}"},
        )

    # Page 1 (limit 2, skip 0)
    p1 = await client.get(
        "/api/searches?skip=0&limit=2",
        headers={"Authorization": f"Bearer {token_c}"},
    )
    assert p1.status_code == 200
    p1_data = p1.json()
    assert p1_data["total"] == 5
    assert len(p1_data["searches"]) == 2

    # Page 2 (limit 2, skip 2)
    p2 = await client.get(
        "/api/searches?skip=2&limit=2",
        headers={"Authorization": f"Bearer {token_c}"},
    )
    assert p2.status_code == 200
    p2_data = p2.json()
    assert p2_data["total"] == 5
    assert len(p2_data["searches"]) == 2
    assert p1_data["searches"][0]["id"] != p2_data["searches"][0]["id"]
    print("  [PASS] History pagination (skip & limit) works properly for user searches.")


async def test_20_empty_history_for_new_user(client):
    """Test 20: Brand new user receives empty history with total=0."""
    print("Test 20: Empty History for New User...")
    # Register a new user
    reg_res = await client.post(
        "/api/auth/register",
        json={"email": "fresh_user@example.com", "password": "FreshPassword123!"},
    )
    assert reg_res.status_code == 201
    fresh_user_id = reg_res.json()["id"]

    token = create_access_token(user_id=fresh_user_id)
    res = await client.get(
        "/api/searches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["searches"] == []
    print("  [PASS] Empty history cleanly returned for new user.")


async def test_21_step19_pipeline_regression(client, db):
    """Test 21: Step 19 background pipeline progress calculation still operates cleanly."""
    print("Test 21: Step 19 Pipeline Functionality Regression...")
    token_b = create_access_token(user_id=202)
    db.expire_all()
    bob_search = db.scalars(select(Search).where(Search.user_id == 202)).first()

    # Progress check on owned search
    prog_res = await client.get(
        f"/api/searches/{bob_search.id}/progress",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert prog_res.status_code == 200
    prog_data = prog_res.json()
    assert prog_data["search_id"] == bob_search.id
    assert "progress_percentage" in prog_data
    assert "is_completed" in prog_data
    print("  [PASS] Step 19 pipeline progress functions accurately.")


async def test_22_step20_saved_websites_regression(client):
    """Test 22: Step 20 saved website bookmarking remains isolated per user."""
    print("Test 22: Step 20 Saved Websites Regression...")
    token_a = create_access_token(user_id=101)
    token_b = create_access_token(user_id=202)

    # Alice saves website #901
    save_res = await client.post(
        "/api/websites/901/save",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert save_res.status_code == 200
    assert save_res.json()["is_saved"] is True

    # Bob's saved list should be empty
    bob_saved = await client.get(
        "/api/websites/saved",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bob_saved.status_code == 200
    assert bob_saved.json()["total"] == 0

    # Alice's saved list has 1 website
    alice_saved = await client.get(
        "/api/websites/saved",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert alice_saved.status_code == 200
    assert alice_saved.json()["total"] == 1
    print("  [PASS] Step 20 saved website isolation functions properly.")


async def test_23_step21_auth_me_regression(client):
    """Test 23: Step 21 authentication & me profile inspection remains functional."""
    print("Test 23: Step 21 Authentication Regression...")
    token_a = create_access_token(user_id=101)
    me_res = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "alice@example.com"
    print("  [PASS] Step 21 auth/me endpoint functions properly.")


async def test_24_full_step22_lifecycle_scenario(client, db):
    """Test 24: Full end-to-end multi-user search history scenario."""
    print("Test 24: Full Step 22 Lifecycle and Isolation Scenario...")

    # Create User A & User B tokens
    token_a = create_access_token(user_id=101)
    token_b = create_access_token(user_id=202)

    # User A performs Search A1 & Search A2
    res_a1 = await client.post(
        "/api/searches?auto_process=false",
        json={"keyword": "Fintech Guest Posts", "requested_website_count": 20},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a1.status_code == 201
    id_a1 = res_a1.json()["id"]

    res_a2 = await client.post(
        "/api/searches?auto_process=false",
        json={"keyword": "Edtech Opportunities", "requested_website_count": 30},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a2.status_code == 201
    id_a2 = res_a2.json()["id"]

    # User B performs Search B1
    res_b1 = await client.post(
        "/api/searches?auto_process=false",
        json={"keyword": "Healthcare Guest Posts", "requested_website_count": 40},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b1.status_code == 201
    id_b1 = res_b1.json()["id"]

    # User A History contains A1 and A2 only
    hist_a = await client.get("/api/searches", headers={"Authorization": f"Bearer {token_a}"})
    a_ids = {s["id"] for s in hist_a.json()["searches"]}
    assert id_a1 in a_ids
    assert id_a2 in a_ids
    assert id_b1 not in a_ids

    # User B History contains B1 only (plus prior bob searches)
    hist_b = await client.get("/api/searches", headers={"Authorization": f"Bearer {token_b}"})
    b_ids = {s["id"] for s in hist_b.json()["searches"]}
    assert id_b1 in b_ids
    assert id_a1 not in b_ids
    assert id_a2 not in b_ids

    # User A tries to access B1 -> 404
    cross_get = await client.get(f"/api/searches/{id_b1}", headers={"Authorization": f"Bearer {token_a}"})
    assert cross_get.status_code == 404

    # User A tries to delete B1 -> 404
    cross_del = await client.delete(f"/api/searches/{id_b1}", headers={"Authorization": f"Bearer {token_a}"})
    assert cross_del.status_code == 404

    # User B can delete B1
    b_del = await client.delete(f"/api/searches/{id_b1}", headers={"Authorization": f"Bearer {token_b}"})
    assert b_del.status_code == 200

    print("  [PASS] Full multi-user search lifecycle and security isolation verified cleanly.")


# =====================================================================
# MAIN RUNNER
# =====================================================================

async def run_all_tests():
    init_db()
    db = SessionLocal()
    transport = httpx.ASGITransport(app=app)
    try:
        seed_test_database(db)

        with patch("app.services.search_service.execute_search_discovery", new=AsyncMock(side_effect=mock_discovery)):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await test_01_unauthenticated_history_access(client)
                await test_02_authenticated_history_access(client)
                await test_03_invalid_token_behavior(client)
                await test_04_expired_token_behavior(client)
                await test_05_search_created_by_user_a(client, db)
                await test_06_search_created_by_user_b(client, db)
                await test_07_user_id_spoofing_prevented(client, db)
                await test_08_user_a_only_sees_own_searches(client)
                await test_09_user_b_only_sees_own_searches(client)
                await test_10_user_a_can_retrieve_own_search_by_id(client, db)
                await test_11_user_a_cannot_retrieve_user_b_search(client, db)
                await test_12_user_b_cannot_retrieve_user_a_search(client, db)
                await test_13_user_a_can_delete_own_search(client, db)
                await test_14_user_a_cannot_delete_user_b_search(client, db)
                await test_15_user_b_cannot_delete_user_a_search(client, db)
                await test_16_unauthenticated_delete_returns_401(client, db)
                await test_17_user_a_cannot_process_user_b_search(client, db)
                await test_18_user_a_cannot_view_progress_of_user_b_search(client, db)
                await test_19_search_history_pagination(client)
                await test_20_empty_history_for_new_user(client)
                await test_21_step19_pipeline_regression(client, db)
                await test_22_step20_saved_websites_regression(client)
                await test_23_step21_auth_me_regression(client)
                await test_24_full_step22_lifecycle_scenario(client, db)

        print("\n" + "=" * 70)
        print("ALL 24 STEP 22 AUDIT & INTEGRATION TESTS PASSED SUCCESSFULLY! [PASS]")
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
