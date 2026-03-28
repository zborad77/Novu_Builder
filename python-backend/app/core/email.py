"""Transactional email backend (C7).

Sends password reset emails via SMTP. In development (SMTP_HOST unset), emails
are printed to stdout instead of sent — no external dependency required for
local development or CI.
"""
import asyncio
import smtplib
import structlog
from email.message import EmailMessage

logger = structlog.get_logger(__name__)


def _send_sync(*, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.smtp_host:
        # Dev/CI fallback — print to stdout
        logger.info(
            "email.dev_stdout",
            to=to,
            subject=subject,
            body=body_text,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        logger.info("email.sent", to=to, subject=subject)
    except Exception as exc:
        logger.error("email.send_failed", to=to, subject=subject, error=str(exc))
        raise


async def send_email(*, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Send an email asynchronously (offloads blocking SMTP to a thread)."""
    await asyncio.to_thread(_send_sync, to=to, subject=subject, body_text=body_text, body_html=body_html)


async def send_password_reset_email(*, to: str, reset_url: str, expires_minutes: int) -> None:
    """Send the password reset email with the one-time reset link."""
    subject = "Password Reset Request"
    body_text = (
        f"You requested a password reset.\n\n"
        f"Click the link below to set a new password (valid for {expires_minutes} minutes):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, please ignore this email.\n"
    )
    body_html = (
        f"<p>You requested a password reset.</p>"
        f"<p><a href=\"{reset_url}\">Reset your password</a> "
        f"(link valid for {expires_minutes} minutes)</p>"
        f"<p>If you did not request this, please ignore this email.</p>"
    )
    await send_email(to=to, subject=subject, body_text=body_text, body_html=body_html)
