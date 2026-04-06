"""Payment preference creation: build MercadoPago preferences and persist Payment records."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.models import (
    CreditPackage,
    CreditPackageType,
    Payment,
    PaymentStatus,
)
from app.payments.schemas import (
    CreditPackageType as APICreditPackageType,
    PreferenceResponse,
)
from app.payments.use_case.client import _get_mp_client
from app.shared.config import settings

logger = logging.getLogger(__name__)


async def _build_and_create_mp_preference(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    amount: float,
    package_type: CreditPackageType | None = None,
) -> PreferenceResponse:
    """Build MercadoPago preference payload, call the API, persist Payment, and return response.

    This is the shared core that eliminates duplication between single-analysis
    and credit-package preference creation.

    Args:
        db: Async database session.
        user_id: UUID of the authenticated user.
        title: Human-readable item title for the MercadoPago preference.
        amount: Price in USD.
        package_type: Credit package type if this is a package purchase, None for single analysis.

    Returns:
        PreferenceResponse with preference ID and payment URL.

    Raises:
        HTTPException 503: If MercadoPago is not configured.
        HTTPException 502: If the MercadoPago API call fails or returns invalid data.
    """
    mp = _get_mp_client()

    # Convert USD to PEN for Mercado Pago Peru (1 USD ≈ 3.75 PEN)
    # Mercado Pago Peru only accepts PEN for product payments
    PEN_TO_USD_RATE = 3.75
    amount_pen = round(amount * PEN_TO_USD_RATE, 2)  # Round to 2 decimal places

    # Build preference data following Mercado Pago official documentation
    # Note: site_id is auto-detected from access token, removing explicit site_id
    preference_data: dict[str, Any] = {
        "items": [
            {
                "title": title,
                "quantity":1,
                "unit_price": amount_pen,  # Already rounded float
                "currency_id": "PEN",  # Force PEN currency for Peru
            }
        ],
        "back_urls": {
            "success": f"{settings.frontend_base_url}/payment/success",
            "failure": f"{settings.frontend_base_url}/payment/failure",
            "pending": f"{settings.frontend_base_url}/payment/pending",
        },
        "auto_return": "approved",
        "external_reference": str(user_id),
    }

    # Add notification_url if configured (webhook endpoint for payment notifications)
    if settings.mercadopago_webhook_url:
        preference_data["notification_url"] = settings.mercadopago_webhook_url

    # ==== DETAILED LOGS FOR DEBUGGING ====
    logger.warning("=" * 80)
    logger.warning("MERCADO PAGO - ENVIANDO PREFERENCIA:")
    logger.warning("=" * 80)
    logger.warning("JSON enviado a Mercado Pago API:")
    logger.warning("%s", preference_data)
    logger.warning("Detalles:")
    logger.warning("  - Usuario ID: %s", user_id)
    logger.warning("  - Título: %s", title)
    logger.warning("  - Monto USD: %s", amount)
    logger.warning("  - Monto PEN (convertido): %s", amount_pen)
    logger.warning("  - Tasa de cambio: 1 USD = %s PEN", PEN_TO_USD_RATE)
    logger.warning("  - Moneda: PEN")
    logger.warning("  - Auto return: approved")
    logger.warning("=" * 80)

    logger.info(
        "Creating MercadoPago preference: title=%s, amount=%s PEN (%s USD)",
        title,
        amount_pen,
        amount,
    )

    logger.info(
        "Creating MercadoPago preference with base_url: %s",
        settings.frontend_base_url,
    )
    logger.info(
        "Back URLs: %s",
        preference_data.get("back_urls"),
    )

    try:
        logger.warning("Llamando a Mercado Pago API...")
        mp_response = mp.preference().create(preference_data)
        logger.warning("=" * 80)
        logger.warning("MERCADO PAGO - RESPUESTA RECIBIDA:")
        logger.warning("=" * 80)
        logger.warning("Status HTTP: %s", mp_response.get("status"))
        logger.warning("Response completo:")
        logger.warning("%s", mp_response)
        logger.warning("=" * 80)
    except Exception as exc:
        logger.exception("MercadoPago API error while creating preference")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create payment preference: {exc}",
        ) from exc

    # Mercado Pago Python SDK returns: {"status": 201, "response": {...}}
    # The response contains preference data
    if not isinstance(mp_response, dict):
        logger.error("MercadoPago response is not a dict: %s", type(mp_response))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response format from MercadoPago.",
        )

    mp_data = mp_response.get("response", {})
    preference_id = mp_data.get("id")
    init_point = mp_data.get("init_point", "")
    sandbox_init_point = mp_data.get("sandbox_init_point", "")

    logger.warning("DATOS DE LA PREFERENCIA:")
    logger.warning("  - Preference ID: %s", preference_id)
    logger.warning("  - Site ID: %s", mp_data.get("site_id"))
    logger.warning("  - Currency ID: %s", mp_data.get("items", [{}])[0].get("currency_id") if mp_data.get("items") else "N/A")
    logger.warning("  - Unit Price: %s %s", mp_data.get("items", [{}])[0].get("unit_price") if mp_data.get("items") else "N/A", mp_data.get("items", [{}])[0].get("currency_id") if mp_data.get("items") else "N/A")
    logger.warning("")
    logger.warning("URLs:")
    logger.warning("  - Init Point (PROD): %s", init_point)
    logger.warning("  - Sandbox Init Point (SANDBOX): %s", sandbox_init_point)
    logger.warning("=" * 80)

    if not preference_id:
        logger.error("MercadoPago response missing id. Full response: %s", mp_data)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from MercadoPago: missing preference ID.",
        )

    # Use sandbox URL if available (for testing with sandbox credentials)
    # Sandbox credentials start with APP_USR-
    payment_url = sandbox_init_point if sandbox_init_point else init_point

    logger.warning("")
    logger.warning("=" * 80)
    logger.warning("URL FINAL PARA PAGO:")
    logger.warning("=" * 80)
    logger.warning(payment_url)
    logger.warning("")
    logger.warning("Usando SANDBOX: %s", "SI ✅" if sandbox_init_point else "NO ❌")
    logger.warning("=" * 80)

    if not payment_url:
        logger.error(
            "MercadoPago response missing init_point and sandbox_init_point. Full response: %s",
            mp_data,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from MercadoPago: missing payment URL.",
        )

    # Persist payment record (store in PEN for Mercado Pago Peru)
    payment = Payment(
        user_id=user_id,
        amount=amount_pen,  # Store rounded amount in PEN
        currency="PEN",  # Mercado Pago Peru uses PEN
        status=PaymentStatus.PENDING,
        mercadopago_preference_id=str(preference_id),
        package_type=package_type,
        external_reference=str(user_id),  # Store the external_reference for webhook matching
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)

    api_package_type = APICreditPackageType(package_type.value) if package_type else None

    return PreferenceResponse(
        preference_id=str(preference_id),
        payment_url=payment_url,
        amount=amount,  # Return USD for display to user
        currency="USD",  # Show USD in API response
        package_type=api_package_type,
    )


async def create_preference(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: float | None = None,
) -> PreferenceResponse:
    """Create a MercadoPago payment preference for a single CV analysis.

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

    return await _build_and_create_mp_preference(
        db=db,
        user_id=user_id,
        title="Análisis de CV",
        amount=effective_amount,
        package_type=None,
    )


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

    # Map package type to readable title (sin tildes para evitar errores)
    title_map = {
        CreditPackageType.pack_20: "Pack 20 Analisis de CV",
        CreditPackageType.pack_50: "Pack 50 Analisis de CV",
        CreditPackageType.pack_100: "Pack 100 Analisis de CV",
    }

    title = title_map.get(
        package_type, f"{package_type.value} Analisis de CV"
    )

    return await _build_and_create_mp_preference(
        db=db,
        user_id=user_id,
        title=title,
        amount=package.price_usd,
        package_type=package_type,
    )
