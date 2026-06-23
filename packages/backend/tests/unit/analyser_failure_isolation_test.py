"""Per-document failure isolation in analyse_product_documents.

Phase 2.2 of the ship-readiness spec: one bad document inside a product's
analyse loop must not block the rest. Before this, the inner ``_analyse_one``
caught only ``asyncio.CancelledError`` — any other exception (LLM error, JSON
parse, validation failure) would propagate through ``asyncio.gather`` and fail
the whole product, leaving the overview never generated. Now, sibling tasks
keep running and the function returns the document list with ``analysis``
populated only on the docs that succeeded; the overview stage filters by
``doc.analysis`` so failures contribute nothing rather than poisoning the run.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.analyser import analyse_product_documents
from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores


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
async def test_one_failing_document_does_not_fail_the_product() -> None:
    docs = [
        _make_doc("a", "https://x/a"),
        _make_doc("b", "https://x/b"),
        _make_doc("c", "https://x/c"),
    ]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)

    # Doc 'b' raises a generic exception; 'a' and 'c' succeed.
    async def fake_analyse(doc: Document, **_: Any) -> DocumentAnalysis | None:
        if doc.id == "b":
            raise RuntimeError("simulated LLM blow-up on doc b")
        return _stub_analysis()

    with patch("src.analyser.analyse_document", side_effect=fake_analyse):
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    # All three docs come back (we operate on whatever was loaded).
    ids = sorted(d.id for d in result.documents)
    assert ids == ["a", "b", "c"]

    # The failing doc has no analysis attached; the others do.
    by_id = {d.id: d for d in result.documents}
    assert by_id["a"].analysis is not None
    assert by_id["b"].analysis is None
    assert by_id["c"].analysis is not None

    assert by_id["b"].analysis_error is not None
    assert "RuntimeError" in by_id["b"].analysis_error
    assert by_id["a"].analysis_error is None
    assert by_id["c"].analysis_error is None

    assert document_svc.update_document.await_count == 3


@pytest.mark.asyncio
async def test_dropped_analysis_is_stamped_for_visibility() -> None:
    """A doc dropped because analyse_document returned None must carry a visible marker,
    not look like an intentional skip."""
    docs = [_make_doc("a", "https://x/a")]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)

    async def fake_analyse(doc: Document, **_: Any) -> DocumentAnalysis | None:
        return None

    with patch("src.analyser.analyse_document", side_effect=fake_analyse):
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    doc = result.documents[0]
    assert doc.analysis is None
    assert doc.analysis_error == "analyse_document returned no result after retries"
    document_svc.update_document.assert_awaited()


@pytest.mark.asyncio
async def test_cancellation_still_propagates() -> None:
    """The broad except must not swallow CancelledError — cancellation semantics matter."""
    docs = [_make_doc("a", "https://x/a"), _make_doc("b", "https://x/b")]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)

    async def fake_analyse(doc: Document, **_: Any) -> DocumentAnalysis | None:
        raise asyncio.CancelledError()

    with patch("src.analyser.analyse_document", side_effect=fake_analyse):
        with pytest.raises(asyncio.CancelledError):
            await analyse_product_documents(
                db=AsyncMock(), product_slug="example", document_svc=document_svc
            )
