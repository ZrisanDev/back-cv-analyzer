"""Pydantic schemas for authentication requests and responses."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Registration / Login ────────────────────────────────────


class UserCreate(BaseModel):
    """Payload for user registration."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Juan Pérez"])
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: EmailStr
    password: str


# ── Token responses ─────────────────────────────────────────


class TokenResponse(BaseModel):
    """JWT tokens returned after successful login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    """Payload to exchange a valid refresh token for a new pair."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Body for logout — include the refresh token to fully invalidate the session."""

    refresh_token: str | None = None


# ── User responses ──────────────────────────────────────────


class UserResponse(BaseModel):
    """Public user information (never includes password)."""

    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    free_analyses_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Password reset ──────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    """Payload to request a password-reset email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload to actually reset the password using a token."""

    token: str = Field(..., min_length=1, description="JWT password-reset token")
    new_password: str = Field(..., min_length=6, max_length=128)
