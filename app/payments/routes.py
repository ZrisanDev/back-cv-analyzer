"""Payment routes: create preference, receive webhooks, query payment status."""

from __future__ import annotations

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
from app.payments.models import CreditPackage, Payment
from app.payments.schemas import (
    CreditPackageCreate,
    CreditPackageResponse,
    CreditPackageType,
    PaymentCreate,
    PaymentResponse,
    PreferenceResponse,
    UserCreditsResponse,
    WebhookPayload,
)
from app.payments.services import (
    create_credit_package_preference,
    create_preference,
    get_user_credits,
    process_webhook,
)
from app.shared.config import settings
from app.shared.database import get_db

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
    by fetching the latest status directly from MercadoPago.
    """
    try:
        payload = await request.json()
    except Exception:
        # Return 200 to avoid MercadoPago retrying with malformed data
        return {"status": "ignored", "reason": "invalid JSON body"}

    result = await process_webhook(db=db, payload=payload)
    return result


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
