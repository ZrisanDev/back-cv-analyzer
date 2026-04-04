"""SQLAlchemy models for the auth module."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """User account for CV Analyzer."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    free_analyses_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Contador de análisis gratuitos usados (máximo: FREE_ANALYSIS_LIMIT)",
    )
    paid_analyses_credits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Créditos pagos acumulados (no expiran)",
    )
    total_analyses_used: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Contador total de análisis realizados (gratis + pagos)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=_utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!s} email={self.email!r} free_analyses={self.free_analyses_count} paid_credits={self.paid_analyses_credits}>"


class TokenBlacklist(Base):
    """Stores revoked JWT tokens (both access and refresh) to support logout."""

    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        comment="JWT ID — unique token identifier embedded in the payload",
    )
    token_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Either 'access' or 'refresh'",
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Owner of the token (UUID as string)",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When this token naturally expires — used for cleanup",
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_token_blacklist_expires_at", "expires_at"),)

    def __repr__(self) -> str:
        return f"<TokenBlacklist jti={self.jti!r} type={self.token_type!r}>"


class PasswordResetToken(Base):
    """Tracks password-reset JWTs to enforce single-use and expiry."""

    __tablename__ = "password_reset_tokens"

    jti: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        comment="JWT ID of the password-reset token",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether the token has already been consumed",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the token naturally expires",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<PasswordResetToken jti={self.jti!r} user_id={self.user_id!s} used={self.used}>"
