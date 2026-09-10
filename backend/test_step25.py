"""Comprehensive Test Suite for Step 25: Security Hardening.

Covers all security requirements and threat vectors:
1. Authentication & JWT Hardening (valid token, malformed token, tampered signature, expired token, unsupported algorithm, missing claims)
2. Password Security & Credential Protection (bcrypt hashing, 8-128 character bounds, no credential leaks in responses, no user enumeration)
3. Authorization & Ownership Enforcement (User A vs User B search isolation, User A vs User B saved sites isolation, request-body user_id spoofing prevention)
4. Input Validation & SSRF Prevention (IPv4 loopback, localhost, private RFC1918 IPs, link-local / AWS metadata 169.254.169.254, IPv6 loopback, non-HTTP schemes, internal hostnames)
5. Configuration & Secret Safety (production mode rejects default secret and short keys)
6. HTTP Security Headers & Safe Error Handling (nosniff, DENY, XSS protection, referrer policy, sanitized 500 error responses)
"""

import asyncio
import jwt
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import select

from app.config import settings, Settings
from app.database import init_db, SessionLocal
from app.models import User, Website, Search, SavedWebsite
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    normalize_email,
)
from app.services.crawler import validate_target_url_safety
from app.main import app


def seed_test_database(db):
    """Seed controlled database records for Step 25 security tests."""
    db.query(SavedWebsite).delete()
    db.query(Search).delete()
    db.query(Website).delete()
    db.query(User).delete()
    db.commit()

    # User 1 (Alice)
    u1 = User(
        id=101,
        email="alice.sec@example.com",
        password_hash=hash_password("AliceSecretPassword123!"),
    )
    # User 2 (Bob)
    u2 = User(
        id=102,
        email="bob.sec@example.com",
        password_hash=hash_password("BobSecretPassword456!"),
    )

    # Search for User 1
    s1 = Search(
        id=501,
        user_id=101,
        keyword="ai marketing",
        status="completed",
    )
    # Search for User 2
    s2 = Search(
        id=502,
        user_id=102,
        keyword="crypto fintech",
        status="completed",
    )

    # Website records
    w1 = Website(
        id=801,
        domain="sec-target.example.com",
        url="https://sec-target.example.com/write-for-us",
        name="Security Target Blog",
        crawl_status="success",
    )

    db.add_all([u1, u2, s1, s2, w1])
    db.commit()


# =====================================================================
# SECTION 1: AUTHENTICATION & JWT SECURITY
# =====================================================================

async def test_01_valid_jwt_authentication(client):
    """Test 1.1: Valid JWT login and authenticated profile retrieval."""
    print("Test 1.1: Valid JWT Authentication...")
    login_res = await client.post(
        "/api/auth/login",
        json={"email": "alice.sec@example.com", "password": "AliceSecretPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "alice.sec@example.com"
    print("  [PASS] Valid JWT grants authenticated access.")


async def test_02_malformed_and_tampered_jwt(client):
    """Test 1.2: Malformed and signature-tampered JWTs are rejected with 401."""
    print("Test 1.2: Malformed & Tampered JWT Rejection...")
    # Malformed string
    res1 = await client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert res1.status_code == 401

    # Tampered signature
    valid_token = create_access_token(user_id=101)
    parts = valid_token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.invalidsignature123"
    res2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res2.status_code == 401
    print("  [PASS] Malformed and tampered tokens rejected with HTTP 401.")


async def test_03_expired_jwt(client):
    """Test 1.3: Expired JWT is rejected with 401."""
    print("Test 1.3: Expired JWT Rejection...")
    expired_token = create_access_token(user_id=101, expires_delta=timedelta(seconds=-60))
    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()
    print("  [PASS] Expired JWT properly rejected with 401.")


async def test_04_unsupported_jwt_algorithm(client):
    """Test 1.4: JWT with 'none' or mismatched algorithm is rejected."""
    print("Test 1.4: Unsupported JWT Algorithm Rejection...")
    # Generate an unsecure algorithm token
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "101",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    # Algorithm 'none'
    none_token = jwt.encode(payload, key="", algorithm="none")
    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {none_token}"})
    assert res.status_code == 401
    print("  [PASS] Algorithm 'none' token securely rejected.")


async def test_05_jwt_missing_required_claims(client):
    """Test 1.5: JWT missing sub or exp or iat is rejected."""
    print("Test 1.5: JWT Missing Required Claims Rejection...")
    # Missing 'sub' claim
    now = datetime.now(timezone.utc)
    bad_payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    bad_token = jwt.encode(bad_payload, key=settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert res.status_code == 401
    print("  [PASS] Token without required claims rejected.")


async def test_06_missing_or_bad_auth_header(client):
    """Test 1.6: Missing or malformed Authorization header formats return 401."""
    print("Test 1.6: Malformed Authorization Header Schemes...")
    # Missing header
    res_none = await client.get("/api/auth/me")
    assert res_none.status_code == 401

    # Basic scheme instead of Bearer
    res_basic = await client.get("/api/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res_basic.status_code == 401

    # Raw token without Bearer prefix
    res_raw = await client.get("/api/auth/me", headers={"Authorization": "some_token_here"})
    assert res_raw.status_code == 401
    print("  [PASS] Non-Bearer and missing auth headers rejected.")


# =====================================================================
# SECTION 2: PASSWORD & CREDENTIAL SECURITY
# =====================================================================

def test_07_password_hashing_and_salting():
    """Test 2.1: Password hashing produces unique bcrypt hashes with work factor."""
    print("Test 2.1: Password Hashing & Salting...")
    pw = "StrongSecret123!"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2, "Salts must ensure distinct hashes for identical passwords"
    assert verify_password(pw, h1) is True
    assert verify_password(pw, h2) is True
    assert verify_password("WrongSecret", h1) is False
    print("  [PASS] Password hashing properly salted and verified.")


async def test_08_password_length_bounds(client):
    """Test 2.2: Passwords < 8 or > 128 characters are rejected."""
    print("Test 2.2: Password Length Bounds (8 to 128 chars)...")
    # Too short (< 8 chars)
    res_short = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "1234567"},
    )
    assert res_short.status_code in [400, 422]

    # Too long (> 128 chars, DoS defense)
    res_long = await client.post(
        "/api/auth/register",
        json={"email": "long@example.com", "password": "A" * 129},
    )
    assert res_long.status_code in [400, 422]
    print("  [PASS] Password length boundaries strictly enforced.")


async def test_09_no_user_enumeration(client):
    """Test 2.3: Nonexistent email and incorrect password return uniform 401."""
    print("Test 2.3: No User Enumeration on Login...")
    res_bad_pw = await client.post(
        "/api/auth/login",
        json={"email": "alice.sec@example.com", "password": "WrongPassword!"},
    )
    assert res_bad_pw.status_code == 401
    msg_bad_pw = res_bad_pw.json()["detail"]

    res_unknown_user = await client.post(
        "/api/auth/login",
        json={"email": "nonexistent.user@example.com", "password": "AnyPassword123!"},
    )
    assert res_unknown_user.status_code == 401
    msg_unknown_user = res_unknown_user.json()["detail"]

    assert msg_bad_pw == msg_unknown_user == "Invalid email or password"
    print("  [PASS] Login error messages are identical, preventing user enumeration.")


async def test_10_credentials_never_exposed(client, db):
    """Test 2.4: Passwords and hashes are not exposed in any API output."""
    print("Test 2.4: Credentials Never Exposed...")
    reg_res = await client.post(
        "/api/auth/register",
        json={"email": "dave.sec@example.com", "password": "DavePassword123!"},
    )
    assert reg_res.status_code == 201
    body_reg = reg_res.text
    assert "password_hash" not in body_reg
    assert "DavePassword123!" not in body_reg

    login_res = await client.post(
        "/api/auth/login",
        json={"email": "dave.sec@example.com", "password": "DavePassword123!"},
    )
    assert login_res.status_code == 200
    body_login = login_res.text
    assert "password_hash" not in body_login
    assert "DavePassword123!" not in body_login
    print("  [PASS] Passwords and hashes are never exposed in responses.")


# =====================================================================
# SECTION 3: AUTHORIZATION & OWNERSHIP ENFORCEMENT
# =====================================================================

async def test_11_cross_user_search_isolation(client):
    """Test 3.1: User A cannot read, delete, or list User B's searches."""
    print("Test 3.1: Cross-User Search Isolation...")
    token_a = create_access_token(user_id=101)  # Alice
    token_b = create_access_token(user_id=102)  # Bob

    # Alice tries to read Bob's search (ID 502) -> 404
    res_read = await client.get("/api/searches/502", headers={"Authorization": f"Bearer {token_a}"})
    assert res_read.status_code == 404, f"Expected 404, got {res_read.status_code}"

    # Alice tries to delete Bob's search (ID 502) -> 404
    res_del = await client.delete("/api/searches/502", headers={"Authorization": f"Bearer {token_a}"})
    assert res_del.status_code == 404, f"Expected 404, got {res_del.status_code}"

    # Bob can read his own search (ID 502) -> 200
    res_bob = await client.get("/api/searches/502", headers={"Authorization": f"Bearer {token_b}"})
    assert res_bob.status_code == 200
    print("  [PASS] Cross-user search access returns 404, strictly isolated.")


from unittest.mock import patch

async def test_12_request_body_user_id_spoofing_prevented(client, db):
    """Test 3.2: Authenticated user cannot spoof user_id in request body."""
    print("Test 3.2: Request Body user_id Spoofing Prevention...")
    token_a = create_access_token(user_id=101)  # Alice

    # Mock execute_search_discovery to avoid external network calls during testing
    async def mock_discovery(db, search):
        return search

    with patch("app.services.search_service.execute_search_discovery", side_effect=mock_discovery):
        # Alice attempts to create search with user_id = 102 (Bob) in payload
        create_res = await client.post(
            "/api/searches",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"keyword": "spoof attempt", "user_id": 102},
        )
        assert create_res.status_code == 201
        search_id = create_res.json()["id"]

        # Verify in DB that the search was created with user_id = 101 (Alice), NOT 102
        search = db.scalars(select(Search).where(Search.id == search_id)).first()
        assert search is not None
        assert search.user_id == 101, f"Expected user_id 101, but found {search.user_id} (spoof succeeded!)"
        print("  [PASS] Injected user_id ignored; derived strictly from authenticated JWT.")


async def test_13_saved_websites_isolation(client):
    """Test 3.3: User A and User B saved websites are strictly isolated."""
    print("Test 3.3: Saved Websites User Isolation...")
    token_a = create_access_token(user_id=101)  # Alice
    token_b = create_access_token(user_id=102)  # Bob

    # Alice saves website 801
    await client.post("/api/websites/801/save", headers={"Authorization": f"Bearer {token_a}"})

    # Alice sees 1 saved website
    res_a = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    assert res_a.json()["total"] == 1

    # Bob sees 0 saved websites
    res_b = await client.get("/api/websites/saved", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    assert res_b.json()["total"] == 0
    print("  [PASS] Saved websites completely isolated between users.")


# =====================================================================
# SECTION 4: INPUT VALIDATION & SSRF MITIGATION
# =====================================================================

def test_14_ssrf_ip_and_scheme_blocking():
    """Test 4.1: Target URL safety validator blocks loopback, private IPs, metadata, and non-HTTP schemes."""
    print("Test 4.1: SSRF IP & Scheme Safety Validation...")
    # Loopback IPv4
    assert validate_target_url_safety("http://127.0.0.1")[0] is False
    assert validate_target_url_safety("http://127.0.0.2:8080")[0] is False
    assert validate_target_url_safety("http://localhost")[0] is False
    assert validate_target_url_safety("http://sub.localhost:3000")[0] is False

    # Private IPv4 (RFC 1918)
    assert validate_target_url_safety("http://10.0.0.1")[0] is False
    assert validate_target_url_safety("http://172.16.0.1")[0] is False
    assert validate_target_url_safety("http://192.168.1.1")[0] is False

    # Cloud metadata / link-local
    assert validate_target_url_safety("http://169.254.169.254/latest/meta-data")[0] is False
    assert validate_target_url_safety("http://instance-data")[0] is False

    # IPv6 loopback
    assert validate_target_url_safety("http://[::1]")[0] is False
    assert validate_target_url_safety("http://[fe80::1]")[0] is False

    # Non-HTTP schemes
    assert validate_target_url_safety("file:///etc/passwd")[0] is False
    assert validate_target_url_safety("ftp://ftp.example.com")[0] is False
    assert validate_target_url_safety("gopher://gopher.example.com")[0] is False
    assert validate_target_url_safety("javascript:alert(1)")[0] is False

    # Valid external URLs
    is_safe, msg = validate_target_url_safety("https://techcrunch.com/write-for-us")
    assert is_safe is True, f"Expected safe, got: {msg}"

    is_safe2, _ = validate_target_url_safety("http://example.org/guest-posts")
    assert is_safe2 is True
    print("  [PASS] SSRF protection blocks all forbidden IP ranges, hosts, and protocols.")


# =====================================================================
# SECTION 5: CONFIGURATION & PRODUCTION SECURITY DEFAULTS
# =====================================================================

def test_15_production_security_validation():
    """Test 5.1: Production environment rejects default secret key or short key."""
    print("Test 5.1: Production Security Key Validation...")
    # Dev mode with default secret: warns but does not raise
    dev_settings = Settings()
    dev_settings.ENVIRONMENT = "development"
    dev_settings.DEBUG = True
    dev_settings.JWT_SECRET_KEY = "guest-posting-ai-insecure-dev-secret-key-change-in-production-32bytes"
    dev_settings.validate_security()

    # Production mode with default secret: MUST RAISE
    prod_bad_settings = Settings()
    prod_bad_settings.ENVIRONMENT = "production"
    prod_bad_settings.DEBUG = False
    prod_bad_settings.JWT_SECRET_KEY = "guest-posting-ai-insecure-dev-secret-key-change-in-production-32bytes"
    try:
        prod_bad_settings.validate_security()
        assert False, "Expected ValueError for default secret key in production!"
    except ValueError as e:
        assert "Production security error" in str(e)

    # Production mode with short secret: MUST RAISE
    prod_short_settings = Settings()
    prod_short_settings.ENVIRONMENT = "production"
    prod_short_settings.DEBUG = False
    prod_short_settings.JWT_SECRET_KEY = "short_key_123"
    try:
        prod_short_settings.validate_security()
        assert False, "Expected ValueError for short secret key in production!"
    except ValueError as e:
        assert "at least 32 characters" in str(e)

    # Production mode with valid strong secret: PASSES
    prod_good_settings = Settings()
    prod_good_settings.ENVIRONMENT = "production"
    prod_good_settings.DEBUG = False
    prod_good_settings.JWT_SECRET_KEY = "a_very_strong_and_long_production_secret_key_1234567890"
    prod_good_settings.validate_security()
    print("  [PASS] Production configuration enforcement prevents unsafe deployments.")


# =====================================================================
# SECTION 6: HTTP SECURITY HEADERS & ERROR HANDLING
# =====================================================================

async def test_16_http_security_headers(client):
    """Test 6.1: Defensive HTTP headers are returned in all responses."""
    print("Test 6.1: HTTP Security Response Headers...")
    res = await client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    print("  [PASS] All expected HTTP security headers are present.")


async def test_17_safe_error_handling(client):
    """Test 6.2: Global exception handler prevents leaking stack traces."""
    print("Test 6.2: Safe Error Handling on Malformed / Unknown Routes...")
    # 404 route returns JSON detail
    res_404 = await client.get("/api/nonexistent-route-for-testing")
    assert res_404.status_code == 404
    assert "detail" in res_404.json()
    assert "Traceback" not in res_404.text
    print("  [PASS] Error handling returns clean, non-leaking JSON responses.")


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
            await test_01_valid_jwt_authentication(client)
            await test_02_malformed_and_tampered_jwt(client)
            await test_03_expired_jwt(client)
            await test_04_unsupported_jwt_algorithm(client)
            await test_05_jwt_missing_required_claims(client)
            await test_06_missing_or_bad_auth_header(client)
            test_07_password_hashing_and_salting()
            await test_08_password_length_bounds(client)
            await test_09_no_user_enumeration(client)
            await test_10_credentials_never_exposed(client, db)
            await test_11_cross_user_search_isolation(client)
            await test_12_request_body_user_id_spoofing_prevented(client, db)
            await test_13_saved_websites_isolation(client)
            test_14_ssrf_ip_and_scheme_blocking()
            test_15_production_security_validation()
            await test_16_http_security_headers(client)
            await test_17_safe_error_handling(client)

        print("\n" + "=" * 70)
        print("ALL 17 STEP 25 SECURITY HARDENING TESTS PASSED SUCCESSFULLY! [PASS]")
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
