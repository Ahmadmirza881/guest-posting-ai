"""Authentication routes for registration, login, profile inspection, and logout (Step 21)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    GoogleAuthRequest,
    GoogleConfigResponse,
    UserResponse,
    TokenResponse,
    MessageResponse,
)
from app.services.google_auth import (
    verify_google_credential,
    authenticate_or_create_google_user,
)
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    normalize_email,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new platform user with normalized email and secure bcrypt password hashing."""
    email = normalize_email(payload.email)

    # Check for duplicate email
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    # Hash password securely
    hashed = hash_password(payload.password)

    user = User(
        email=email,
        password_hash=hashed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and issue JWT access token",
)
def login(
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
):
    """Verify user credentials and issue a signed JWT access token."""
    email = normalize_email(payload.email)

    user = db.scalars(select(User).where(User.email == email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    """Return the profile of the currently authenticated user without exposing sensitive credentials."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out user",
)
def logout():
    """Stateless JWT logout confirmation.

    Client-side application discards the stored access token from storage.
    """
    return MessageResponse(message="Logged out successfully")


@router.get(
    "/google/config",
    response_model=GoogleConfigResponse,
    summary="Get public Google OAuth configuration",
)
def get_google_config():
    """Return public Google OAuth client configuration for frontend initialization."""
    import os
    from dotenv import dotenv_values
    from app.config import ENV_FILE

    env_vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    client_id = (
        env_vals.get("GOOGLE_CLIENT_ID")
        or os.getenv("GOOGLE_CLIENT_ID")
        or settings.GOOGLE_CLIENT_ID
    )
    return GoogleConfigResponse(
        client_id=client_id,
        enabled=bool(client_id),
    )


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Authenticate or register user via Google OAuth",
)
def google_auth(
    payload: GoogleAuthRequest,
    db: Session = Depends(get_db),
):
    """Authenticate or register user via Google OAuth and issue JWT access token."""
    user_info = verify_google_credential(
        credential=payload.credential,
        access_token=payload.access_token,
        fallback_email=payload.email,
        fallback_name=payload.full_name,
        fallback_avatar=payload.avatar_url,
        fallback_google_id=payload.google_id,
    )
    user = authenticate_or_create_google_user(db, user_info)
    access_token = create_access_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )
