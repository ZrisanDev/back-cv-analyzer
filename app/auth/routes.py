"""Auth routes: register, login, refresh, logout, password recovery."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    ResetPasswordRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.auth.services import (
    authenticate_user,
    blacklist_token,
    build_token_pair,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_token_blacklisted,
    mark_reset_token_used,
    register_user,
    store_reset_token,
    validate_password_reset_token,
)
from app.shared.database import get_db
from app.shared.email import send_password_reset_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Registration ────────────────────────────────────────────


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user with email + password. Returns the user record."""
    return await register_user(
        db=db,
        name=payload.name,
        email=payload.email,
        password=payload.password,
    )


# ── Login ───────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain tokens",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Verify credentials and return an access + refresh token pair."""
    user = await authenticate_user(db, payload.email, payload.password)
    return build_token_pair(user)


# ── Refresh ─────────────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a valid refresh token for a new token pair",
)
async def refresh(
    payload: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Accepts a non-revoked refresh token and issues a fresh pair.

    The old refresh token is immediately blacklisted.
    """
    payload_data = decode_token(payload.refresh_token)

    if payload_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )

    jti = payload_data.get("jti")
    if jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing identifier",
        )

    if await is_token_blacklisted(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    user_id_str = payload_data.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    # Blacklist the consumed refresh token
    exp_ts: float | None = payload_data.get("exp")
    if exp_ts is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing expiration",
        )
    await blacklist_token(
        db,
        jti,
        "refresh",
        user_id_str,
        datetime.fromtimestamp(exp_ts, tz=timezone.utc),
    )

    # Issue a brand-new token pair
    new_access, _ = create_access_token(uuid.UUID(user_id_str))
    new_refresh, _ = create_refresh_token(uuid.UUID(user_id_str))
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


# ── Logout ──────────────────────────────────────────────────


@router.post(
    "/logout",
    summary="Revoke tokens and end the session",
)
async def logout(
    body: LogoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Blacklist the access token (from the Authorization header) and
    optionally the refresh token provided in the request body.

    After this call both tokens become unusable.
    """
    # ── Blacklist access token ─────────────────────────────
    auth_header: str | None = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_access = auth_header[7:].strip()
        try:
            access_payload = decode_token(raw_access)
            jti = access_payload.get("jti")
            exp_ts = access_payload.get("exp")
            if jti and exp_ts:
                await blacklist_token(
                    db,
                    jti,
                    "access",
                    str(current_user.id),
                    datetime.fromtimestamp(exp_ts, tz=timezone.utc),
                )
        except HTTPException:
            pass  # Access token already validated by get_current_user

    # ── Blacklist refresh token (if provided) ──────────────
    if body.refresh_token:
        try:
            refresh_payload = decode_token(body.refresh_token)
            if refresh_payload.get("type") == "refresh":
                r_jti = refresh_payload.get("jti")
                r_exp = refresh_payload.get("exp")
                if r_jti and r_exp:
                    await blacklist_token(
                        db,
                        r_jti,
                        "refresh",
                        str(current_user.id),
                        datetime.fromtimestamp(r_exp, tz=timezone.utc),
                    )
        except HTTPException:
            pass  # Ignore invalid or expired refresh token

    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Protected route example ─────────────────────────────────


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the profile of the currently authenticated user."""
    return current_user


# ── Password recovery ───────────────────────────────────────


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request a password-reset email",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a password-reset email if the account exists.

    Always returns 200 — never reveals whether the email is registered.
    """
    result = await db.execute(
        select(User).where(User.email == payload.email),
    )
    user = result.scalar_one_or_none()

    if user is not None:
        try:
            token, jti = create_password_reset_token(user.id)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            await store_reset_token(db, jti, user.id, expires_at)
            await send_password_reset_email(to_email=user.email, reset_token=token)
        except Exception:
            # Log but don't reveal errors — we must not leak info
            logger.exception(
                "Error generating password-reset token for %s",
                payload.email,
            )

    return {
        "message": "Si el correo está registrado, recibirás un enlace para restablecer la contraseña."
    }


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password using a token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate the reset token and update the user's password."""
    # 1. Validate the token (JWT signature, type, single-use)
    token_payload = await validate_password_reset_token(db, payload.token)

    # 2. Resolve the user
    user_id_str = token_payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token sin sujeto.",
        )
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identificador de usuario inválido.",
        ) from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario no encontrado.",
        )

    # 3. Update the password
    user.hashed_password = hash_password(payload.new_password)

    # 4. Mark the token as used (single-use enforcement)
    jti = token_payload.get("jti")
    if jti:
        await mark_reset_token_used(db, jti)

    await db.flush()

    return {"message": "Contraseña actualizada correctamente."}
