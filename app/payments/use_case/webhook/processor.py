"""Webhook processor: main orchestrator for MercadoPago webhook notifications."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.use_case.webhook.credit_manager import handle_approved_payment
from app.payments.use_case.webhook.payment_finder import find_payment_by_webhook_data
from app.payments.use_case.webhook.status_syncer import sync_payment_status_from_mp

logger = logging.getLogger(__name__)


async def process_webhook(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Process an incoming MercadoPago webhook notification.

    This endpoint is **idempotent**: receiving of same notification
    multiple times is safe. We fetch the latest payment status from
    MercadoPago and only update if the status has changed.

    Args:
        db: Async database session.
        payload: Raw JSON body from webhook POST.

    Returns:
        A confirmation dict.

    Raises:
        HTTPException 200: Always returns 200 to MercadoPago to acknowledge receipt.

    NOTE: Handles different webhook types:
    - payment: Payment created/updated
    - merchant_order: Order created/updated (ignored for now)
    """
    notification_type = payload.get("type") or payload.get("topic")

    # Only process payment webhooks, ignore merchant_order for now
    if notification_type != "payment":
        logger.info(
            "Ignoring webhook type '%s' (only processing 'payment' webhooks)",
            notification_type,
        )
        return {
            "status": "ignored",
            "reason": f"unsupported_type_{notification_type}",
        }

    action = payload.get("action")
    data = payload.get("data", {})
    mp_payment_id = data.get("id") if isinstance(data, dict) else None

    # MercadoPago webhooks can come in two formats:
    # 1. body with "data.id" (handled above)
    # 2. body with "resource" (legacy format)
    if not mp_payment_id:
        mp_payment_id = payload.get("resource")

    if not mp_payment_id:
        logger.warning("Webhook received with no payment ID: %s", payload)
        return {"status": "ignored", "reason": "no payment ID in payload"}

    mp_payment_id_str = str(mp_payment_id)

    # Find payment record using the MP payment_id from webhook
    payment, preference_id, external_reference = await find_payment_by_webhook_data(
        db, mp_payment_id_str
    )

    if payment is None:
        logger.warning(
            "Webhook for unknown payment %s — no matching record",
            mp_payment_id_str,
        )
        return {"status": "ignored", "reason": "payment not found"}

    # Fetch latest payment info from MercadoPago for idempotency
    await sync_payment_status_from_mp(db, payment, mp_payment_id_str)

    return {"status": "processed", "payment_id": mp_payment_id_str}
