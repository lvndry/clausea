"""Tests that analyse_document skips when there is no document text."""

from unittest.mock import AsyncMock, patch

import pytest

from src.analyser import analyse_document
from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores


@pytest.mark.asyncio
async def test_analyse_document_skips_when_text_empty() -> None:
    doc = Document(
        url="https://example.com/privacy",
        product_id="p1",
        doc_type="privacy_policy",
        markdown="",
        text="",
    )
    with patch("src.analyser.extract_document_facts", new_callable=AsyncMock) as mock_extract:
        result = await analyse_document(doc, use_cache=False)
    assert result is None
    mock_extract.assert_not_called()


@pytest.mark.asyncio
async def test_analyse_document_skips_when_text_whitespace_only() -> None:
    doc = Document(
        url="https://example.com/privacy",
        product_id="p1",
        doc_type="privacy_policy",
        markdown="   \n\t  ",
        text="   \n\t  ",
    )
    with patch("src.analyser.extract_document_facts", new_callable=AsyncMock) as mock_extract:
        result = await analyse_document(doc, use_cache=False)
    assert result is None
    mock_extract.assert_not_called()


@pytest.mark.asyncio
async def test_analyse_document_empty_text_does_not_use_cache() -> None:
    """Stale analysis on the model must not be returned when there is no text."""
    cached = DocumentAnalysis(
        summary="cached",
        scores={
            "transparency": DocumentAnalysisScores(score=5, justification=""),
            "data_collection_scope": DocumentAnalysisScores(score=5, justification=""),
            "user_control": DocumentAnalysisScores(score=5, justification=""),
            "third_party_sharing": DocumentAnalysisScores(score=5, justification=""),
            "data_retention_score": DocumentAnalysisScores(score=5, justification=""),
            "security_score": DocumentAnalysisScores(score=5, justification=""),
        },
        risk_score=5,
        verdict="moderate",
        keypoints=[],
    )
    doc = Document(
        url="https://example.com/privacy",
        product_id="p1",
        doc_type="privacy_policy",
        markdown="",
        text="",
        metadata={"content_hash": "abc"},
        analysis=cached,
    )
    with patch("src.analyser.extract_document_facts", new_callable=AsyncMock) as mock_extract:
        result = await analyse_document(doc, use_cache=True)
    assert result is None
    mock_extract.assert_not_called()
