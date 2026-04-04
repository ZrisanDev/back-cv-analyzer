"""Authentication service: password hashing, JWT tokens, blacklist."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import PasswordResetToken, TokenBlacklist, User
from app.auth.schemas import TokenResponse
from app.shared.config import settings

# ── Password hashing ────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT helpers ─────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: uuid.UUID,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """Create a short-lived access token. Returns (token, jti)."""
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = _now_utc()
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "access",
        "iat": now,
        "exp": now + delta,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti


def create_refresh_token(
    user_id: uuid.UUID,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """Create a longer-lived refresh token. Returns (token, jti)."""
    delta = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    now = _now_utc()
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": now + delta,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Token blacklist ─────────────────────────────────────────


async def blacklist_token(
    db: AsyncSession,
    jti: str,
    token_type: str,
    user_id: str,
    expires_at: datetime,
) -> None:
    """Insert a token into the blacklist so it can no longer be used."""
    entry = TokenBlacklist(
        jti=jti,
        token_type=token_type,
        user_id=user_id,
        expires_at=expires_at,
    )
    db.add(entry)
    await db.flush()


async def is_token_blacklisted(db: AsyncSession, jti: str) -> bool:
    """Check whether a token's JTI appears in the blacklist."""
    result = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == jti),
    )
    return result.scalar_one_or_none() is not None


# ── High-level auth operations ──────────────────────────────


async def register_user(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
) -> User:
    """Create a new user account. Raises 400 if email already exists."""
    existing = await db.execute(
        select(User).where(User.email == email),
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User:
    """Verify credentials and return the user. Raises 401 on failure."""
    result = await db.execute(
        select(User).where(User.email == email),
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return user


def build_token_pair(user: User) -> TokenResponse:
    """Generate an access + refresh token pair for a user."""
    access_token, _ = create_access_token(user.id)
    refresh_token, _ = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


async def logout_user(
    db: AsyncSession,
    access_jti: str,
    refresh_jti: str,
    user_id: str,
    access_exp: datetime,
    refresh_exp: datetime,
) -> None:
    """Blacklist both tokens to fully log out the user."""
    await blacklist_token(db, access_jti, "access", user_id, access_exp)
    await blacklist_token(db, refresh_jti, "refresh", user_id, refresh_exp)
    await db.flush()


# ── Password reset ──────────────────────────────────────────

RESET_TOKEN_EXPIRE_HOURS = 1


def create_password_reset_token(
    user_id: uuid.UUID,
) -> tuple[str, str]:
    """Create a short-lived JWT for password reset. Returns (token, jti).

    The token payload contains type="password_reset" and expires in 1 hour.
    """
    delta = timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)
    now = _now_utc()
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "password_reset",
        "iat": now,
        "exp": now + delta,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti


async def store_reset_token(
    db: AsyncSession,
    jti: str,
    user_id: uuid.UUID,
    expires_at: datetime,
) -> None:
    """Persist the password-reset token so we can enforce single-use."""
    record = PasswordResetToken(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at,
    )
    db.add(record)
    await db.flush()


async def validate_password_reset_token(
    db: AsyncSession,
    token: str,
) -> dict:
    """Decode and validate a password-reset token.

    Returns the JWT payload dict on success.
    Raises HTTPException if the token is invalid, expired, or already used.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado.",
        ) from exc

    if payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de token incorrecto.",
        )

    jti = payload.get("jti")
    if jti is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token sin identificador.",
        )

    # Check single-use constraint
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.jti == jti),
    )
    reset_record = result.scalar_one_or_none()

    if reset_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado.",
        )

    if reset_record.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este token ya fue utilizado. Solicitá uno nuevo.",
        )

    return payload


async def mark_reset_token_used(
    db: AsyncSession,
    jti: str,
) -> None:
    """Mark a password-reset token as consumed so it cannot be reused."""
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.jti == jti),
    )
    reset_record = result.scalar_one_or_none()
    if reset_record is not None:
        reset_record.used = True
        await db.flush()
