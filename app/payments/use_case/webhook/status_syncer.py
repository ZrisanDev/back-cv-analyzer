"""Status syncer: synchronize payment status from MercadoPago."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.models import Payment, PaymentStatus
from app.payments.use_case.client import _get_mp_client

logger = logging.getLogger(__name__)


async def sync_payment_status_from_mp(
    db: AsyncSession,
    payment: Payment,
    mp_payment_id: str,
) -> None:
    """Fetch the latest status from MercadoPago and update our record.

    This is the idempotency mechanism: we always go to the source of truth
    (MercadoPago) rather than trusting the webhook body.

    Args:
        db: Async database session.
        payment: The payment record to update.
        mp_payment_id: The MercadoPago payment ID.

    Raises:
        HTTPException 502: If failed to fetch payment from MercadoPago.
    """
    mp = _get_mp_client()

    try:
        mp_response = mp.payment().get(mp_payment_id)
    except Exception as exc:
        logger.exception("Failed to fetch payment %s from MercadoPago", mp_payment_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to verify payment with MercadoPago: {exc}",
        ) from exc

    if mp_response.get("status") < 200 or mp_response.get("status") >= 300:
        logger.error(
            "MercadoPago payment lookup error: %s — %s",
            mp_response.get("status"),
            mp_response.get("response"),
        )
        return

    mp_data = mp_response.get("response", {})
    mp_status = mp_data.get("status")
    mp_status_detail = mp_data.get("status_detail")
    mp_transaction_amount = mp_data.get("transaction_amount")
    mp_external_reference = mp_data.get("external_reference")
    mp_date_approved = mp_data.get("date_approved")
    mp_payment_method = mp_data.get("payment_method_id")

    # Map MercadoPago statuses to our enum
    status_mapping = {
        "approved": PaymentStatus.APPROVED,
        "pending": PaymentStatus.PENDING,
        "rejected": PaymentStatus.REJECTED,
        "refunded": PaymentStatus.REFUNDED,
        "in_process": PaymentStatus.IN_PROCESS,
        "in_mediation": PaymentStatus.IN_PROCESS,
        "cancelled": PaymentStatus.REJECTED,
    }

    new_status = status_mapping.get(mp_status)
    if new_status is None:
        logger.warning(
            "Unknown MercadoPago status '%s' for payment %s", mp_status, mp_payment_id
        )
        return

    # Only update if the status has changed (idempotency)
    if payment.status != new_status:
        logger.info(
            "Payment %s status changed: %s → %s",
            payment.id,
            payment.status.value,
            new_status.value,
        )
        old_status = payment.status
        payment.status = new_status

        # Update additional payment details
        payment.status_detail = mp_status_detail
        payment.payment_method_id = mp_payment_method

        # Parse payer information if available
        payer_data = mp_data.get("payer", {})
        if isinstance(payer_data, dict):
            payment.payer_email = payer_data.get("email")

        # If payment was just approved, store the MP payment ID
        if new_status == PaymentStatus.APPROVED and not payment.mercadopago_payment_id:
            payment.mercadopago_payment_id = mp_payment_id

        # Parse and store date_approved if available
        if mp_date_approved:
            try:
                # Parse ISO 8601 date string
                if isinstance(mp_date_approved, str):
                    payment.date_approved = datetime.fromisoformat(
                        mp_date_approved.replace("Z", "+00:00")
                    )
            except Exception as exc:
                logger.warning("Failed to parse date_approved: %s", exc)

        # Store external_reference if not already set
        if mp_external_reference and not payment.external_reference:
            payment.external_reference = mp_external_reference
            logger.info(
                "Stored external_reference for payment %s: %s",
                payment.id,
                mp_external_reference,
            )

        # If this is a credit package payment and was just approved, handle it
        if (
            new_status == PaymentStatus.APPROVED
            and payment.package_type
            and old_status != PaymentStatus.APPROVED
        ):
            # Import here to avoid circular dependency
            from app.payments.use_case.webhook.credit_manager import (
                handle_approved_payment,
            )

            await handle_approved_payment(
                db=db,
                payment=payment,
                mp_status_detail=mp_status_detail,
                mp_transaction_amount=mp_transaction_amount,
            )

        await db.flush()
    else:
        logger.info(
            "Payment %s status unchanged: %s (no update needed)",
            payment.id,
            payment.status.value,
        )
