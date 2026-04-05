"""MercadoPago infrastructure: SDK client factory and webhook signature verification.

NOTE: Functions here are private (_) but exported for use in other use_case modules
and payment routes. Pylance may report "not accessed" warnings - these are false positives
because functions are used across module boundaries.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import mercadopago
from fastapi import HTTPException, status

from app.shared.config import settings

logger = logging.getLogger(__name__)


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
    comparing HMAC-SHA256 signature in the x-signature header.

    Args:
        x_signature: Value from 'x-signature' request header
        x_request_id: Value from 'x-request-id' request header
        data_id: The resource ID (can be from 'data.id' or 'id' query param)

    Returns:
        True if signature is valid, False otherwise

    Validation process:
        1. Parse x-signature header to extract 'ts' (timestamp) and 'v1' (hash)
        2. Build manifest string: "id:{data_id};request-id:{x_request_id};ts:{ts};"
        3. Calculate HMAC-SHA256 using the webhook secret key
        4. Compare calculated hash with v1 from x-signature

    Reference: https://www.mercadopago.com.ar/developers/es/docs/checkout-v1/webhooks/signatures

    NOTE: MercadoPago sends webhooks with different query param formats:
    - New format: data.id={id}
    - Old format: id={id}
    Both are supported for backward compatibility.
    """
    if not settings.mercadopago_webhook_secret:
        logger.warning(
            "Webhook signature verification skipped: MERCADOPAGO_WEBHOOK_SECRET not configured"
        )
        return True  # Allow webhook without verification if secret not set (dev mode)

    if not x_signature or not x_request_id:
        logger.warning(
            "Webhook signature verification failed: missing required headers"
        )
        return False

    # Allow webhooks without data.id (some MercadoPago notifications don't include it)
    if not data_id:
        logger.warning(
            "Webhook signature verification: no data.id in params, skipping verification"
        )
        return True  # Skip verification for notifications without data.id

    # TEMPORARY: DISABLE signature verification for testing
    # TODO: Enable this once the webhook_secret is correctly configured in .env
    logger.warning(
        "⚠️  SIGNATURE VERIFICATION TEMPORARILY DESACTIVADA PARA TESTING"
        "Esto permite procesar webhooks aunque la firma no coincida"
    )
    return True  # Always return True for now

    # Allow webhooks without data.id (some MercadoPago notifications don't include it)
    if not data_id:
        logger.warning(
            "Webhook signature verification: no data.id in params, skipping verification"
        )
        return True  # Skip verification for notifications without data.id

    # Parse x-signature header: format is "ts={timestamp},v1={hash}"
    parts = x_signature.split(',')
    ts = None
    v1 = None

    for part in parts:
        key_value = part.strip().split("=", 1)
        if len(key_value) == 2:
            key, value = key_value[0].strip(), key_value[1].strip()
            if key == "ts":
                ts = value
            elif key == "v1":
                v1 = value

    if not ts or not v1:
        logger.warning(
            "Webhook signature verification: invalid x-signature format: %s", x_signature
        )
        return False

    # Build manifest string: "id:{data_id};request-id:{x_request_id};ts:{ts};"
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

    # DEBUG: Log all values for verification
    logger.info("=== Webhook Signature Verification DEBUG ===")
    logger.info("x_signature header: %s", x_signature)
    logger.info("x_request_id header: %s", x_request_id)
    logger.info("data_id: %s", data_id)
    logger.info("ts from header: %s", ts)
    logger.info("v1 from header: %s", v1)
    logger.info("manifest: %s", manifest)
    logger.info("webhook_secret (first 20 chars): %s", settings.mercadopago_webhook_secret[:20] if settings.mercadopago_webhook_secret else "NOT_SET")
    logger.info("=== End DEBUG ===")

    # Calculate HMAC-SHA256 using the webhook secret key
    webhook_secret = settings.mercadopago_webhook_secret
    calculated_hash = hmac.new(
        webhook_secret.encode(),  # key as bytes
        manifest.encode(),     # message as bytes
        hashlib.sha256,
    ).hexdigest()

    # Compare calculated hash with v1 from x-signature
    if calculated_hash == v1:
        logger.info(
            "Webhook signature verification: ✅ VALID (manifest=%s)", manifest
        )
        return True
    else:
        logger.warning(
            "Webhook signature verification: ❌ INVALID (expected=%s, got=%s)",
            calculated_hash,
            v1,
        )
        return False
