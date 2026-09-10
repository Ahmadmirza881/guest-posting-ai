"""Comprehensive tests for Google Sign-In backend integration."""

from unittest.mock import patch, MagicMock
import httpx
from sqlalchemy import select

from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.utils.security import hash_password, verify_password


def setup_function():
    """Ensure clean test environment before each test."""
    init_db()
    db = SessionLocal()
    try:
        db.query(User).filter(User.email.like("%@test-google.com")).delete()
        db.commit()
    finally:
        db.close()


def teardown_function():
    """Clean up test users after each test."""
    db = SessionLocal()
    try:
        db.query(User).filter(User.email.like("%@test-google.com")).delete()
        db.commit()
    finally:
        db.close()


async def test_google_config_endpoint():
    """Verify GET /api/auth/google/config returns configuration correctly."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/auth/google/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "client_id" in data
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)


async def test_google_login_creates_new_user():
    """Verify Google login creates a new user if one does not exist."""
    test_email = "newuser@test-google.com"
    payload = {
        "email": test_email,
        "full_name": "New Google User",
        "avatar_url": "https://example.com/avatar.jpg",
        "google_id": "google_uid_12345",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/auth/google", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == test_email
        assert data["user"]["full_name"] == "New Google User"
        assert data["user"]["avatar_url"] == "https://example.com/avatar.jpg"
        assert data["user"]["auth_provider"] == "google"

        # Verify token works on /api/auth/me
        token = data["access_token"]
        me_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == test_email

    # Verify database state
    db = SessionLocal()
    try:
        user = db.scalars(select(User).where(User.email == test_email)).first()
        assert user is not None
        assert user.google_id == "google_uid_12345"
        assert user.password_hash is None
        assert user.auth_provider == "google"
    finally:
        db.close()


async def test_google_login_links_existing_user_and_preserves_password():
    """Verify Google login signs into existing account and keeps password login working."""
    test_email = "existinguser@test-google.com"
    raw_password = "SecurePassword123!"

    # Seed existing user with password
    db = SessionLocal()
    try:
        existing = User(
            email=test_email,
            password_hash=hash_password(raw_password),
            full_name="Existing Local User",
            auth_provider="local",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        user_id = existing.id
    finally:
        db.close()

    payload = {
        "email": test_email,
        "full_name": "Existing Local User",
        "avatar_url": "https://example.com/google_photo.jpg",
        "google_id": "google_uid_67890",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Sign in via Google
        google_resp = await client.post("/api/auth/google", json=payload)
        assert google_resp.status_code == 200
        g_data = google_resp.json()
        assert g_data["user"]["id"] == user_id
        assert g_data["user"]["email"] == test_email

        # 2. Verify normal email/password login still works 100%
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": test_email, "password": raw_password},
        )
        assert login_resp.status_code == 200
        l_data = login_resp.json()
        assert l_data["user"]["id"] == user_id
        assert l_data["user"]["email"] == test_email

    # Verify in DB that google_id is linked and password_hash is intact
    db = SessionLocal()
    try:
        user = db.scalars(select(User).where(User.id == user_id)).first()
        assert user.google_id == "google_uid_67890"
        assert user.password_hash is not None
        assert verify_password(raw_password, user.password_hash)
    finally:
        db.close()


async def test_google_returning_user_login():
    """Verify returning Google user is recognized and logged in by google_id."""
    test_email = "returning@test-google.com"
    google_id = "google_uid_returning_999"

    db = SessionLocal()
    try:
        user = User(
            email=test_email,
            password_hash=None,
            full_name="Returning User",
            auth_provider="google",
            google_id=google_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        existing_id = user.id
    finally:
        db.close()

    payload = {
        "email": test_email,
        "google_id": google_id,
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/auth/google", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["id"] == existing_id
        assert data["user"]["email"] == test_email


async def test_google_verified_credential_token_mock():
    """Verify credential token parsing and validation with Google tokeninfo mock."""
    from app.config import settings

    mock_tokeninfo_response = MagicMock()
    mock_tokeninfo_response.status_code = 200
    mock_tokeninfo_response.json.return_value = {
        "aud": settings.GOOGLE_CLIENT_ID or "mock_aud",
        "sub": "mock_sub_101010",
        "email": "tokenuser@test-google.com",
        "email_verified": "true",
        "name": "Token Verified User",
        "picture": "https://lh3.googleusercontent.com/avatar",
    }

    with patch("httpx.Client.get", return_value=mock_tokeninfo_response):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/google",
                json={"credential": "mock.google.jwt.token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["user"]["email"] == "tokenuser@test-google.com"
            assert data["user"]["full_name"] == "Token Verified User"


async def test_google_invalid_credential_token_rejected():
    """Verify invalid or expired Google credential returns HTTP 401."""
    mock_invalid_response = MagicMock()
    mock_invalid_response.status_code = 400
    mock_invalid_response.json.return_value = {"error": "invalid_token"}

    with patch("httpx.Client.get", return_value=mock_invalid_response):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/google",
                json={"credential": "bad_token_123"},
            )
            assert resp.status_code == 401
            assert "Invalid or expired Google credential token" in resp.json()["detail"]


async def test_google_unverified_email_rejected():
    """Verify unverified Google email returns HTTP 400."""
    from app.config import settings

    mock_unverified_response = MagicMock()
    mock_unverified_response.status_code = 200
    mock_unverified_response.json.return_value = {
        "aud": settings.GOOGLE_CLIENT_ID or "mock_aud",
        "sub": "mock_sub_unverified",
        "email": "unverified@test-google.com",
        "email_verified": "false",
        "name": "Unverified User",
    }

    with patch("httpx.Client.get", return_value=mock_unverified_response):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/google",
                json={"credential": "unverified_email_token"},
            )
            assert resp.status_code == 400
            assert "Google email address is not verified" in resp.json()["detail"]


if __name__ == "__main__":
    import asyncio

    async def main():
        print("Running Google Auth Tests...")
        setup_function()
        try:
            await test_google_config_endpoint()
            print("  [PASS] test_google_config_endpoint")

            await test_google_login_creates_new_user()
            print("  [PASS] test_google_login_creates_new_user")

            await test_google_login_links_existing_user_and_preserves_password()
            print("  [PASS] test_google_login_links_existing_user_and_preserves_password")

            await test_google_returning_user_login()
            print("  [PASS] test_google_returning_user_login")

            await test_google_verified_credential_token_mock()
            print("  [PASS] test_google_verified_credential_token_mock")

            await test_google_invalid_credential_token_rejected()
            print("  [PASS] test_google_invalid_credential_token_rejected")

            await test_google_unverified_email_rejected()
            print("  [PASS] test_google_unverified_email_rejected")

            print("\n==================================================")
            print("ALL GOOGLE AUTH INTEGRATION TESTS PASSED! [PASS]")
            print("==================================================")
        finally:
            teardown_function()

    asyncio.run(main())
