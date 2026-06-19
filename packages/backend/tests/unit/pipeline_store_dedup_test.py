"""Content-based collapsing of same-content locale variants in _store_documents.

Same policy text at different URLs (e.g. /privacy and /es/privacy) collapses to one
stored doc; genuinely different regional policies (different text) are both kept.
"""

from contextlib import asynccontextmanager
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

import src.pipeline as pipeline_module
from src.models.document import Document
from src.pipeline import PolicyDocumentPipeline


def _doc(url: str, text: str) -> Document:
    return Document(
        id=url,
        url=url,
        product_id="prod-1",
        doc_type="privacy_policy",
        title="Privacy",
        text=text,
        markdown=text,
    )


@pytest.mark.asyncio
async def test_collapses_same_content_locale_variants(monkeypatch):
    stored_urls: list[str] = []

    service = MagicMock()
    # all URLs are new for this product
    service.get_document_by_url = AsyncMock(return_value=None)
    service.link_document_to_product = AsyncMock(return_value=True)
    service.update_document = AsyncMock(return_value=True)

    async def _store(_db, document):
        stored_urls.append(document.url)
        return document

    service.store_document = AsyncMock(side_effect=_store)

    @asynccontextmanager
    async def fake_db_session():
        yield MagicMock()

    monkeypatch.setattr(pipeline_module.pipeline, "db_session", fake_db_session)
    monkeypatch.setattr(pipeline_module.pipeline, "create_document_service", lambda: service)
    monkeypatch.setattr(pipeline_module.document_storer, "db_session", fake_db_session)
    monkeypatch.setattr(pipeline_module.document_storer, "create_document_service", lambda: service)

    pipeline = PolicyDocumentPipeline()

    same = "This Privacy Policy explains what personal data we collect and how we share it. " * 30
    different = "Politique de confidentialité distincte pour l'Union européenne (RGPD). " * 30

    docs = [
        _doc("https://acme.com/es/privacy", same),  # locale variant, same content
        _doc("https://acme.com/privacy", same),  # canonical, same content
        _doc("https://acme.com/fr/privacy", same),  # locale variant, same content
        _doc("https://acme.com/eu/privacy", different),  # different regional policy
    ]

    stored_count = await pipeline._store_documents(docs)

    # Canonical /privacy kept (sorted first), /es and /fr collapsed, /eu kept (different text).
    assert stored_count == 2
    assert "https://acme.com/privacy" in stored_urls
    assert "https://acme.com/eu/privacy" in stored_urls
    assert "https://acme.com/es/privacy" not in stored_urls
    assert "https://acme.com/fr/privacy" not in stored_urls
    service.get_document_by_url.assert_awaited()


@pytest.mark.asyncio
async def test_reuses_canonical_document_across_products(monkeypatch):
    service = MagicMock()
    existing = _doc("https://acme.com/privacy", "Shared privacy policy text. " * 40)
    existing.id = "doc-existing"
    existing.product_id = "prod-a"
    existing.product_ids = ["prod-a"]

    incoming = _doc("https://acme.com/privacy", "Shared privacy policy text. " * 40)
    incoming.product_id = "prod-b"

    service.get_document_by_url = AsyncMock(return_value=existing)
    service.link_document_to_product = AsyncMock(return_value=True)
    service.store_document = AsyncMock()
    service.update_document = AsyncMock()

    @asynccontextmanager
    async def fake_db_session():
        yield MagicMock()

    monkeypatch.setattr(pipeline_module.pipeline, "db_session", fake_db_session)
    monkeypatch.setattr(pipeline_module.pipeline, "create_document_service", lambda: service)
    monkeypatch.setattr(pipeline_module.document_storer, "db_session", fake_db_session)
    monkeypatch.setattr(pipeline_module.document_storer, "create_document_service", lambda: service)

    pipeline = PolicyDocumentPipeline()
    stored_count = await pipeline._store_documents([incoming])

    # No new canonical row should be inserted, but the cross-product link counts
    # as a successful stored document for this product run.
    assert stored_count == 1
    service.link_document_to_product.assert_awaited_once_with(ANY, "doc-existing", "prod-b")
    service.store_document.assert_not_awaited()
    service.update_document.assert_not_awaited()
