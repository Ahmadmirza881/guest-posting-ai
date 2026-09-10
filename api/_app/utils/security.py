"""Security and cryptographic utilities for password hashing and JWT tokens (Step 21)."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict
import bcrypt
import jwt
from app.config import settings


def normalize_email(email: str) -> str:
    """Normalize email address consistently across the platform."""
    if not email:
        return ""
    return email.strip().lower()


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password securely using bcrypt with length bounding."""
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(plain_password) > 128:
        raise ValueError("Password cannot exceed 128 characters.")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash safely."""
    if not plain_password or not hashed_password:
        return False
    if len(plain_password) > 128:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a signed JWT access token with required subject, timestamp, and expiration claims.

    Args:
        user_id: The positive integer ID of the authenticated user.
        expires_delta: Optional custom duration. Defaults to configured expiration.
        extra_claims: Optional non-sensitive extra claims.

    Returns:
        Encoded JWT token string.
    """
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        for k, v in extra_claims.items():
            if k not in ("sub", "exp", "iat"):
                payload[k] = v

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token with strict signature, claim, and algorithm verification.

    Args:
        token: Encoded JWT token string.

    Returns:
        Decoded payload dictionary.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token signature is invalid, claims are missing, or algorithm is unexpected.
    """
    if not token or not isinstance(token, str):
        raise jwt.InvalidTokenError("Token string must be non-empty.")

    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={
            "require": ["sub", "exp", "iat"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
        },
    )
