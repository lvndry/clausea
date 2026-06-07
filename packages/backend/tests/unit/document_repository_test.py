"""Regression tests for DocumentRepository.update — guards against the partial-loader text-loss bug.

Background: find_by_product_id projects out text/markdown and fills them with "".
If a caller then passes such a partial Document into update(), $set(model_dump())
would overwrite the real stored text with "". The update() method must drop empty
text/markdown from the $set payload when the stored row already has content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.models.document import Document
from src.repositories.document_repository import DocumentRepository


def _make_doc(text: str, markdown: str) -> Document:
    return Document(
        id="doc-1",
        url="https://example.com/policy",
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown=markdown,
        text=text,
        metadata={},
        versions=[],
        analysis=None,
        extraction=None,
        locale=None,
        regions=[],
        effective_date=None,
        created_at=datetime(2026, 1, 1),
    )


def _fake_db_with_existing(text: str, markdown: str) -> tuple[Any, AsyncMock]:
    """Return a db-like mock whose documents.update_one captures the $set payload."""
    documents_collection = AsyncMock()
    documents_collection.find_one = AsyncMock(
        return_value={"id": "doc-1", "text": text, "markdown": markdown}
    )
    update_result = AsyncMock()
    update_result.modified_count = 1
    documents_collection.update_one = AsyncMock(return_value=update_result)

    db = AsyncMock()
    db.documents = documents_collection
    return db, documents_collection.update_one


@pytest.mark.asyncio
async def test_update_drops_empty_text_when_stored_has_content() -> None:
    """Partial-loader regression: empty incoming text must not wipe stored text."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="real policy content " * 100, markdown="# real")
    partial_doc = _make_doc(text="", markdown="")

    ok = await repo.update(db, partial_doc)
    assert ok is True

    update_one.assert_awaited_once()
    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    assert "text" not in set_payload, "empty incoming text must be dropped from $set"
    assert "markdown" not in set_payload, "empty incoming markdown must be dropped from $set"


@pytest.mark.asyncio
async def test_update_writes_text_when_incoming_has_content() -> None:
    """Normal path: a full Document with real text writes through unchanged."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="old text", markdown="# old")
    full_doc = _make_doc(text="new policy text", markdown="# new")

    ok = await repo.update(db, full_doc)
    assert ok is True

    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    assert set_payload["text"] == "new policy text"
    assert set_payload["markdown"] == "# new"


@pytest.mark.asyncio
async def test_update_allows_empty_when_stored_is_also_empty() -> None:
    """Edge case: both sides empty means there is nothing to protect."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="", markdown="")
    doc = _make_doc(text="", markdown="")

    ok = await repo.update(db, doc)
    assert ok is True
    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    # Empty values are allowed to be written since stored is also empty.
    assert set_payload.get("text", "") == ""
    assert set_payload.get("markdown", "") == ""


@pytest.mark.asyncio
async def test_save_refuses_empty_document() -> None:
    """Inserts with both text and markdown empty must raise — masking crawl bugs is bad."""
    repo = DocumentRepository()
    documents_collection = AsyncMock()
    documents_collection.insert_one = AsyncMock()
    db = AsyncMock()
    db.documents = documents_collection
    doc = _make_doc(text="   ", markdown="")  # whitespace counts as empty

    with pytest.raises(ValueError, match="Refusing to store empty document"):
        await repo.save(db, doc)
    documents_collection.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_accepts_normal_document() -> None:
    repo = DocumentRepository()
    documents_collection = AsyncMock()
    documents_collection.insert_one = AsyncMock()
    db = AsyncMock()
    db.documents = documents_collection
    doc = _make_doc(text="real policy content " * 50, markdown="# real policy")

    saved = await repo.save(db, doc)
    assert saved is doc
    documents_collection.insert_one.assert_awaited_once()
