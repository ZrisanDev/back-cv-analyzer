"""Pydantic schemas for the payments module."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums exposed to the API ────────────────────────────────


class Status(str):
    """Mirror of the DB enum so the API layer never imports SQLAlchemy."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    IN_PROCESS = "in_process"


class CreditPackageType(str, Enum):
    """Credit package types available for purchase."""

    pack_20 = "pack_20"
    pack_50 = "pack_50"
    pack_100 = "pack_100"


# ── Request schemas ───────────────────────────────────────────


class CreditPackageCreate(BaseModel):
    """Body payload when creating a payment preference for a credit package."""

    package_type: CreditPackageType = Field(
        ...,
        description="Type of credit package to purchase",
    )


class PaymentCreate(BaseModel):
    """Body payload when creating a payment preference (LEGACY - use CreditPackageCreate)."""

    amount: float | None = Field(
        None,
        description="Custom amount. If omitted, uses the default ANALYSIS_PRICE_USD.",
        gt=0,
    )


class WebhookPayload(BaseModel):
    """Payload received from MercadoPago webhook notifications.

    MercadoPago sends different action types. We care about:
    - ``payment``: a payment was created/updated
    """

    action: str | None = Field(None, description="Webhook action type")
    type: str | None = Field(None, description="Event type (e.g. 'payment')")
    data: WebhookPayloadData | None = Field(None, description="Event data")


class WebhookPayloadData(BaseModel):
    """Nested data object from MercadoPago webhook."""

    id: str | None = Field(None, description="MercadoPago payment ID")


# ── Response schemas ──────────────────────────────────────────


class PreferenceResponse(BaseModel):
    """Returned after creating a MercadoPago preference."""

    preference_id: str
    payment_url: str
    amount: float
    currency: str = "USD"
    package_type: CreditPackageType | None = None


class PaymentResponse(BaseModel):
    """Full payment details returned to the client."""

    id: uuid.UUID
    user_id: uuid.UUID
    analysis_id: uuid.UUID | None = None
    amount: float
    currency: str
    status: str
    mercadopago_payment_id: str | None = None
    mercadopago_preference_id: str | None = None
    package_type: CreditPackageType | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Credit package schemas ────────────────────────────────────


class CreditPackageResponse(BaseModel):
    """Credit package details returned to the client."""

    package_type: CreditPackageType
    credits_count: int
    price_usd: float
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreditsResponse(BaseModel):
    """User's available credits and usage information."""

    free_analyses_count: int
    free_analyses_limit: int
    free_analyses_remaining: int
    paid_analyses_credits: int
    total_analyses_used: int

    class Config:
        from_attributes = True
