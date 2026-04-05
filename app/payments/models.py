"""SQLAlchemy models for the payments module."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class PaymentStatus(str, enum.Enum):
    """Lifecycle states for a payment.

    Maps to MercadoPago payment statuses:
    - pending: payment created but not yet paid
    - approved: payment confirmed
    - rejected: payment was declined
    - refunded: payment was refunded
    - in_process: payment is being reviewed
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    IN_PROCESS = "in_process"


class CreditPackageType(str, enum.Enum):
    """Types of credit packages available for purchase.

    Maps to predefined bundles of analysis credits:
    - pack_20: 20 analyses
    - pack_50: 50 analyses
    - pack_100: 100 analyses
    """

    pack_20 = "pack_20"
    pack_50 = "pack_50"
    pack_100 = "pack_100"


class CreditPackage(Base):
    """Defines available credit packages with their pricing.

    Seeded by migration with:
    - pack_20: 20 credits, $3.00 USD
    - pack_50: 50 credits, $10.00 USD
    - pack_100: 100 credits, $20.00 USD
    """

    __tablename__ = "credit_packages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    package_type: Mapped[CreditPackageType] = mapped_column(
        Enum(CreditPackageType, name="credit_package_type", native_enum=False),
        unique=True,
        nullable=False,
    )
    credits_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of analysis credits included in this package",
    )
    price_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Price in USD",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this package is currently available for purchase",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CreditPackage type={self.package_type.value!r} "
            f"credits={self.credits_count} price=${self.price_usd}>"
        )


class Payment(Base):
    """Stores payment records linked to users and optionally to analyses."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
        comment="Currency code (USD, ARS, etc.)",
    )
    package_type: Mapped[CreditPackageType | None] = mapped_column(
        Enum(CreditPackageType, name="credit_package_type", native_enum=False),
        nullable=True,
        index=True,
        comment="Type of credit package purchased. Null for individual analyses (legacy).",
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    mercadopago_payment_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
    )
    mercadopago_preference_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    # Additional MercadoPago payment details
    status_detail: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="MercadoPago status detail (e.g., accredited, pending_contingency)",
    )
    date_approved: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When payment was approved",
    )
    payment_method_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="MercadoPago payment method used (e.g., credit_card, debit_card)",
    )
    payer_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Email of the payer from MercadoPago",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id!s} user_id={self.user_id!s} "
            f"status={self.status.value!r} amount={self.amount} "
            f"package_type={self.package_type.value if self.package_type else None}>"
        )
