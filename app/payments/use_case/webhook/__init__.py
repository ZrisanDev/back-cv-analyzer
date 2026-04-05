"""Webhook processing module for MercadoPago payment notifications."""

from app.payments.use_case.webhook.processor import process_webhook

__all__ = ["process_webhook"]
