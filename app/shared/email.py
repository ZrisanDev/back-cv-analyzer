"""Shared email service using aiosmtplib with Gmail SMTP."""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.shared.config import settings

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

# ── HTML templates ──────────────────────────────────────────

_PASSWORD_RESET_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Restablecer contraseña — CV Analyzer</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:32px 0;">
  <tr>
    <td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;">
        <!-- Header -->
        <tr>
          <td style="background-color:#2563eb;padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:24px;">CV Analyzer</h1>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:40px;">
            <h2 style="margin:0 0 16px;color:#1f2937;font-size:20px;">Restablecer tu contraseña</h2>
            <p style="margin:0 0 24px;color:#4b5563;font-size:16px;line-height:1.5;">
              Recibimos una solicitud para restablecer la contraseña de tu cuenta.
              Hacé clic en el botón de abajo para crear una nueva contraseña:
            </p>
            <p style="text-align:center;margin:32px 0;">
              <a href="{reset_link}"
                 style="display:inline-block;background-color:#2563eb;color:#ffffff;padding:14px 32px;border-radius:6px;text-decoration:none;font-size:16px;font-weight:bold;">
                Restablecer contraseña
              </a>
            </p>
            <p style="margin:0 0 8px;color:#6b7280;font-size:14px;line-height:1.5;">
              O copiá y pegá este enlace en tu navegador:
            </p>
            <p style="margin:0 0 24px;color:#2563eb;font-size:14px;word-break:break-all;">
              {reset_link}
            </p>
            <p style="margin:0 0 8px;color:#9ca3af;font-size:13px;">
              Este enlace expira en 1 hora. Si no solicitaste este cambio, podés ignorar este correo.
            </p>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="background-color:#f9fafb;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:12px;">
              CV Analyzer &mdash; Plataforma de análisis de CVs
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


# ── Core email function ─────────────────────────────────────


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
) -> None:
    """Send an HTML email via Gmail SMTP.

    Silently logs errors instead of raising — callers decide
    whether the failure should propagate.
    """
    if not settings.gmail_email or not settings.gmail_app_password:
        logger.error(
            "Email credentials not configured (GMAIL_EMAIL / GMAIL_APP_PASSWORD). "
            "Skipping email send to %s",
            to_email,
        )
        return

    message = EmailMessage()
    message["From"] = settings.gmail_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(
        "Por favor, habilitá HTML en tu cliente de correo para ver este mensaje.",
    )
    message.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=GMAIL_SMTP_HOST,
            port=GMAIL_SMTP_PORT,
            start_tls=True,
            username=settings.gmail_email,
            password=settings.gmail_app_password,
        )
        logger.info("Email sent successfully to %s", to_email)
    except aiosmtplib.SMTPException as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


# ── Domain-specific senders ─────────────────────────────────


async def send_password_reset_email(
    to_email: str,
    reset_token: str,
) -> None:
    """Send a password-reset email with a link containing the JWT token."""
    # The frontend will build the full URL.  We embed the token in the link
    # and let the FE decide the base URL via a query param or path segment.
    reset_link = f"https://cv-analyzer.app/reset-password?token={reset_token}"

    html = _PASSWORD_RESET_TEMPLATE.format(reset_link=reset_link)

    await send_email(
        to_email=to_email,
        subject="Restablecer tu contraseña — CV Analyzer",
        html_content=html,
    )
