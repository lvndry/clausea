"""Regression tests for the "analysis generated but not persisted" bug.

Symptom in production: every recently-analysed document had ``analysis=null`` in
MongoDB even though ``analyse_document`` returned a valid ``DocumentAnalysis`` and
LLM usage was logged with ``reason=success``. The product overview then failed with
"none of N core documents have analysis".

Two mechanisms are covered here:

1. analyse_product_documents must persist analysis through the dedicated surgical
   path (update_document_analysis) so it lands with its own ``$set`` and cannot be
   dropped by a full-document rewrite. A write that does not persist must surface as
   a per-document failure (in-memory ``doc.analysis`` cleared) rather than be masked
   by the in-memory count the overview stage relies on.

2. DocumentRepository.update must guard ``analysis`` / ``extraction`` against the
   round-trip wipe: a Document loaded via a projecting reader (analysis/extraction
   stripped to None) saved back with a full ``model_dump`` must not overwrite the
   stored analysis/extraction with None.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.analyser import analyse_product_documents
from src.models.document import (
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentExtraction,
)
from src.repositories.document_repository import DocumentRepository


def _make_doc(doc_id: str, url: str) -> Document:
    return Document(
        id=doc_id,
        url=url,
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="real policy " * 50,
        metadata={},
        versions=[],
        analysis=None,
        extraction=None,
        locale=None,
        regions=[],
        effective_date=None,
        created_at=datetime(2026, 1, 1),
    )


def _stub_analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        summary="ok",
        scores={"transparency": DocumentAnalysisScores(score=5, justification="x")},
        risk_score=5,
        verdict="moderate",
    )


@pytest.mark.asyncio
async def test_analysis_is_persisted_via_surgical_path() -> None:
    """Each successfully analysed document must be written via update_document_analysis."""
    docs = [_make_doc("a", "https://x/a"), _make_doc("b", "https://x/b")]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    async def fake_analyse(doc: Document, **_: Any) -> DocumentAnalysis:
        return _stub_analysis()

    with patch("src.analyser.analyse_document", side_effect=fake_analyse):
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert document_svc.update_document_analysis.await_count == 2
    persisted_ids = sorted(
        call.args[1] for call in document_svc.update_document_analysis.call_args_list
    )
    assert persisted_ids == ["a", "b"]
    assert all(doc.analysis is not None for doc in result.documents)


@pytest.mark.asyncio
async def test_unpersisted_analysis_is_reported_as_failure_not_masked() -> None:
    """If the analysis write does not land, the doc must NOT count as analysed.

    This is the core of the production bug: analysis was generated (in-memory
    doc.analysis set) but never persisted, yet the pipeline reported success off
    the in-memory count. A write that does not persist must clear doc.analysis so
    the downstream count is truthful.
    """
    docs = [_make_doc("a", "https://x/a")]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)
    # The DB write reports that nothing was persisted.
    document_svc.update_document_analysis = AsyncMock(return_value=False)

    async def fake_analyse(doc: Document, **_: Any) -> DocumentAnalysis:
        return _stub_analysis()

    with patch("src.analyser.analyse_document", side_effect=fake_analyse):
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    # In-memory analysis must be cleared so the pipeline's analysed_count is honest.
    assert result.documents[0].analysis is None


def _fake_db_with_existing(stored: dict[str, Any]) -> tuple[Any, AsyncMock]:
    documents_collection = AsyncMock()
    documents_collection.find_one = AsyncMock(return_value={"id": "doc-1", **stored})
    update_result = MagicMock()
    update_result.matched_count = 1
    update_result.modified_count = 1
    documents_collection.update_one = AsyncMock(return_value=update_result)

    db = AsyncMock()
    db.documents = documents_collection
    return db, documents_collection.update_one


def _doc_without_analysis_or_extraction() -> Document:
    return Document(
        id="doc-1",
        url="https://example.com/policy",
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="# real",
        metadata={},
        versions=[],
        analysis=None,
        extraction=None,
        locale=None,
        regions=[],
        effective_date=None,
        created_at=datetime(2026, 1, 1),
    )


@pytest.mark.asyncio
async def test_update_does_not_wipe_stored_analysis_with_none() -> None:
    """Round-trip-wipe guard: a None analysis must not overwrite stored analysis."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing(
        {"text": "real " * 100, "markdown": "# real", "analysis": _stub_analysis().model_dump()}
    )
    partial_doc = _doc_without_analysis_or_extraction()

    ok = await repo.update(db, partial_doc)
    assert ok is True

    set_payload = update_one.call_args.args[1]["$set"]
    assert "analysis" not in set_payload, "None incoming analysis must be dropped from $set"


@pytest.mark.asyncio
async def test_update_does_not_wipe_stored_extraction_with_none() -> None:
    """Round-trip-wipe guard: a None extraction must not overwrite stored extraction."""
    repo = DocumentRepository()
    stored_extraction = DocumentExtraction(source_content_hash="abc").model_dump()
    db, update_one = _fake_db_with_existing(
        {"text": "real " * 100, "markdown": "# real", "extraction": stored_extraction}
    )
    partial_doc = _doc_without_analysis_or_extraction()

    ok = await repo.update(db, partial_doc)
    assert ok is True

    set_payload = update_one.call_args.args[1]["$set"]
    assert "extraction" not in set_payload, "None incoming extraction must be dropped from $set"


@pytest.mark.asyncio
async def test_update_writes_analysis_when_incoming_has_content() -> None:
    """Normal path: a Document carrying real analysis writes it through unchanged."""
    repo = DocumentRepository()
    db, update_one = _fake_db_with_existing({"text": "old", "markdown": "# old", "analysis": None})
    doc = _doc_without_analysis_or_extraction()
    doc.analysis = _stub_analysis()

    ok = await repo.update(db, doc)
    assert ok is True

    set_payload = update_one.call_args.args[1]["$set"]
    assert set_payload["analysis"]["summary"] == "ok"


@pytest.mark.asyncio
async def test_update_analysis_returns_true_on_identical_byte_match() -> None:
    """A re-analysed document with a byte-identical analysis must still report success.

    Mongo reports modified_count == 0 for a no-op $set; using matched_count keeps the
    surgical persist path from misreporting an unchanged re-run as a failure.
    """
    repo = DocumentRepository()
    documents_collection = AsyncMock()
    update_result = AsyncMock()
    update_result.matched_count = 1
    update_result.modified_count = 0
    documents_collection.update_one = AsyncMock(return_value=update_result)
    db = AsyncMock()
    db.documents = documents_collection

    ok = await repo.update_analysis(db, "doc-1", _stub_analysis())
    assert ok is True
