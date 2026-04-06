"""Payment finder: locate payment records and fetch preference_id from MercadoPago."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.models import Payment
from app.payments.use_case.client import _get_mp_client

logger = logging.getLogger(__name__)


async def find_payment_by_webhook_data(
    db: AsyncSession,
    mp_payment_id: str,
) -> tuple[Payment | None, str | None, str | None]:
    """Find a payment record using the MP payment_id from a webhook.

    This function implements a robust multi-strategy lookup:
    1. Try to find by mercadopago_payment_id first (fastest, direct match)
    2. If not found, fetch payment details from Mercado Pago to get preference_id
    3. Try to find by preference_id (most common after step 2)
    4. If still not found, try by external_reference (fallback for edge cases)

    Args:
        db: Async database session.
        mp_payment_id: The MercadoPago payment ID from the webhook.

    Returns:
        A tuple of (payment_record, preference_id_from_mp, external_reference_from_mp).
        All can be None if the payment is not found or MP fetch fails.
    """
    # Strategy 1: First try to find by mercadopago_payment_id (fastest direct lookup)
    result = await db.execute(
        select(Payment).where(Payment.mercadopago_payment_id == mp_payment_id)
    )
    payment = result.scalar_one_or_none()

    if payment:
        return payment, payment.mercadopago_preference_id, payment.external_reference

    # Strategy 2: Fetch payment details from Mercado Pago to get preference_id and external_reference
    preference_id = await _fetch_preference_id_from_mp(mp_payment_id)
    external_reference = await _fetch_external_reference_from_mp(mp_payment_id)

    # Strategy 3: Try to find by preference_id
    if preference_id:
        result = await db.execute(
            select(Payment).where(Payment.mercadopago_preference_id == preference_id)
        )
        payment = result.scalar_one_or_none()

        if payment:
            # Update the payment_id if it's not set (for faster future lookups)
            if not payment.mercadopago_payment_id:
                payment.mercadopago_payment_id = mp_payment_id
                await db.flush()

            # Update external_reference if it's not set
            if not payment.external_reference and external_reference:
                payment.external_reference = external_reference
                await db.flush()

            return payment, preference_id, external_reference

    # Strategy 4: Try to find by external_reference (fallback)
    if external_reference:
        result = await db.execute(
            select(Payment).where(Payment.external_reference == external_reference)
        )
        payments = result.scalars().all()

        if payments:
            # If multiple payments found, pick the most recent one without mercadopago_payment_id
            # This handles the case where a user created multiple pending payments
            payment = (
                sorted(
                    [p for p in payments if not p.mercadopago_payment_id],
                    key=lambda x: x.created_at if hasattr(x, "created_at") else None,
                    reverse=True,
                )[0]
                if any(not p.mercadopago_payment_id for p in payments)
                else None
            )

            if payment:
                # Update the payment_id if it's not set (for faster future lookups)
                if not payment.mercadopago_payment_id:
                    payment.mercadopago_payment_id = mp_payment_id
                    await db.flush()

                return payment, preference_id, external_reference

    # Payment not found
    logger.warning(
        "Payment not found for MP payment_id: %s (preference_id=%s, external_reference=%s)",
        mp_payment_id,
        preference_id,
        external_reference,
    )

    return None, preference_id, external_reference


async def _fetch_preference_id_from_mp(mp_payment_id: str) -> str | None:
    """Fetch the preference_id from MercadoPago for a given payment_id.

    Args:
        mp_payment_id: The MercadoPago payment ID.

    Returns:
        The preference_id if found, None otherwise.
    """
    mp = _get_mp_client()

    try:
        logger.info("🔍 Fetching payment %s from MercadoPago...", mp_payment_id)
        mp_response = mp.payment().get(mp_payment_id)

        if mp_response.get("status") >= 200 and mp_response.get("status") < 300:
            mp_data = mp_response.get("response", {})
            preference_id = mp_data.get("preference_id")
            logger.info(
                "✅ Fetched payment from MP: payment_id=%s, preference_id=%s",
                mp_payment_id,
                preference_id or "NOT_FOUND",
            )
            return preference_id
        else:
            logger.warning(
                "⚠️  Failed to fetch payment from MP: status=%s, response=%s",
                mp_response.get("status"),
                mp_response.get("response"),
            )
    except Exception as exc:
        logger.warning("❌ Failed to fetch payment %s from MP: %s", mp_payment_id, exc)

    return None


async def _fetch_external_reference_from_mp(mp_payment_id: str) -> str | None:
    """Fetch the external_reference from MercadoPago for a given payment_id.

    The external_reference is the user_id we set when creating a preference.

    Args:
        mp_payment_id: The MercadoPago payment ID.

    Returns:
        The external_reference if found, None otherwise.
    """
    mp = _get_mp_client()

    try:
        logger.info("🔍 Fetching external_reference for payment %s...", mp_payment_id)
        mp_response = mp.payment().get(mp_payment_id)

        if mp_response.get("status") >= 200 and mp_response.get("status") < 300:
            mp_data = mp_response.get("response", {})
            external_reference = mp_data.get("external_reference")
            logger.info(
                "✅ Fetched external_reference from MP: payment_id=%s, external_reference=%s",
                mp_payment_id,
                external_reference or "NOT_FOUND",
            )
            return external_reference
        else:
            logger.warning(
                "⚠️  Failed to fetch payment from MP: status=%s, response=%s",
                mp_response.get("status"),
                mp_response.get("response"),
            )
    except Exception as exc:
        logger.warning("❌ Failed to fetch payment %s from MP: %s", mp_payment_id, exc)

    return None
