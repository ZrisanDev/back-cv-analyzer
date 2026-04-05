"""Credit manager: add credits to users when payments are approved."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.models import CreditPackage, CreditPackageType, Payment

logger = logging.getLogger(__name__)


async def handle_approved_payment(
    db: AsyncSession,
    payment: Payment,
    mp_status_detail: str,
    mp_transaction_amount: float | None,
) -> None:
    """Handle an approved credit package payment: validate and add credits.

    Args:
        db: Async database session.
        payment: The payment record that was approved.
        mp_status_detail: The status_detail from MercadoPago.
        mp_transaction_amount: The transaction amount from MercadoPago.
    """
    # Validate status_detail is 'accredited' (money actually credited)
    if mp_status_detail != "accredited":
        logger.warning(
            "Payment approved but status_detail is '%s' (expected 'accredited')",
            mp_status_detail,
        )
        # Still proceed, but log warning

    # Validate transaction amount (anti-fraud check)
    if mp_transaction_amount is not None:
        amount_diff = abs(mp_transaction_amount - payment.amount)
        # Allow small difference due to currency conversion (within 1%)
        if amount_diff > 0.01 * payment.amount:
            logger.error(
                "PAYMENT AMOUNT MISMATCH for payment %s: expected %s, got %s (diff: %s)",
                payment.id,
                payment.amount,
                mp_transaction_amount,
                amount_diff,
            )
            # Don't proceed with credit addition if amounts don't match
            await db.flush()
            return
        else:
            logger.info(
                "Payment amount validated: %s ≈ %s (diff: %s)",
                payment.amount,
                mp_transaction_amount,
                amount_diff,
            )

    # Add credits to user
    await add_credits_to_user(db, payment.user_id, payment.package_type)
    logger.info(
        "Added credits to user %s for package %s",
        payment.user_id,
        payment.package_type.value,
    )


async def add_credits_to_user(
    db: AsyncSession,
    user_id: Any,  # uuid.UUID but we use Any to avoid import issues
    package_type: CreditPackageType,
) -> None:
    """Add credits to a user when a credit package payment is approved.

    Args:
        db: Async database session.
        user_id: UUID of the user to credit.
        package_type: Type of package that was purchased.
    """
    # Get package details to know how many credits to add
    result = await db.execute(
        select(CreditPackage).where(CreditPackage.package_type == package_type)
    )
    package = result.scalar_one_or_none()
    if package is None:
        logger.error("Credit package %s not found when adding credits", package_type)
        return

    # Add credits to user
    from app.auth.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.error("User %s not found when adding credits", user_id)
        return

    user.paid_analyses_credits += package.credits_count
    logger.info(
        "User %s: added %d credits (total now: %d)",
        user_id,
        package.credits_count,
        user.paid_analyses_credits,
    )
