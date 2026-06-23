"""Tests for LLM re-analysis skip when findings already exist for a document.

When a pipeline job re-runs on a product whose documents were already analysed
in a previous run, calling the LLM again would waste tokens and time if the
document content hasn't changed.  The skip logic in
``analyse_product_documents`` compares the stored extraction's
``source_content_hash`` against the current content hash to decide whether to
reuse the existing analysis.

These tests do NOT hit the network, a real LLM, or MongoDB — they exercise only
the in-process skip decision and the ``AnalysisResult.analyses_skipped`` counter.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from src.analyser import AnalysisResult, _analysis_up_to_date, analyse_product_documents
from src.models.document import (
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentExtraction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        summary="existing summary",
        scores={"transparency": DocumentAnalysisScores(score=5, justification="ok")},
        risk_score=5,
        verdict="moderate",
    )


def _content_hash_for(doc: Document) -> str:
    """Mirror the hash the extraction service uses (SHA-256 of markdown+doc_type)."""
    content = f"{doc.markdown}{doc.doc_type}"
    return hashlib.sha256(content.encode()).hexdigest()


def _make_doc_with_current_analysis(doc_id: str, url: str) -> Document:
    """A document whose extraction was built from its current content."""
    doc = Document(
        id=doc_id,
        url=url,
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="This is the full policy text " * 30,
        analysis=_make_analysis(),
    )
    doc.extraction = DocumentExtraction(
        source_content_hash=_content_hash_for(doc),
    )
    return doc


def _make_doc_without_analysis(doc_id: str, url: str) -> Document:
    """A new document that has not yet been analysed."""
    return Document(
        id=doc_id,
        url=url,
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="Brand new policy text " * 30,
        analysis=None,
        extraction=None,
    )


def _make_doc_with_stale_analysis(doc_id: str, url: str) -> Document:
    """A document whose content changed after the last analysis run."""
    doc = Document(
        id=doc_id,
        url=url,
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="Old policy text " * 30,
        analysis=_make_analysis(),
    )
    # Point the extraction at a *different* content (stale hash).
    doc.extraction = DocumentExtraction(
        source_content_hash="0000000000000000000000000000000000000000000000000000000000000000",
    )
    return doc


# ---------------------------------------------------------------------------
# Unit tests for _analysis_up_to_date helper
# ---------------------------------------------------------------------------


def test_up_to_date_true_when_hashes_match() -> None:
    doc = _make_doc_with_current_analysis("d1", "https://example.com/privacy")
    assert _analysis_up_to_date(doc) is True


def test_up_to_date_false_when_no_analysis() -> None:
    doc = _make_doc_without_analysis("d1", "https://example.com/privacy")
    assert _analysis_up_to_date(doc) is False


def test_up_to_date_false_when_no_extraction() -> None:
    doc = Document(
        id="d1",
        url="https://example.com/privacy",
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="text " * 50,
        analysis=_make_analysis(),
        extraction=None,
    )
    assert _analysis_up_to_date(doc) is False


def test_up_to_date_false_when_content_changed() -> None:
    doc = _make_doc_with_stale_analysis("d1", "https://example.com/privacy")
    assert _analysis_up_to_date(doc) is False


# ---------------------------------------------------------------------------
# Integration-style tests for analyse_product_documents skip path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_up_to_date_documents_are_skipped() -> None:
    """Documents with current analysis must not trigger an LLM call."""
    docs = [
        _make_doc_with_current_analysis("a", "https://x/a"),
        _make_doc_with_current_analysis("b", "https://x/b"),
    ]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)

    with patch("src.analyser.analyse_document", new_callable=AsyncMock) as mock_analyse:
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert isinstance(result, AnalysisResult)
    assert result.analyses_skipped == 2
    mock_analyse.assert_not_called()


@pytest.mark.asyncio
async def test_new_documents_are_analysed() -> None:
    """Documents without existing analysis must go through the LLM."""
    docs = [_make_doc_without_analysis("a", "https://x/a")]
    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    with patch("src.analyser.analyse_document", new_callable=AsyncMock) as mock_analyse:
        mock_analyse.return_value = _make_analysis()
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert result.analyses_skipped == 0
    mock_analyse.assert_called_once()


@pytest.mark.asyncio
async def test_mixed_documents_only_new_ones_are_analysed() -> None:
    """With a mix of up-to-date and new documents, only new ones trigger LLM."""
    up_to_date = _make_doc_with_current_analysis("existing", "https://x/existing")
    new_doc = _make_doc_without_analysis("new", "https://x/new")
    docs = [up_to_date, new_doc]

    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    with patch("src.analyser.analyse_document", new_callable=AsyncMock) as mock_analyse:
        mock_analyse.return_value = _make_analysis()
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert result.analyses_skipped == 1
    assert mock_analyse.call_count == 1
    called_doc = mock_analyse.call_args[0][0]
    assert called_doc.id == "new"


@pytest.mark.asyncio
async def test_stale_analysis_is_reanalysed() -> None:
    """A document whose content changed since last analysis must be re-analysed."""
    doc = _make_doc_with_stale_analysis("stale", "https://x/stale")
    docs = [doc]

    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    with patch("src.analyser.analyse_document", new_callable=AsyncMock) as mock_analyse:
        mock_analyse.return_value = _make_analysis()
        result = await analyse_product_documents(
            db=AsyncMock(), product_slug="example", document_svc=document_svc
        )

    assert result.analyses_skipped == 0
    mock_analyse.assert_called_once()


@pytest.mark.asyncio
async def test_force_reanalyze_bypasses_skip() -> None:
    """force_reanalyze=True must re-run LLM even for up-to-date documents."""
    doc = _make_doc_with_current_analysis("d1", "https://x/d1")
    docs = [doc]

    document_svc = AsyncMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=docs)
    document_svc.update_document = AsyncMock(return_value=True)
    document_svc.update_document_analysis = AsyncMock(return_value=True)

    with patch("src.analyser.analyse_document", new_callable=AsyncMock) as mock_analyse:
        mock_analyse.return_value = _make_analysis()
        result = await analyse_product_documents(
            db=AsyncMock(),
            product_slug="example",
            document_svc=document_svc,
            force_reanalyze=True,
        )

    assert result.analyses_skipped == 0
    mock_analyse.assert_called_once()
