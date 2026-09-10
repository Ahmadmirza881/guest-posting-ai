"""Comprehensive Test Suite for Step 21: Authentication & User Accounts.

Covers all 25 specific audit and integration test requirements:
1. User registration success (POST /api/auth/register)
2. Registration validation (invalid email, weak password)
3. Duplicate email rejection (returns HTTP 400 Bad Request)
4. Password is saved as hash (verify database stores bcrypt hash, not plaintext)
5. Password is never returned in API responses (register, login, me)
6. Login success (returns access_token and user info)
7. Invalid password rejection (safe HTTP 401 Unauthorized)
8. Unknown user rejection (safe HTTP 401 Unauthorized)
9. JWT/token creation (verify valid signature, 'sub', 'exp')
10. Valid token authentication (access protected endpoint with Bearer token)
11. Invalid token rejection (malformed/tampered token returns HTTP 401)
12. Expired token rejection (expired token returns HTTP 401)
13. Missing Authorization header on protected endpoints (returns HTTP 401)
14. GET /api/auth/me authenticated (returns user details)
15. GET /api/auth/me unauthenticated (returns HTTP 401)
16. Saved website requires authentication (returns HTTP 401 without Bearer token)
17. User A can save website
18. User B can save the same website independently
19. User A cannot see User B's saved websites in GET /api/websites/saved
20. Duplicate save prevented per user (idempotent 200 without duplicate records)
21. User A unsave does not affect User B's saved records
22. Saved CSV only contains current user's saved websites
23. is_saved is user-specific (User A sees True, User B sees False for same site)
24. Logout behavior (POST /api/auth/logout returns 200)
25. Full authentication + saved website integration flow
"""

import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import select

from app.database import init_db, SessionLocal
from app.models import User, Website, WebsiteAnalysis, GuestPostInformation, SavedWebsite
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    normalize_email,
)
from app.main import app


def seed_test_database(db):
    """Seed clean, controlled database records for Step 21 tests."""
    db.query(SavedWebsite).delete()
    db.query(GuestPostInformation).delete()
    db.query(WebsiteAnalysis).delete()
    db.query(Website).delete()
    db.query(User).delete()
    db.commit()

    # Seed 2 candidate websites
    w1 = Website(
        id=901,
        domain="alpha-tech.example.com",
        url="https://alpha-tech.example.com/write-for-us",
        name="Alpha Tech Blog",
        crawl_status="success",
    )
    gp1 = GuestPostInformation(
        website_id=901,
        accepts_guest_posts=True,
        confidence=90,
        pricing="Free",
        submission_method="email",
        contact_email="editor@alpha-tech.example.com",
        verification_status="verified",
    )
    wa1 = WebsiteAnalysis(
        website_id=901,
        primary_niche="Technology",
        quality_score=85,
        relevance_score=88,
        content_quality_score=82,
    )

    w2 = Website(
        id=902,
        domain="beta-health.example.com",
        url="https://beta-health.example.com/guest-posting",
        name="Beta Health Journal",
        crawl_status="success",
    )
    gp2 = GuestPostInformation(
        website_id=902,
        accepts_guest_posts=True,
        confidence=85,
        pricing="Paid",
        submission_method="form",
        submission_url="https://beta-health.example.com/submit",
        verification_status="verified",
    )
    wa2 = WebsiteAnalysis(
        website_id=902,
        primary_niche="Health & Wellness",
        quality_score=78,
        relevance_score=75,
        content_quality_score=80,
    )

    db.add_all([w1, gp1, wa1, w2, gp2, wa2])
    db.commit()


# =====================================================================
# INDIVIDUAL TEST CASES
# =====================================================================

async def test_01_user_registration_success(client, db):
    """Test 1: User registration succeeds with valid email and password."""
    print("Test 1: User Registration Success...")
    res = await client.post(
        "/api/auth/register",
        json={"email": "Alice@Example.com", "password": "SecurePassword123!"},
    )
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["email"] == "alice@example.com"  # normalized
    assert "created_at" in data

    # Verify user exists in database
    user = db.scalars(select(User).where(User.email == "alice@example.com")).first()
    assert user is not None
    assert user.email == "alice@example.com"
    print("  [PASS] User successfully registered with normalized email.")


async def test_02_registration_validation(client):
    """Test 2: Registration rejects invalid email and weak password."""
    print("Test 2: Registration Validation...")
    # Invalid email
    res1 = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "validPassword123"},
    )
    assert res1.status_code == 422 or res1.status_code == 400

    # Weak password (< 6 chars)
    res2 = await client.post(
        "/api/auth/register",
        json={"email": "valid@example.com", "password": "123"},
    )
    assert res2.status_code == 422 or res2.status_code == 400
    print("  [PASS] Registration validation rejected malformed email and short password.")


async def test_03_duplicate_email_rejection(client):
    """Test 3: Duplicate email registration returns HTTP 400."""
    print("Test 3: Duplicate Email Rejection...")
    res = await client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "AnotherPassword456!"},
    )
    assert res.status_code == 400
    data = res.json()
    assert "detail" in data
    assert "already registered" in data["detail"].lower()
    print("  [PASS] Duplicate email registration rejected with safe HTTP 400 message.")


def test_04_password_is_hashed(db):
    """Test 4: Password is saved as a bcrypt hash, never plaintext."""
    print("Test 4: Password Is Saved as Hash...")
    user = db.scalars(select(User).where(User.email == "alice@example.com")).first()
    assert user is not None
    assert user.password_hash != "SecurePassword123!"
    assert user.password_hash.startswith("$2b$") or user.password_hash.startswith("$2a$")
    assert verify_password("SecurePassword123!", user.password_hash) is True
    assert verify_password("WrongPassword!", user.password_hash) is False
    print("  [PASS] Password stored exclusively as bcrypt hash in database.")


async def test_05_password_never_returned(client):
    """Test 5: Neither password nor password_hash is exposed in API responses."""
    print("Test 5: Password Never Returned in API Responses...")
    # Register response check
    res_reg = await client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    assert res_reg.status_code == 201
    data_reg = res_reg.json()
    assert "password" not in data_reg
    assert "password_hash" not in data_reg

    # Login response check
    res_login = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    assert res_login.status_code == 200
    data_login = res_login.json()
    assert "password" not in data_login
    assert "password_hash" not in data_login
    assert "password" not in data_login.get("user", {})
    assert "password_hash" not in data_login.get("user", {})
    print("  [PASS] Passwords and hashes are completely absent from API responses.")


async def test_06_login_success(client):
    """Test 6: Successful login returns access token and user info."""
    print("Test 6: Login Success...")
    res = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["email"] == "alice@example.com"
    print("  [PASS] Successful login issued valid bearer token and user object.")


async def test_07_invalid_password_rejection(client):
    """Test 7: Login with invalid password returns safe 401."""
    print("Test 7: Invalid Password Rejection...")
    res = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert "detail" in res.json()
    assert res.json()["detail"] == "Invalid email or password"
    print("  [PASS] Invalid password safely rejected with 401 Unauthorized.")


async def test_08_unknown_user_rejection(client):
    """Test 8: Login with nonexistent user returns safe 401."""
    print("Test 8: Unknown User Rejection...")
    res = await client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "AnyPassword123!"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"
    print("  [PASS] Unknown user rejected with uniform 401 Unauthorized message.")


def test_09_jwt_token_creation_and_structure(db):
    """Test 9: JWT access token creation, claims, and decoding."""
    print("Test 9: JWT Token Creation and Structure...")
    user = db.scalars(select(User).where(User.email == "alice@example.com")).first()
    token = create_access_token(user_id=user.id)
    assert isinstance(token, str)
    assert len(token) > 20

    payload = decode_access_token(token)
    assert payload["sub"] == str(user.id)
    assert "exp" in payload
    assert "iat" in payload
    assert payload["exp"] > payload["iat"]
    print("  [PASS] JWT token structure, subject claim, and timestamp verified.")


async def test_10_valid_token_authentication(client):
    """Test 10: Valid bearer token authenticates successfully on protected endpoint."""
    print("Test 10: Valid Token Authentication...")
    # Log in as Alice
    login_res = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]

    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"
    print("  [PASS] Valid Bearer token authenticated request on /api/auth/me.")


async def test_11_invalid_token_rejection(client):
    """Test 11: Malformed or invalid token returns HTTP 401."""
    print("Test 11: Invalid Token Rejection...")
    res = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-valid-token-string"})
    assert res.status_code == 401
    assert "detail" in res.json()
    print("  [PASS] Invalid token rejected with HTTP 401 Unauthorized.")


async def test_12_expired_token_rejection(client, db):
    """Test 12: Expired JWT token returns HTTP 401."""
    print("Test 12: Expired Token Rejection...")
    user = db.scalars(select(User).where(User.email == "alice@example.com")).first()
    expired_token = create_access_token(user_id=user.id, expires_delta=timedelta(seconds=-10))

    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()
    print("  [PASS] Expired token cleanly rejected with HTTP 401.")


async def test_13_missing_authorization_header(client):
    """Test 13: Protected endpoints reject requests without Authorization header."""
    print("Test 13: Missing Authorization Header...")
    res = await client.get("/api/auth/me")
    assert res.status_code == 401
    print("  [PASS] Missing Authorization header rejected with HTTP 401.")


async def test_14_get_auth_me_authenticated(client):
    """Test 14: GET /api/auth/me returns current user details."""
    print("Test 14: GET /api/auth/me Authenticated...")
    login_res = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]
    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"
    print("  [PASS] Authenticated user retrieved profile successfully.")


async def test_15_get_auth_me_unauthenticated(client):
    """Test 15: GET /api/auth/me returns 401 without credentials."""
    print("Test 15: GET /api/auth/me Unauthenticated...")
    res = await client.get("/api/auth/me")
    assert res.status_code == 401
    print("  [PASS] Unauthenticated access to /api/auth/me returned 401.")


async def test_16_saved_website_requires_authentication(client):
    """Test 16: Saved website operations require authentication."""
    print("Test 16: Saved Website Requires Authentication...")
    res_save = await client.post("/api/websites/901/save")
    assert res_save.status_code == 401

    res_unsave = await client.delete("/api/websites/901/save")
    assert res_unsave.status_code == 401

    res_list = await client.get("/api/websites/saved")
    assert res_list.status_code == 401

    res_csv = await client.get("/api/websites/saved/export/csv")
    assert res_csv.status_code == 401
    print("  [PASS] Unauthenticated access to all 4 saved endpoints returned HTTP 401.")


async def test_17_user_a_can_save_website(client):
    """Test 17: User A can save a website opportunity."""
    print("Test 17: User A Can Save Website...")
    login_a = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token_a = login_a.json()["access_token"]

    res = await client.post(
        "/api/websites/901/save",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    assert res.json()["is_saved"] is True
    assert res.json()["website_id"] == 901
    print("  [PASS] User A successfully bookmarked website #901.")


async def test_18_user_b_can_save_same_website(client):
    """Test 18: User B can independently bookmark the exact same website."""
    print("Test 18: User B Can Save Same Website Independently...")
    login_b = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # Bob saves website 901 as well
    res = await client.post(
        "/api/websites/901/save",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 200
    assert res.json()["is_saved"] is True
    print("  [PASS] User B successfully saved same website #901 without conflict.")


async def test_19_user_a_cannot_see_user_b_saved_websites(client):
    """Test 19: User A only sees their own saved websites."""
    print("Test 19: User Isolation in Saved Websites List...")
    login_a = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token_a = login_a.json()["access_token"]

    login_b = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # Bob saves website 902 as well (Alice does NOT save 902)
    await client.post(
        "/api/websites/902/save",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # Check Alice's saved list: should only have 1 site (901)
    res_a = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["total"] == 1
    assert data_a["items"][0]["website_id"] == 901

    # Check Bob's saved list: should have 2 sites (901 and 902)
    res_b = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["total"] == 2
    website_ids_b = {it["website_id"] for it in data_b["items"]}
    assert website_ids_b == {901, 902}
    print("  [PASS] User A and User B saved lists strictly isolated.")


async def test_20_duplicate_save_prevented_per_user(client):
    """Test 20: Duplicate save for the same user is idempotent."""
    print("Test 20: Duplicate Save Prevented Per User...")
    login_a = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token_a = login_a.json()["access_token"]

    res_dup = await client.post(
        "/api/websites/901/save",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_dup.status_code == 200
    assert "already saved" in res_dup.json()["message"].lower()

    # Verify list count is still 1
    list_res = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_a}"})
    assert list_res.json()["total"] == 1
    print("  [PASS] Duplicate save handled idempotently without duplicate records.")


async def test_21_user_a_unsave_does_not_affect_user_b(client):
    """Test 21: User A unsaving website 901 leaves User B's bookmark intact."""
    print("Test 21: User A Unsave Does Not Affect User B...")
    login_a = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token_a = login_a.json()["access_token"]

    login_b = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # Alice removes website 901
    res_unsave = await client.delete(
        "/api/websites/901/save",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_unsave.status_code == 200
    assert res_unsave.json()["is_saved"] is False

    # Alice's saved list is now empty
    res_a = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.json()["total"] == 0

    # Bob's saved list still has 2 sites (including 901)
    res_b = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.json()["total"] == 2
    b_ids = {it["website_id"] for it in res_b.json()["items"]}
    assert 901 in b_ids
    print("  [PASS] User A's unsave action did not affect User B's saved records.")


async def test_22_saved_csv_only_contains_current_user_records(client):
    """Test 22: GET /api/websites/saved/export/csv only exports the current user's records."""
    print("Test 22: Saved CSV Only Contains Current User's Records...")
    login_a = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token_a = login_a.json()["access_token"]

    login_b = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # Alice has 0 saved sites now
    res_a_csv = await client.get(
        "/api/websites/saved/export/csv",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a_csv.status_code == 200
    rows_a = list(csv.DictReader(io.StringIO(res_a_csv.content.decode("utf-8-sig"))))
    assert len(rows_a) == 0

    # Bob has 2 saved sites
    res_b_csv = await client.get(
        "/api/websites/saved/export/csv",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b_csv.status_code == 200
    rows_b = list(csv.DictReader(io.StringIO(res_b_csv.content.decode("utf-8-sig"))))
    assert len(rows_b) == 2
    domains_b = {row["Domain"] for row in rows_b}
    assert "alpha-tech.example.com" in domains_b
    assert "beta-health.example.com" in domains_b
    print("  [PASS] Saved CSV export strictly scoped to authenticated user.")


async def test_23_is_saved_is_user_specific(client):
    """Test 23: is_saved flag in website responses is calculated per authenticated user."""
    print("Test 23: is_saved Is User-Specific...")
    login_a = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    token_a = login_a.json()["access_token"]

    login_b = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "BobPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # Check website 902: Bob has it saved, Alice does NOT
    # Unauthenticated visitor: is_saved is False
    res_unauth = await client.get("/api/websites/902")
    assert res_unauth.status_code == 200
    assert res_unauth.json()["is_saved"] is False

    # Alice: is_saved is False
    res_alice = await client.get("/api/websites/902", headers={"Authorization": f"Bearer {token_a}"})
    assert res_alice.status_code == 200
    assert res_alice.json()["is_saved"] is False

    # Bob: is_saved is True
    res_bob = await client.get("/api/websites/902", headers={"Authorization": f"Bearer {token_b}"})
    assert res_bob.status_code == 200
    assert res_bob.json()["is_saved"] is True

    # Filter endpoint check
    res_filter_bob = await client.get("/api/websites/filter", headers={"Authorization": f"Bearer {token_b}"})
    assert res_filter_bob.status_code == 200
    bob_items = {it["id"]: it["is_saved"] for it in res_filter_bob.json()["items"]}
    assert bob_items[901] is True
    assert bob_items[902] is True

    res_filter_alice = await client.get("/api/websites/filter", headers={"Authorization": f"Bearer {token_a}"})
    assert res_filter_alice.status_code == 200
    alice_items = {it["id"]: it["is_saved"] for it in res_filter_alice.json()["items"]}
    assert alice_items[901] is False
    assert alice_items[902] is False
    print("  [PASS] is_saved accurately computed per user and defaults to False for guests.")


async def test_24_logout_behavior(client):
    """Test 24: POST /api/auth/logout returns success message."""
    print("Test 24: Logout Behavior...")
    res = await client.post("/api/auth/logout")
    assert res.status_code == 200
    assert "logged out" in res.json()["message"].lower()
    print("  [PASS] Logout endpoint confirmed successful stateless logout.")


async def test_25_full_auth_and_saved_flow(client):
    """Test 25: Full end-to-end user lifecycle and bookmarking workflow."""
    print("Test 25: Full Authentication and Saved Website Lifecycle...")
    # 1. Register User Carol
    reg_res = await client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "password": "CarolSecretPassword123!"},
    )
    assert reg_res.status_code == 201

    # 2. Login Carol
    log_res = await client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "CarolSecretPassword123!"},
    )
    assert log_res.status_code == 200
    token = log_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Verify /auth/me
    me_res = await client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "carol@example.com"

    # 4. Save website 901
    save_res = await client.post("/api/websites/901/save", headers=headers)
    assert save_res.status_code == 200
    assert save_res.json()["is_saved"] is True

    # 5. Check saved list
    saved_res = await client.get("/api/websites/saved", headers=headers)
    assert saved_res.status_code == 200
    assert saved_res.json()["total"] == 1

    # 6. Unsave website 901
    unsave_res = await client.delete("/api/websites/901/save", headers=headers)
    assert unsave_res.status_code == 200
    assert unsave_res.json()["is_saved"] is False

    # 7. Check empty saved list
    empty_res = await client.get("/api/websites/saved", headers=headers)
    assert empty_res.json()["total"] == 0

    # 8. Logout
    logout_res = await client.post("/api/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    print("  [PASS] Full end-to-end registration, login, bookmarking, and logout flow verified.")


# =====================================================================
# MAIN RUNNER
# =====================================================================

async def run_all_tests():
    init_db()
    db = SessionLocal()
    transport = httpx.ASGITransport(app=app)
    try:
        seed_test_database(db)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await test_01_user_registration_success(client, db)
            await test_02_registration_validation(client)
            await test_03_duplicate_email_rejection(client)
            test_04_password_is_hashed(db)
            await test_05_password_never_returned(client)
            await test_06_login_success(client)
            await test_07_invalid_password_rejection(client)
            await test_08_unknown_user_rejection(client)
            test_09_jwt_token_creation_and_structure(db)
            await test_10_valid_token_authentication(client)
            await test_11_invalid_token_rejection(client)
            await test_12_expired_token_rejection(client, db)
            await test_13_missing_authorization_header(client)
            await test_14_get_auth_me_authenticated(client)
            await test_15_get_auth_me_unauthenticated(client)
            await test_16_saved_website_requires_authentication(client)
            await test_17_user_a_can_save_website(client)
            await test_18_user_b_can_save_same_website(client)
            await test_19_user_a_cannot_see_user_b_saved_websites(client)
            await test_20_duplicate_save_prevented_per_user(client)
            await test_21_user_a_unsave_does_not_affect_user_b(client)
            await test_22_saved_csv_only_contains_current_user_records(client)
            await test_23_is_saved_is_user_specific(client)
            await test_24_logout_behavior(client)
            await test_25_full_auth_and_saved_flow(client)

        print("\n" + "=" * 70)
        print("ALL 25 STEP 21 AUDIT & INTEGRATION TESTS PASSED SUCCESSFULLY! [PASS]")
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
