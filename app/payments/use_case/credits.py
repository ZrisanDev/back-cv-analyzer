"""User credit operations: query, check availability, and consume credits."""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.schemas import UserCreditsResponse
from app.shared.config import settings

logger = logging.getLogger(__name__)


async def get_user_credits(db: AsyncSession, user_id: uuid.UUID) -> UserCreditsResponse:
    """Get the user's current credits and usage statistics.

    Args:
        db: Async database session.
        user_id: UUID of the user.

    Returns:
        UserCreditsResponse with free and paid credits information.
    """
    from app.auth.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    free_remaining = max(0, settings.free_analysis_limit - user.free_analyses_count)

    return UserCreditsResponse(
        free_analyses_count=user.free_analyses_count,
        free_analyses_limit=settings.free_analysis_limit,
        free_analyses_remaining=free_remaining,
        paid_analyses_credits=user.paid_analyses_credits,
        total_analyses_used=user.total_analyses_used,
    )


async def has_credits_available(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[bool, str]:
    """Check whether a user can perform an analysis.

    Args:
        db: Async database session.
        user_id: UUID of the user.

    Returns:
        Tuple of (can_analyze, reason):
        - (True, "") → User can analyze
        - (False, "no_free") → No free analyses remaining
        - (False, "no_credits") → No paid credits remaining
    """
    from app.auth.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return (False, "user_not_found")

    # Check free analyses first
    if user.free_analyses_count < settings.free_analysis_limit:
        return (True, "")

    # Then check paid credits
    if user.paid_analyses_credits > 0:
        return (True, "")

    return (False, "no_credits")


async def consume_credit(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Consume one credit from the user's account.

    Prioritizes free analyses, then paid credits.

    Args:
        db: Async database session.
        user_id: UUID of the user.

    Raises:
        HTTPException 402: If user has no credits available.
    """
    from app.auth.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    # Check if user has any credits available
    can_analyze, reason = await has_credits_available(db, user_id)
    if not can_analyze:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No credits available. Please purchase a credit package.",
            headers={"X-Needs-Payment": "true"},
        )

    # Consume free analysis first
    if user.free_analyses_count < settings.free_analysis_limit:
        user.free_analyses_count += 1
    else:
        # Consume paid credit
        user.paid_analyses_credits -= 1

    user.total_analyses_used += 1
