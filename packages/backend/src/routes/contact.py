"""Contact form endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from src.core.logging import get_logger
from src.services.email_service import EmailServiceError, get_email_service

logger = get_logger(__name__)

router = APIRouter(prefix="/contact", tags=["contact"])


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    company: str | None = None
    message: str


@router.post("")
async def submit_contact_form(req: ContactRequest) -> dict[str, str]:
    """Handle contact form submissions."""
    email_service = get_email_service()

    company_line = f"Company: {req.company}\n" if req.company else ""
    subject = f"Clausea - Contact form: {req.name}"
    body = (
        f"New contact form submission\n\n"
        f"Name: {req.name}\n"
        f"Email: {req.email}\n"
        f"{company_line}"
        f"Message:\n{req.message}"
    )

    try:
        await email_service.send_contact_email(
            subject=subject,
            body=body,
        )
    except EmailServiceError as e:
        logger.error("Failed to send contact form email")
        raise HTTPException(
            status_code=500, detail="Failed to send message. Please try again."
        ) from e

    return {"status": "ok"}
