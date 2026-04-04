"""Payment services: MercadoPago integration, webhook processing, free analyses."""

from __future__ import annotations

import hashlib
import hmac
import logging
import urllib.parse
from typing import Any

import mercadopago
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from app.payments.models import (
    CreditPackage,
    CreditPackageType,
    Payment,
    PaymentStatus,
)
from app.payments.schemas import (
    CreditPackageType as APICreditPackageType,
    PreferenceResponse,
    UserCreditsResponse,
)
from app.shared.config import settings

logger = logging.getLogger(__name__)

# ── MercadoPago SDK Client ────────────────────────────────────


def _get_mp_client() -> mercadopago.SDK:
    """Create a MercadoPago SDK client instance.

    Reuses access token from settings. Each call creates a new
    instance to avoid state leakage between requests.
    """
    if not settings.mercadopago_access_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MercadoPago is not configured. Set MERCADOPAGO_ACCESS_TOKEN.",
        )
    return mercadopago.SDK(settings.mercadopago_access_token)


def _verify_webhook_signature(
    x_signature: str | None,
    x_request_id: str | None,
    data_id: str | None,
) -> bool:
    """Verify MercadoPago webhook x-signature header.

    Validates that the webhook notification came from MercadoPago by
    comparing the HMAC-SHA256 signature in the x-signature header.

    Args:
        x_signature: Value from the 'x-signature' request header
        x_request_id: Value from the 'x-request-id' request header
        data_id: The 'data.id' query parameter value

    Returns:
        True if signature is valid, False otherwise

    Validation process:
    1. Parse x-signature header to extract 'ts' (timestamp) and 'v1' (hash)
    2. Build manifest string: "id:{data_id};request-id:{x_request_id};ts:{ts};"
    3. Calculate HMAC-SHA256 using the webhook secret key
    4. Compare calculated hash with v1 from x-signature

    Reference: https://www.mercadopago.com.ar/developers/es/docs/checkout-v1/webhooks/signatures
    """
    if not settings.mercadopago_webhook_secret:
        logger.warning(
            "Webhook signature verification skipped: MERCADOPAGO_WEBHOOK_SECRET not configured"
        )
        return True  # Allow webhook without verification if secret not set (dev mode)

    if not x_signature or not x_request_id or not data_id:
        logger.warning(
            "Webhook signature verification failed: missing required headers/params"
        )
        return False

    # Parse x-signature header (format: "ts=...,v1=...")
    parts = x_signature.split(",")
    ts = None
    signature_hash = None

    for part in parts:
        key_value = part.split("=", 1)
        if len(key_value) == 2:
            key = key_value[0].strip()
            value = key_value[1].strip()
            if key == "ts":
                ts = value
            elif key == "v1":
                signature_hash = value

    if not ts or not signature_hash:
        logger.warning(
            "Webhook signature verification failed: could not parse x-signature"
        )
        return False

    # Build manifest string following MercadoPago specification
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

    # Calculate HMAC-SHA256 using the webhook secret
    hmac_obj = hmac.new(
        settings.mercadopago_webhook_secret.encode(),
        msg=manifest.encode(),
        digestmod=hashlib.sha256,
    )
    calculated_hash = hmac_obj.hexdigest()

    # Compare hashes
    is_valid = hmac.compare_digest(calculated_hash, signature_hash)

    if not is_valid:
        logger.warning("Webhook signature verification failed: hash mismatch")
    else:
        logger.info("Webhook signature verified successfully")

    return is_valid


# ── User Credits ───────────────────────────────────────────────


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


# ── Free Analyses ─────────────────────────────────────────────


async def has_free_analyses_remaining(db: AsyncSession, user_id) -> bool:
    """Check whether a user still has free analyses available.

    Args:
        db: Async database session.
        user_id: UUID of the user.

    Returns:
        True if the user has used fewer analyses than the free limit.
    """
    can_analyze, _ = await has_credits_available(db, user_id)
    return can_analyze


# ── Create Preference ─────────────────────────────────────────


async def create_preference(
    db: AsyncSession,
    user_id,
    amount: float | None = None,
) -> PreferenceResponse:
    """Create a MercadoPago payment preference and persist a Payment record.

    Args:
        db: Async database session.
        user_id: UUID of the authenticated user.
        amount: Optional custom amount. Falls back to ``ANALYSIS_PRICE_USD``.

    Returns:
        PreferenceResponse with the preference ID and payment URL.

    Raises:
        HTTPException 503: If MercadoPago is not configured.
        HTTPException 502: If the MercadoPago API call fails.
    """
    effective_amount = amount or settings.analysis_price_usd

    # Build MercadoPago preference payload
    mp = _get_mp_client()

    preference_data: dict[str, Any] = {
        "items": [
            {
                "title": "Análisis de CV",
                "quantity": 1,
                "unit_price": effective_amount,
                "currency_id": "USD",
            }
        ],
        "back_urls": {
            "success": f"{settings.frontend_base_url}/payment/success",
            "failure": f"{settings.frontend_base_url}/payment/failure",
            "pending": f"{settings.frontend_base_url}/payment/pending",
        },
        "auto_return": "approved",
        "external_reference": str(user_id),
        "binary_mode": True,  # Solo rechaza si falla la autenticación
    }

    logger.info(
        "Creating MercadoPago preference with base_url: %s",
        settings.frontend_base_url,
    )
    logger.info(
        "Back URLs: %s",
        preference_data.get("back_urls"),
    )

    try:
        mp_response = mp.preference().create(preference_data)
    except Exception as exc:
        logger.exception("MercadoPago API error while creating preference")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create payment preference: {exc}",
        ) from exc

    if mp_response.get("status") < 200 or mp_response.get("status") >= 300:
        logger.error(
            "MercadoPago returned error: %s — %s",
            mp_response.get("status"),
            mp_response.get("response"),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MercadoPago returned an error creating the preference.",
        )

    mp_data = mp_response.get("response", {})
    preference_id = mp_data.get("id")
    init_point = mp_data.get("init_point", "")

    if not preference_id or not init_point:
        logger.error("MercadoPago response missing id or init_point: %s", mp_data)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from MercadoPago.",
        )

    # Persist payment record
    payment = Payment(
        user_id=user_id,
        amount=effective_amount,
        currency="USD",
        status=PaymentStatus.PENDING,
        mercadopago_preference_id=str(preference_id),
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)

    return PreferenceResponse(
        preference_id=str(preference_id),
        payment_url=init_point,
        amount=effective_amount,
        currency="USD",
        package_type=None,
    )


# ── Create Credit Package Preference ─────────────────────────────


async def create_credit_package_preference(
    db: AsyncSession,
    user_id: uuid.UUID,
    package_type: CreditPackageType,
) -> PreferenceResponse:
    """Create a MercadoPago payment preference for a credit package.

    Args:
        db: Async database session.
        user_id: UUID of the authenticated user.
        package_type: Type of credit package to purchase.

    Returns:
        PreferenceResponse with preference ID and payment URL.

    Raises:
        HTTPException 404: If package type is not found.
        HTTPException 503: If MercadoPago is not configured.
        HTTPException 502: If the MercadoPago API call fails.
    """
    # Get package details
    result = await db.execute(
        select(CreditPackage).where(
            CreditPackage.package_type == package_type,
            CreditPackage.is_active == True,
        )
    )
    package = result.scalar_one_or_none()

    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credit package '{package_type.value}' not found or inactive.",
        )

    # Build MercadoPago preference payload
    mp = _get_mp_client()

    # Map package type to readable title
    title_map = {
        CreditPackageType.pack_20: "Pack 20 Análisis de CV",
        CreditPackageType.pack_50: "Pack 50 Análisis de CV",
        CreditPackageType.pack_100: "Pack 100 Análisis de CV",
    }

    preference_data: dict[str, Any] = {
        "items": [
            {
                "title": title_map.get(
                    package_type, f"{package_type.value} Análisis de CV"
                ),
                "quantity": 1,
                "unit_price": package.price_usd,
                "currency_id": "USD",
            }
        ],
        "back_urls": {
            "success": f"{settings.frontend_base_url}/payment/success",
            "failure": f"{settings.frontend_base_url}/payment/failure",
            "pending": f"{settings.frontend_base_url}/payment/pending",
        },
        "auto_return": "approved",
        "external_reference": str(user_id),
        "binary_mode": True,  # Solo rechaza si falla la autenticación
    }

    logger.info(
        "Creating MercadoPago preference with base_url: %s",
        settings.frontend_base_url,
    )
    logger.info(
        "Back URLs: %s",
        preference_data.get("back_urls"),
    )

    try:
        mp_response = mp.preference().create(preference_data)
    except Exception as exc:
        logger.exception("MercadoPago API error while creating package preference")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create payment preference: {exc}",
        ) from exc

    if mp_response.get("status") < 200 or mp_response.get("status") >= 300:
        logger.error(
            "MercadoPago returned error: %s — %s",
            mp_response.get("status"),
            mp_response.get("response"),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MercadoPago returned an error creating the preference.",
        )

    mp_data = mp_response.get("response", {})
    preference_id = mp_data.get("id")
    init_point = mp_data.get("init_point", "")

    if not preference_id or not init_point:
        logger.error("MercadoPago response missing id or init_point: %s", mp_data)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from MercadoPago.",
        )

    # Persist payment record
    payment = Payment(
        user_id=user_id,
        amount=package.price_usd,
        currency="USD",
        status=PaymentStatus.PENDING,
        mercadopago_preference_id=str(preference_id),
        package_type=package_type,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)

    return PreferenceResponse(
        preference_id=str(preference_id),
        payment_url=init_point,
        amount=package.price_usd,
        currency="USD",
        package_type=APICreditPackageType(package_type.value),
    )


# ── Webhook Processing ────────────────────────────────────────


async def process_webhook(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Process an incoming MercadoPago webhook notification.

    This endpoint is **idempotent**: receiving the same notification
    multiple times is safe. We fetch the latest payment status from
    MercadoPago and only update if the status has changed.

    Args:
        db: Async database session.
        payload: Raw JSON body from the webhook POST.

    Returns:
        A confirmation dict.

    Raises:
        HTTPException 200: Always returns 200 to MercadoPago to acknowledge receipt.
    """
    action = payload.get("action")
    data = payload.get("data", {})
    mp_payment_id = data.get("id") if isinstance(data, dict) else None

    if not mp_payment_id:
        logger.warning("Webhook received with no payment ID: %s", payload)
        return {"status": "ignored", "reason": "no payment ID in payload"}

    mp_payment_id_str = str(mp_payment_id)

    # Find existing payment record by mercadopago_payment_id
    result = await db.execute(
        select(Payment).where(Payment.mercadopago_payment_id == mp_payment_id_str)
    )
    payment = result.scalar_one_or_none()

    if payment is None:
        logger.warning(
            "Webhook for unknown payment %s — no matching record",
            mp_payment_id_str,
        )
        return {"status": "ignored", "reason": "payment not found"}

    # Fetch latest payment info from MercadoPago for idempotency
    await _sync_payment_status_from_mp(db, payment, mp_payment_id_str)

    return {"status": "processed", "payment_id": mp_payment_id_str}


async def _sync_payment_status_from_mp(
    db: AsyncSession,
    payment: Payment,
    mp_payment_id: str,
) -> None:
    """Fetch the latest status from MercadoPago and update our record.

    This is the idempotency mechanism: we always go to the source of truth
    (MercadoPago) rather than trusting the webhook body.
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
        payment.status = new_status

        # If payment was just approved, store the MP payment ID
        if new_status == PaymentStatus.APPROVED and not payment.mercadopago_payment_id:
            payment.mercadopago_payment_id = mp_payment_id

        # If this is a credit package payment and was just approved, add credits to user
        if (
            new_status == PaymentStatus.APPROVED
            and payment.package_type
            and payment.status != PaymentStatus.APPROVED
        ):
            await _add_credits_to_user(db, payment.user_id, payment.package_type)
            logger.info(
                "Added credits to user %s for package %s",
                payment.user_id,
                payment.package_type.value,
            )

        await db.flush()


# ── Add Credits to User ────────────────────────────────────────


async def _add_credits_to_user(
    db: AsyncSession,
    user_id: uuid.UUID,
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


# ── Update Payment Status ─────────────────────────────────────


async def update_payment_status(
    db: AsyncSession,
    payment_id,
    new_status: PaymentStatus,
) -> Payment:
    """Manually update the status of a payment record.

    Args:
        db: Async database session.
        payment_id: UUID of the payment to update.
        new_status: The new PaymentStatus to set.

    Returns:
        The updated Payment ORM object.

    Raises:
        HTTPException 404: If the payment does not exist.
    """
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    payment.status = new_status
    await db.flush()
    await db.refresh(payment)

    return payment
