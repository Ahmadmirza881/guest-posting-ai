"""Google OAuth verification and user synchronization service."""

import logging
from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.utils.security import normalize_email

logger = logging.getLogger("guest_posting_ai.google_auth")


def verify_google_credential(
    credential: Optional[str] = None,
    access_token: Optional[str] = None,
    fallback_email: Optional[str] = None,
    fallback_name: Optional[str] = None,
    fallback_avatar: Optional[str] = None,
    fallback_google_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify Google token (ID token or OAuth2 access token) and extract user profile.

    Args:
        credential: Google ID token (JWT) from Google Identity Services.
        access_token: Google OAuth2 Bearer access token from Google Token Client.
        fallback_email: Optional email for development/test mode.
        fallback_name: Optional name for development/test mode.
        fallback_avatar: Optional avatar URL for development/test mode.
        fallback_google_id: Optional google ID for development/test mode.

    Returns:
        Dict containing normalized email, google_id, full_name, and avatar_url.

    Raises:
        HTTPException: If token is missing, invalid, expired, or unverified.
    """
    # 1. Verify via Google ID Token (Google Identity Services credential)
    if credential:
        try:
            url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)

            if resp.status_code != 200:
                logger.warning(f"Google ID token verification failed with HTTP status {resp.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired Google credential token.",
                )

            data = resp.json()

            # Verify audience matches configured client ID if configured
            if settings.GOOGLE_CLIENT_ID and data.get("aud") != settings.GOOGLE_CLIENT_ID:
                logger.warning(
                    f"Google token audience mismatch: expected {settings.GOOGLE_CLIENT_ID}, got {data.get('aud')}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google token was not issued for this application.",
                )

            email = normalize_email(data.get("email"))
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google account does not provide a valid email address.",
                )

            email_verified = data.get("email_verified")
            if email_verified not in (True, "true", "True"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google email address is not verified.",
                )

            return {
                "email": email,
                "google_id": str(data.get("sub", "")),
                "full_name": data.get("name") or fallback_name,
                "avatar_url": data.get("picture") or fallback_avatar,
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error during Google ID token verification: {exc}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to verify Google credential token.",
            )

    # 2. Verify via Google OAuth2 Access Token
    if access_token:
        try:
            url = "https://www.googleapis.com/oauth2/v3/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=headers)

            if resp.status_code != 200:
                logger.warning(f"Google access token verification failed with HTTP status {resp.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired Google access token.",
                )

            data = resp.json()

            email = normalize_email(data.get("email"))
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google account does not provide a valid email address.",
                )

            email_verified = data.get("email_verified")
            if email_verified not in (True, "true", "True"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google email address is not verified.",
                )

            return {
                "email": email,
                "google_id": str(data.get("sub", "")),
                "full_name": data.get("name") or fallback_name,
                "avatar_url": data.get("picture") or fallback_avatar,
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error during Google access token verification: {exc}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to verify Google access token.",
            )

    # 3. Fallback for development, testing, and non-production environments
    if (settings.DEBUG or settings.ENVIRONMENT != "production") and fallback_email:
        clean_email = normalize_email(fallback_email)
        if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format in Google authentication payload.",
            )

        return {
            "email": clean_email,
            "google_id": fallback_google_id or f"mock_google_{clean_email}",
            "full_name": fallback_name or clean_email.split("@")[0].capitalize(),
            "avatar_url": fallback_avatar,
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Missing Google OAuth credential or access token.",
    )


def authenticate_or_create_google_user(
    db: Session,
    user_info: Dict[str, Any],
) -> User:
    """Find existing user by google_id or email, or create a new user entity.

    Rules:
    - If user exists by google_id: return user.
    - If user exists by email: link google_id and profile fields, preserve password_hash, return user.
    - If user does not exist: create user with auth_provider='google', password_hash=None, return user.
    """
    email = user_info["email"]
    google_id = user_info.get("google_id")
    full_name = user_info.get("full_name")
    avatar_url = user_info.get("avatar_url")

    # 1. Search by google_id
    user = None
    if google_id:
        user = db.scalars(select(User).where(User.google_id == google_id)).first()

    # 2. Search by normalized email
    if not user:
        user = db.scalars(select(User).where(User.email == email)).first()
        if user:
            # Existing account: link Google ID and update metadata if missing, preserve password_hash
            if google_id and not user.google_id:
                user.google_id = google_id
            if full_name and not user.full_name:
                user.full_name = full_name
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            db.commit()
            db.refresh(user)

    # 3. Create new user entity if not found
    if not user:
        user = User(
            email=email,
            password_hash=None,
            full_name=full_name,
            avatar_url=avatar_url,
            auth_provider="google",
            google_id=google_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
