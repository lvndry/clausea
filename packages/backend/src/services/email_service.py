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
            f"Target apps data: https://github.com/lvndry/clausea/blob/main/packages/backend/src/data/target_apps.json"
            f"{metadata_block}"
        )

        await self._send_email(subject=subject, to_email=self.to_email, text=body)

    async def send_contact_email(self, *, subject: str, body: str) -> None:
        """Send an email from the contact form."""
        await self._send_email(subject=subject, to_email=self.to_email, text=body)

    async def send_indexation_complete(
        self,
        *,
        to_email: str,
        product_name: str,
        product_slug: str,
        documents_found: int,
    ) -> None:
        """Send an email to a user when indexation finishes for a product."""
        subject = f"Clausea - Indexation complete for {product_name}"
        docs_label = "document" if documents_found == 1 else "documents"
        company_link = f"https://clausea.co/products/{product_slug}"

        text = (
            f"Indexation is complete for {product_name}.\n\n"
            f"We found {documents_found} {docs_label}.\n\n"
            f"View the company analysis: {company_link}\n\n"
            "If you didn’t request this email, you can ignore it."
        )
        preview = f"Indexation complete — {documents_found} {docs_label} found."

        html = f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="x-apple-disable-message-reformatting" />
    <title>{subject}</title>
    <style>
      @media (prefers-color-scheme: dark) {{
        .bg {{ background: #0b0f1a !important; }}
        .card {{ background: rgba(255,255,255,0.06) !important; border-color: rgba(255,255,255,0.12) !important; }}
        .muted {{ color: rgba(255,255,255,0.72) !important; }}
        .text {{ color: rgba(255,255,255,0.92) !important; }}
        .divider {{ border-color: rgba(255,255,255,0.12) !important; }}
      }}
    </style>
  </head>
  <body class="bg" style="margin:0; padding:0; background:#f6f7fb; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,Helvetica,Arial,sans-serif;">
    <div style="display:none; max-height:0; overflow:hidden; opacity:0; color:transparent;">
      {preview}
    </div>

    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">
      <tr>
        <td align="center" style="padding:28px 16px;">
          <table role="presentation" cellpadding="0" cellspacing="0" width="640" style="width:100%; max-width:640px;">
            <tr>
              <td style="padding:8px 0 18px 0;">
                <div style="display:inline-flex; align-items:center; gap:10px;">
                  <div style="width:34px; height:34px; border-radius:10px; background:linear-gradient(135deg,#7c3aed,#06b6d4);"></div>
                  <div style="line-height:1;">
                    <div class="text" style="font-weight:800; letter-spacing:-0.02em; color:#111827; font-size:16px;">Clausea</div>
                    <div class="muted" style="color:#6b7280; font-size:12px; margin-top:4px;">Legal document intelligence</div>
                  </div>
                </div>
              </td>
            </tr>

            <tr>
              <td class="card" style="background:#ffffff; border:1px solid rgba(17,24,39,0.08); border-radius:18px; padding:22px;">
                <div class="text" style="color:#111827; font-weight:800; letter-spacing:-0.03em; font-size:22px; margin:0 0 10px 0;">
                  Indexation complete
                </div>
                <div class="muted" style="color:#4b5563; font-size:14px; line-height:1.6; margin:0 0 18px 0;">
                  Your company analysis for <span class="text" style="color:#111827; font-weight:700;">{product_name}</span> is ready.
                </div>

                <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse; margin:0 0 18px 0;">
                  <tr>
                    <td style="padding:14px 14px; border-radius:14px; background:linear-gradient(135deg, rgba(124,58,237,0.10), rgba(6,182,212,0.10)); border:1px solid rgba(17,24,39,0.06);">
                      <div class="muted" style="color:#374151; font-size:13px; line-height:1.45;">
                        We found <span class="text" style="color:#111827; font-weight:800;">{documents_found}</span> {docs_label}.
                      </div>
                      <div class="muted" style="color:#6b7280; font-size:12px; margin-top:6px;">
                        Tip: open the Sources tab to view the exact documents Clausea analyzed.
                      </div>
                    </td>
                  </tr>
                </table>

                <table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                  <tr>
                    <td>
                      <a href="{company_link}"
                         style="display:inline-block; background:linear-gradient(135deg,#7c3aed,#06b6d4); color:#ffffff; text-decoration:none; font-weight:800; font-size:14px; padding:12px 16px; border-radius:12px;">
                        View the company analysis
                      </a>
                    </td>
                  </tr>
                </table>

                <div class="divider" style="border-top:1px solid rgba(17,24,39,0.08); margin:18px 0;"></div>

                <div class="muted" style="color:#6b7280; font-size:12px; line-height:1.6;">
                  If you didn’t request this email, you can safely ignore it.
                  <br />
                  Link: <a href="{company_link}" style="color:#4f46e5; text-decoration:none;">{company_link}</a>
                </div>
              </td>
            </tr>

            <tr>
              <td style="padding:14px 0 0 0;">
                <div class="muted" style="color:#9ca3af; font-size:11px; line-height:1.6; text-align:center;">
                  Clausea • Privacy policy & terms analysis
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

        await self._send_email(subject=subject, to_email=to_email, text=text, html=html)

    async def _send_email(
        self,
        *,
        subject: str,
        to_email: str,
        text: str | None = None,
        html: str | None = None,
    ) -> None:
        api_key = self.api_key
        if not api_key:
            raise EmailServiceError("RESEND_API_KEY is not configured")

        if not text and not html:
            raise EmailServiceError("Email must include text or html body")

        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
            "text": text,
            "html": html,
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
