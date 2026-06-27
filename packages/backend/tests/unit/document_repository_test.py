"""Regression tests for DocumentRepository.update — guards against the partial-loader text-loss bug.

Background: find_by_product_id projects out text/markdown and fills them with "".
If a caller then passes such a partial Document into update(), $set(model_dump())
would overwrite the real stored text with "". The update() method must drop empty
text/markdown from the $set payload when the stored row already has content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.document import Document
from src.repositories.document_repository import DocumentRepository


def _make_doc(markdown: str) -> Document:
    return Document(
        id="doc-1",
        url="https://example.com/policy",
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown=markdown,
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
        return_value={
            "id": "doc-1",
            "text": text,
            "markdown": markdown,
            "product_id": "prod-1",
            "product_ids": ["prod-1"],
        }
    )
    update_result = AsyncMock()
    update_result.modified_count = 1
    update_result.matched_count = 1
    documents_collection.update_one = AsyncMock(return_value=update_result)

    db = AsyncMock()
    db.documents = documents_collection
    return db, documents_collection.update_one


@pytest.mark.asyncio
async def test_update_excludes_text_from_set_payload() -> None:
    """text is a transient computed field and must never appear in the $set payload."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="real policy content " * 100, markdown="# real")
    partial_doc = _make_doc("")

    ok = await repo.update(db, partial_doc)
    assert ok is True

    update_one.assert_awaited_once()
    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    assert "text" not in set_payload, "empty incoming text must be dropped from $set"
    assert "markdown" not in set_payload, "empty incoming markdown must be dropped from $set"


@pytest.mark.asyncio
async def test_update_writes_text_when_incoming_has_content() -> None:
    """Normal path: a full Document with real content writes markdown through unchanged.

    text is a transient derived field — it is always excluded from MongoDB writes.
    Only markdown (the canonical representation) is expected in the $set payload.
    """
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="old text", markdown="# old")
    full_doc = _make_doc("# new")

    ok = await repo.update(db, full_doc)
    assert ok is True

    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    # text is transient and excluded from MongoDB writes; only markdown is persisted.
    assert "text" not in set_payload
    assert set_payload["markdown"] == "# new"


@pytest.mark.asyncio
async def test_update_allows_empty_when_stored_is_also_empty() -> None:
    """Edge case: both sides empty means there is nothing to protect."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="", markdown="")
    doc = _make_doc("")

    ok = await repo.update(db, doc)
    assert ok is True
    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    # Empty values are allowed to be written since stored is also empty.
    assert set_payload.get("text", "") == ""
    assert set_payload.get("markdown", "") == ""


@pytest.mark.asyncio
async def test_update_preserves_canonical_owner_on_product_scoped_write() -> None:
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(text="old text", markdown="# old")
    scoped_doc = _make_doc("# new")
    scoped_doc.product_id = "prod-2"  # document loaded in product-2 context
    scoped_doc.product_ids = ["prod-2", "prod-1"]

    ok = await repo.update(db, scoped_doc)
    assert ok is True

    args, _kwargs = update_one.call_args
    set_payload = args[1]["$set"]
    assert set_payload["product_id"] == "prod-1"
    assert set_payload["product_ids"] == ["prod-1", "prod-2"]


@pytest.mark.asyncio
async def test_save_refuses_empty_document() -> None:
    """Inserts with both text and markdown empty must raise — masking crawl bugs is bad."""
    repo = DocumentRepository()
    documents_collection = AsyncMock()
    documents_collection.insert_one = AsyncMock()
    db = AsyncMock()
    db.documents = documents_collection
    doc = _make_doc("")  # whitespace counts as empty

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
    doc = _make_doc("# real policy")

    saved = await repo.save(db, doc)
    assert saved is doc
    documents_collection.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_by_product_and_url_scopes_lookup_to_product() -> None:
    repo = DocumentRepository()
    doc = _make_doc("# policy")
    doc.product_id = "prod-primary"
    doc.product_ids = ["prod-primary", "prod-1"]
    documents_collection = AsyncMock()
    documents_collection.find_one = AsyncMock(return_value=doc.model_dump())
    db = AsyncMock()
    db.documents = documents_collection

    found = await repo.find_by_product_and_url(db, "prod-1", "https://example.com/policy")

    documents_collection.find_one.assert_awaited_once_with(
        {
            "$and": [
                {"url": "https://example.com/policy"},
                {"$or": [{"product_id": "prod-1"}, {"product_ids": "prod-1"}]},
            ]
        }
    )
    assert found is not None
    assert found.product_id == "prod-1"
    assert set(found.product_ids) == {"prod-primary", "prod-1"}
    assert found.url == "https://example.com/policy"


@pytest.mark.asyncio
async def test_link_to_product_adds_product_membership() -> None:
    repo = DocumentRepository()
    documents_collection = AsyncMock()
    documents_collection.find_one = AsyncMock(
        return_value={"id": "doc-1", "product_id": "prod-1", "product_ids": ["prod-1"]}
    )
    update_result = AsyncMock()
    update_result.matched_count = 1
    documents_collection.update_one = AsyncMock(return_value=update_result)
    db = AsyncMock()
    db.documents = documents_collection

    linked = await repo.link_to_product(db, "doc-1", "prod-2")

    assert linked is True
    args, _kwargs = documents_collection.update_one.call_args
    assert args[0] == {"id": "doc-1"}
    assert args[1]["$set"]["product_ids"] == ["prod-1", "prod-2"]


@pytest.mark.asyncio
async def test_find_by_product_id_full_contextualizes_product_id() -> None:
    repo = DocumentRepository()
    shared_doc = _make_doc("# policy")
    shared_doc.product_id = "prod-1"
    shared_doc.product_ids = ["prod-1", "prod-2"]

    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[shared_doc.model_dump()])
    documents_collection = MagicMock()
    documents_collection.find = MagicMock(return_value=cursor)
    db = AsyncMock()
    db.documents = documents_collection

    docs = await repo.find_by_product_id_full(db, "prod-2")

    documents_collection.find.assert_called_once_with(
        {"$or": [{"product_id": "prod-2"}, {"product_ids": "prod-2"}]}
    )
    assert len(docs) == 1
    assert docs[0].product_id == "prod-2"
    assert docs[0].url == "https://example.com/policy"


@pytest.mark.asyncio
async def test_find_by_ids_with_extraction_returns_early_when_no_ids() -> None:
    repo = DocumentRepository()
    documents_collection = MagicMock()
    documents_collection.find = MagicMock()
    db = AsyncMock()
    db.documents = documents_collection

    docs = await repo.find_by_ids_with_extraction(db, "prod-1", [])

    assert docs == []
    documents_collection.find.assert_not_called()


@pytest.mark.asyncio
async def test_find_by_ids_with_extraction_fills_missing_markdown() -> None:
    """Projection drops markdown, so the loader must backfill it before model validation."""
    repo = DocumentRepository()
    record = {
        "id": "doc-1",
        "url": "https://example.com/policy",
        "product_id": "prod-1",
        "product_ids": ["prod-1"],
        "doc_type": "privacy_policy",
    }
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[record])
    documents_collection = MagicMock()
    documents_collection.find = MagicMock(return_value=cursor)
    db = AsyncMock()
    db.documents = documents_collection

    docs = await repo.find_by_ids_with_extraction(db, "prod-1", ["doc-1", "doc-1"])

    args, _kwargs = documents_collection.find.call_args
    assert args[0] == {
        "$and": [
            {"id": {"$in": ["doc-1"]}},
            {"$or": [{"product_id": "prod-1"}, {"product_ids": "prod-1"}]},
        ]
    }
    assert args[1] == {"markdown": 0, "analysis": 0, "consumer_explainer": 0}
    assert len(docs) == 1
    assert docs[0].markdown == ""
