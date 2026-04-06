"""Payment routes: create preference, receive webhooks, query payment status."""

from __future__ import annotations

import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.payments.models import CreditPackage, Payment, PaymentStatus
from app.payments.schemas import (
    CreditPackageCreate,
    CreditPackageResponse,
    PaymentCreate,
    PaymentResponse,
    PreferenceResponse,
    UserCreditsResponse,
)
from app.payments.services import (
    _verify_webhook_signature,
    create_credit_package_preference,
    create_preference,
    get_user_credits,
    process_webhook,
)
from app.shared.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


# ── Get available credit packages ──────────────────────────────


@router.get(
    "/credit-packages",
    response_model=list[CreditPackageResponse],
    summary="Get available credit packages",
)
async def get_credit_packages(
    db: AsyncSession = Depends(get_db),
) -> list[CreditPackage]:
    """Return all active credit packages available for purchase."""
    result = await db.execute(
        select(CreditPackage).where(CreditPackage.is_active == True)
    )
    packages = result.scalars().all()
    return packages


# ── Get user credits ───────────────────────────────────────────


@router.get(
    "/my-credits",
    response_model=UserCreditsResponse,
    summary="Get current user's credits and usage",
)
async def get_my_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserCreditsResponse:
    """Return the authenticated user's available credits and usage statistics."""
    return await get_user_credits(db, current_user.id)


# ── Create credit package payment preference ────────────────────


@router.post(
    "/create-package-preference",
    response_model=PreferenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a MercadoPago preference for a credit package",
)
async def create_payment_package_preference(
    body: CreditPackageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PreferenceResponse:
    """Create a MercadoPago checkout preference for a credit package.

    The user will be redirected to MercadoPago to complete the payment.
    Once approved, the credits will be added to their account.
    """
    return await create_credit_package_preference(
        db=db,
        user_id=current_user.id,
        package_type=body.package_type,
    )


# ── Create payment preference (LEGACY) ─────────────────────────────


@router.post(
    "/create-preference",
    response_model=PreferenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a MercadoPago payment preference (LEGACY)",
    deprecated=True,
)
async def create_payment_preference(
    body: PaymentCreate = PaymentCreate(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PreferenceResponse:
    """Create a MercadoPago checkout preference for the authenticated user.

    **DEPRECATED**: Use /create-package-preference for credit packages.

    Returns a payment URL that the user can follow to complete the payment.
    """
    return await create_preference(
        db=db,
        user_id=current_user.id,
        amount=body.amount,
    )


# ── Webhook (PUBLIC — no auth) ────────────────────────────────


@router.post(
    "/webhook",
    summary="MercadoPago webhook endpoint (public)",
    status_code=status.HTTP_200_OK,
)
async def mercadopago_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive webhook notifications from MercadoPago.

    **This endpoint is PUBLIC** — no authentication required.
    MercadoPago sends POST requests here when payment events occur.

    The endpoint is **idempotent**: duplicate notifications are handled safely
    by fetching latest status directly from MercadoPago.

    **Security**: Validates x-signature header to ensure notifications
    come from MercadoPago. Configure MERCADOPAGO_WEBHOOK_SECRET in .env

    **IMPORTANT**: Always returns HTTP 200 to prevent MercadoPago retries.
    Even if processing fails, we return 200 to avoid infinite retry loops.

    **NOTE**: Supports both query param formats:
    - data.id={id} (new MercadoPago format)
    - id={id} (old MercadoPago format)
    """
    # Extract headers for signature verification
    x_signature = request.headers.get("x-signature")
    x_request_id = request.headers.get("x-request-id")

    # Extract query params for signature verification
    # Support both formats: data.id and id
    query_params = request.query_params
    data_id = query_params.get("data.id") or query_params.get("id")
    topic = query_params.get("topic") or query_params.get("type")

    # Verify webhook signature
    if not _verify_webhook_signature(x_signature, x_request_id, data_id):
        logger.warning(
            "Received webhook with INVALID SIGNATURE. data_id=%s, x-request-id=%s",
            data_id,
            x_request_id,
        )
        # IMPORTANT: Still return 200 to avoid retries from MercadoPago
        # If we return 401, MercadoPago will keep retrying
        return {
            "status": "rejected",
            "reason": "invalid_signature",
            "received": True,
        }

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("Webhook error parsing JSON: %s", exc)
        # Return 200 with ignored status to avoid Mercado Pago retries
        return {"status": "ignored", "reason": "json_parse_error", "received": True}

    # Only process payment webhooks, ignore merchant_order and others
    notification_type = payload.get("type") or payload.get("topic")
    if notification_type != "payment":
        logger.info(
            "Ignoring webhook type '%s' (only processing 'payment' webhooks)",
            notification_type,
        )
        return {
            "status": "ignored",
            "reason": f"unsupported_type_{notification_type}",
            "received": True,
        }

    # Process webhook
    try:
        result = await process_webhook(db=db, payload=payload)
        return {"status": "processed", "received": True, **result}
    except Exception as exc:
        logger.exception("Webhook processing error: %s", exc)
        # IMPORTANT: Always return 200 to avoid MercadoPago retries
        # The webhook will be retried by MP on its own schedule if needed
        return {
            "status": "error",
            "reason": str(exc),
            "received": True,
        }

    # Process webhook
    try:
        result = await process_webhook(db=db, payload=payload)
        return {"status": "processed", "received": True, **result}
    except Exception as exc:
        logger.exception("Webhook processing error: %s", exc)
        # IMPORTANT: Always return 200 to avoid MercadoPago retries
        # The webhook will be retried by MP on its own schedule if needed
        return {
            "status": "error",
            "reason": str(exc),
            "received": True,
        }


# ── Get payment status by MercadoPago payment ID (PUBLIC) ────────────


@router.get(
    "/status",
    summary="Get payment status by MercadoPago payment ID (public)",
)
async def get_payment_status(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the current status of a payment by its MercadoPago payment ID.

    This endpoint is PUBLIC — no authentication required.
    Used by the frontend to verify payment status after MercadoPago redirect.

    This endpoint accepts EITHER a MercadoPago payment_id OR a preference_id.
    It searches for both and returns the payment if found.

    Args:
        payment_id: Either the MercadoPago payment ID OR the preference ID (from query params)

    Returns:
        Dict with payment details in the format expected by the frontend.
    """
    # Try to find payment by mercadopago_payment_id first
    result = await db.execute(
        select(Payment).where(Payment.mercadopago_payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()

    # If not found, try by preference_id (for legacy support)
    if not payment:
        result = await db.execute(
            select(Payment).where(Payment.mercadopago_preference_id == payment_id)
        )
        payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    # Si tenemos preference_id pero no payment_id, consultar a Mercado Pago directamente
    if payment.mercadopago_preference_id and not payment.mercadopago_payment_id:
        try:
            from app.payments.use_case.client import _get_mp_client
            from app.payments.use_case.webhook.status_syncer import (
                sync_payment_status_from_mp,
            )

            mp = _get_mp_client()
            # Buscar pagos por preference_id
            mp_response = mp.payment().search(
                {"preference_id": payment.mercadopago_preference_id}
            )

            if mp_response and mp_response.get("results"):
                payments_list = mp_response["results"]
                if payments_list and len(payments_list) > 0:
                    latest_payment = payments_list[0]

                    # Actualizar el payment en DB con el payment_id de Mercado Pago
                    payment.mercadopago_payment_id = str(latest_payment["id"])

                    # Actualizar status
                    if latest_payment.get("status") == "approved":
                        payment.status = PaymentStatus.APPROVED
                    elif latest_payment.get("status") == "rejected":
                        payment.status = PaymentStatus.REJECTED
                    elif latest_payment.get("status") == "in_process":
                        payment.status = PaymentStatus.IN_PROCESS
                    elif latest_payment.get("status") == "pending":
                        payment.status = PaymentStatus.PENDING

                    await db.commit()
        except Exception as exc:
            logger.warning("Error consultando Mercado Pago API: %s", exc)

    # Sync status from MercadoPago for accuracy
    if payment.mercadopago_payment_id:
        try:
            from app.payments.services import _sync_payment_status_from_mp

            await _sync_payment_status_from_mp(
                db, payment, payment.mercadopago_payment_id
            )
        except Exception as exc:
            logger.warning(
                "Failed to sync payment %s from MercadoPago: %s",
                payment_id,
                exc,
            )

    # Return in the format expected by the frontend
    response_dict = {
        "paymentId": payment.mercadopago_preference_id
        or payment.mercadopago_payment_id,
        "status": payment.status.value if payment.status else "pending",
        "amount": float(payment.amount) if payment.amount else 0.0,
        "currency": str(payment.currency) if payment.currency else "PEN",
        "dateApproved": None,  # Could be added from Mercado Pago response
        "payerEmail": None,  # Could be added from Mercado Pago response
    }

    return response_dict


# ── Get payment by ID ─────────────────────────────────────────


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details by ID",
)
async def get_payment(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Payment:
    """Return the payment details for a payment owned by the authenticated user."""
    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.user_id == current_user.id,
        ),
    )
    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found or you do not have permission to view it.",
        )

    return payment
