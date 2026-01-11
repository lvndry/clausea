"""Email service for sending Clausea notifications."""

from __future__ import annotations

import asyncio
import os
from typing import Final

import resend
import structlog

logger = structlog.get_logger(service="email-service")


class EmailServiceError(Exception):
    """Raised when the email service cannot send a message."""


class EmailService:
    """Resend-backed email delivery service."""

    DEFAULT_RECIPIENT: Final[str] = "lvndry@protonmail.com"

    def __init__(self) -> None:
        self.api_key: str | None = os.getenv("RESEND_API_KEY")
        self.from_email: str = os.getenv(
            "SUPPORT_ALERT_EMAIL_FROM", "Clausea Alerts <alerts@contact.clausea.co>"
        )
        self.to_email: str = os.getenv("SUPPORT_ALERT_EMAIL_TO", self.DEFAULT_RECIPIENT)

        if not self.api_key:
            logger.warning("RESEND_API_KEY is not configured; email sending will fail")
        else:
            resend.api_key = self.api_key

    async def send_support_request(
        self,
        *,
        domain: str,
        url: str,
        source: str,
        metadata: dict | None = None,
    ) -> None:
        """Send an email notifying that a user requested support for a domain."""

        metadata_block = ""
        if metadata:
            lines = ["", "Additional metadata:"]
            for key, value in metadata.items():
                lines.append(f"- {key}: {value}")
            metadata_block = "\n".join(lines)

        subject = f"Clausea - Support request for {domain}"
        body = (
            "A user requested that Clausea support this site.\n\n"
            f"Domain: {domain}\n"
            f"URL: {url}\n"
            f"Source: {source}\n"
            f"Dashboard: https://clausea.co/products/{domain}\n"
            f"Target apps data: https://github.com/lvndry/clausea/blob/main/apps/backend/src/data/target_apps.json"
            f"{metadata_block}"
        )

        await self._send_email(subject=subject, body=body, to_email=self.to_email)

    async def _send_email(self, *, subject: str, body: str, to_email: str) -> None:
        api_key = self.api_key
        if not api_key:
            raise EmailServiceError("RESEND_API_KEY is not configured")

        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }

        def _send() -> None:
            resend.Emails.send(payload)  # type: ignore

        try:
            await asyncio.to_thread(_send)
            logger.info("support email sent", to=to_email, subject=subject)
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to send support email", error=str(exc))
            raise EmailServiceError("Failed to send support email") from exc


_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
