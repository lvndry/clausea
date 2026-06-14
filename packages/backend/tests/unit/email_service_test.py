"""Tests for EmailService admin alerts."""

from unittest.mock import AsyncMock

import pytest

from src.services.email_service import EmailService


@pytest.mark.asyncio
async def test_send_no_documents_alert_goes_to_admin_with_diagnostics(monkeypatch):
    service = EmailService()
    service.to_email = "admin@example.com"

    sent = AsyncMock()
    monkeypatch.setattr(service, "_send_email", sent)

    await service.send_no_documents_alert(
        product_name="CapCut",
        product_slug="capcut",
        url="https://www.capcut.com",
        reason="No policy documents found on this site",
        crawl_error_count=0,
        skip_count=3,
    )

    sent.assert_awaited_once()
    kwargs = sent.await_args.kwargs
    assert kwargs["to_email"] == "admin@example.com"
    assert "capcut" in kwargs["subject"].lower()
    body = kwargs["text"]
    assert "https://www.capcut.com" in body
    assert "No policy documents found on this site" in body
    # The per-URL diagnostics counts are surfaced for triage.
    assert "3" in body
