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

    The webhook payload only contains the MP payment_id, not the preference_id.
    We need to:
    1. Fetch the payment details from MercadoPago to get the preference_id
    2. Search our DB by preference_id first (most common case)
    3. Fallback to search by mercadopago_payment_id if needed

    Args:
        db: Async database session.
        mp_payment_id: The MercadoPago payment ID from the webhook.

    Returns:
        A tuple of (payment_record, preference_id_from_mp, external_reference_from_mp).
        All can be None if the payment is not found or MP fetch fails.
    """
    # Step 1: Fetch payment details from MercadoPago to get preference_id
    preference_id = await _fetch_preference_id_from_mp(mp_payment_id)
    external_reference = await _fetch_external_reference_from_mp(mp_payment_id)

    # Step 2: Try to find payment by preference_id first
    payment = None

    if preference_id:
        result = await db.execute(
            select(Payment).where(Payment.mercadopago_preference_id == preference_id)
        )
        payment = result.scalar_one_or_none()
        if payment:
            logger.info(
                "Found payment by preference_id: %s (preference_id=%s, payment_id=%s)",
                payment.id,
                preference_id,
                payment.mercadopago_payment_id or "NOT_SET",
            )

    # If not found by preference_id, try by external_reference
    if not payment and external_reference:
        # First check if mercadopago_payment_id already exists (deduplication)
        existing_payment_with_mp_id = await db.execute(
            select(Payment).where(Payment.mercadopago_payment_id == mp_payment_id)
        )
        existing_payment = existing_payment_with_mp_id.scalar_one_or_none()

        if existing_payment:
            # This payment_id was already processed and linked to a payment
            logger.info(
                "Payment %s already linked to payment %s (skipping duplicate webhook)",
                mp_payment_id,
                existing_payment.id,
            )
            payment = existing_payment
        else:
            # Try to find payment by external_reference
            result = await db.execute(
                select(Payment).where(Payment.user_id == external_reference)
            )
            payments = result.scalars().all()
            # If multiple payments, find most recent one without mercadopago_payment_id
            if payments:
                # Sort by created_at descending and take first one without mercadopago_payment_id
                payment = sorted(
                    [p for p in payments if not p.mercadopago_payment_id],
                    key=lambda x: x.created_at if hasattr(x, 'created_at') else None,
                    reverse=True
                )[0] if any(not p.mercadopago_payment_id for p in payments) else None
                if payment:
                    logger.info(
                        "Found payment by external_reference: %s (external_reference=%s, payment_id=%s)",
                        payment.id,
                        external_reference,
                        payment.mercadopago_payment_id or "NOT_SET",
                    )

    if payment:
        logger.info(
            "Found payment by preference_id: %s (preference_id=%s, payment_id=%s)",
            payment.id,
            preference_id,
            payment.mercadopago_payment_id or "NOT_SET",
        )
        # Update the payment_id if it's not set (for faster future lookups)
        if not payment.mercadopago_payment_id:
            payment.mercadopago_payment_id = mp_payment_id
            await db.flush()
            logger.info(
                "Updated payment %s with MP payment_id: %s",
                payment.id,
                mp_payment_id,
            )
    else:
        # Fallback: try to find by mercadopago_payment_id
        result = await db.execute(
            select(Payment).where(Payment.mercadopago_payment_id == mp_payment_id)
        )
        payment = result.scalar_one_or_none()
        logger.warning(
            "Payment not found by preference_id %s - trying by mercadopago_payment_id",
            preference_id,
        )
        # Fallback: try to find by mercadopago_payment_id
        result = await db.execute(
            select(Payment).where(Payment.mercadopago_payment_id == mp_payment_id)
        )
        payment = result.scalar_one_or_none()

    return payment, preference_id, external_reference


async def _fetch_preference_id_from_mp(mp_payment_id: str) -> str | None:
    """Fetch the preference_id from MercadoPago for a given payment_id.

    Args:
        mp_payment_id: The MercadoPago payment ID.

    Returns:
        The preference_id if found, None otherwise.
    """
    mp = _get_mp_client()

    try:
        logger.info("Fetching payment %s from MercadoPago...", mp_payment_id)
        mp_response = mp.payment().get(mp_payment_id)
        logger.warning("MercadoPago raw response: %s", mp_response)

        if mp_response.get("status") >= 200 and mp_response.get("status") < 300:
            mp_data = mp_response.get("response", {})
            preference_id = mp_data.get("preference_id")
            logger.info(
                "Fetched payment from MP: payment_id=%s, preference_id=%s",
                mp_payment_id,
                preference_id or "NOT_FOUND",
            )
            logger.warning("MercadoPago response data: %s", mp_data)
            return preference_id
        else:
            logger.warning(
                "Failed to fetch payment from MP: status=%s, response=%s",
                mp_response.get("status"),
                mp_response.get("response"),
            )
    except Exception as exc:
        logger.warning("Failed to fetch payment %s from MP: %s", mp_payment_id, exc)

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
        logger.info("Fetching external_reference for payment %s...", mp_payment_id)
        mp_response = mp.payment().get(mp_payment_id)
        if mp_response.get("status") >= 200 and mp_response.get("status") < 300:
            mp_data = mp_response.get("response", {})
            external_reference = mp_data.get("external_reference")
            logger.info(
                "Fetched external_reference from MP: payment_id=%s, external_reference=%s",
                mp_payment_id,
                external_reference or "NOT_FOUND",
            )
            return external_reference
        else:
            logger.warning(
                "Failed to fetch payment from MP: status=%s, response=%s",
                mp_response.get("status"),
                mp_response.get("response"),
            )
    except Exception as exc:
        logger.warning("Failed to fetch payment %s from MP: %s", mp_payment_id, exc)

    return None
