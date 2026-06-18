"""Recovery re-analysis of documents dropped by a transient failure.

A transient LLM failure (e.g. a provider rate-limit window defeating all in-run retries)
leaves a document with extraction but no analysis, and nothing re-attempts it — so it is
silently excluded from the product overview forever. ``recover_dropped_analyses`` finds
those documents and re-runs analysis, persisting and invalidating the overview on success.
'other' documents (skipped by design) and documents without extraction are left alone.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.analyser import recover_dropped_analyses
from src.models.document import (
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentExtraction,
)


def _doc(doc_id: str, *, doc_type: str = "terms_of_service", analysis=None, extracted=True):
    return Document(
        id=doc_id,
        url=f"https://x/{doc_id}",
        product_id="prod-1",
        doc_type=doc_type,
        markdown="real policy " * 50,
        text="real policy " * 50,
        analysis=analysis,
        extraction=DocumentExtraction(source_content_hash="h") if extracted else None,
    )


def _stub_analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        summary="ok",
        scores={"transparency": DocumentAnalysisScores(score=5, justification="x")},
        risk_score=5,
        verdict="moderate",
    )


@pytest.mark.asyncio
async def test_recovers_dropped_document_and_clears_error() -> None:
    dropped = _doc("dropped", analysis=None, extracted=True)
    dropped.analysis_error = "previous transient failure"
    done = _doc("done", analysis=_stub_analysis(), extracted=True)

    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=[dropped, done])
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    async def fake_analyse(doc: Document, **_: Any) -> DocumentAnalysis | None:
        return _stub_analysis()

    with (
        patch("src.analyser.analyse_document", side_effect=fake_analyse) as analyse,
        patch("src.analyser.generate_product_overview", new=AsyncMock()) as regen,
    ):
        recovered = await recover_dropped_analyses(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert recovered == 1
    # Only the dropped doc is re-analysed; the already-done one is left alone.
    analyse.assert_awaited_once()
    assert dropped.analysis is not None
    assert dropped.analysis_error is None
    # Per-doc persist must NOT delete the overview (it's rebuilt once at the end instead).
    document_svc.update_document.assert_awaited_once()
    assert document_svc.update_document.await_args.kwargs["invalidate_product_overview"] is False
    # The overview is regenerated so it reflects the recovered document.
    regen.assert_awaited_once()


@pytest.mark.asyncio
async def test_skips_other_docs_and_docs_without_extraction() -> None:
    other = _doc("other", doc_type="other", analysis=None, extracted=True)
    no_extraction = _doc("no_ex", analysis=None, extracted=False)

    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=[other, no_extraction])
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    with (
        patch("src.analyser.analyse_document", new=AsyncMock()) as analyse,
        patch("src.analyser.generate_product_overview", new=AsyncMock()) as regen,
    ):
        recovered = await recover_dropped_analyses(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert recovered == 0
    analyse.assert_not_awaited()  # neither doc is a recovery candidate
    regen.assert_not_awaited()  # nothing recovered → overview left untouched


@pytest.mark.asyncio
async def test_recovery_that_still_fails_is_not_counted() -> None:
    dropped = _doc("dropped", analysis=None, extracted=True)

    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=[dropped])
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    async def still_failing(doc: Document, **_: Any) -> DocumentAnalysis | None:
        return None

    with (
        patch("src.analyser.analyse_document", side_effect=still_failing),
        patch("src.analyser.generate_product_overview", new=AsyncMock()) as regen,
    ):
        recovered = await recover_dropped_analyses(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert recovered == 0
    assert dropped.analysis is None
    document_svc.update_document.assert_not_awaited()  # nothing persisted on continued failure
    regen.assert_not_awaited()  # no recovery → no overview rebuild
