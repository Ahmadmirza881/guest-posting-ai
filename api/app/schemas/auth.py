"""Pydantic schemas for authentication and user accounts (Step 21)."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class UserRegisterRequest(BaseModel):
    """Schema for user registration request."""
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v or len(v) > 255 or "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("A valid email address (max 255 characters) is required.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v) > 128:
            raise ValueError("Password cannot exceed 128 characters.")
        return v


class UserLoginRequest(BaseModel):
    """Schema for user login request."""
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if len(v) > 255:
            raise ValueError("Email cannot exceed 255 characters.")
        return v

    @field_validator("password")
    @classmethod
    def check_password_length(cls, v: str) -> str:
        if len(v) > 128:
            raise ValueError("Password cannot exceed 128 characters.")
        return v


class GoogleAuthRequest(BaseModel):
    """Schema for Google OAuth token / credential payload."""
    credential: Optional[str] = None
    access_token: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    google_id: Optional[str] = None


class GoogleConfigResponse(BaseModel):
    """Schema for Google OAuth public client settings."""
    client_id: Optional[str] = None
    enabled: bool = False


class UserResponse(BaseModel):
    """Schema for public user information (never exposes password or hash)."""
    id: int
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    auth_provider: Optional[str] = "local"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Schema for access token responses."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    """Schema for standard message responses."""
    message: str

