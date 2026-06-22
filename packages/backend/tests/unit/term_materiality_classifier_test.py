"""Unit tests for batch LLM term materiality classification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.document import DocumentExtraction, ExtractedTextItem
from src.services.term_materiality_classifier import (
    classify_materiality_batch,
    enrich_extraction_materiality,
)
from src.utils.standard_terms import TermMateriality


def _mock_response(payload: str) -> MagicMock:
    message = MagicMock()
    message.content = payload
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_classify_materiality_batch_parses_llm_response() -> None:
    payload = """
    {
      "items": [
        {"text": "DMCA repeat infringer policy", "materiality": "standard_industry"},
        {"text": "Binding arbitration clause", "materiality": "notable"},
        {"text": "We sell your personal data", "materiality": "material_risk"}
      ]
    }
    """
    with patch(
        "src.services.term_materiality_classifier.acompletion_with_fallback",
        new=AsyncMock(return_value=_mock_response(payload)),
    ):
        result = await classify_materiality_batch(
            [
                "DMCA repeat infringer policy",
                "Binding arbitration clause",
                "We sell your personal data",
            ]
        )

    assert result["DMCA repeat infringer policy"] == TermMateriality.STANDARD_INDUSTRY
    assert result["Binding arbitration clause"] == TermMateriality.NOTABLE
    assert result["We sell your personal data"] == TermMateriality.MATERIAL_RISK


@pytest.mark.asyncio
async def test_classify_materiality_batch_empty_input() -> None:
    assert await classify_materiality_batch([]) == {}


@pytest.mark.asyncio
async def test_enrich_extraction_materiality_fills_unlabeled_dangers() -> None:
    extraction = DocumentExtraction(
        source_content_hash="abc",
        dangers=[
            ExtractedTextItem(value="DMCA repeat infringer policy"),
            ExtractedTextItem(
                value="We sell personal information",
                materiality="material_risk",
            ),
        ],
    )
    payload = """
    {
      "items": [
        {"text": "DMCA repeat infringer policy", "materiality": "standard_industry"}
      ]
    }
    """
    with patch(
        "src.services.term_materiality_classifier.acompletion_with_fallback",
        new=AsyncMock(return_value=_mock_response(payload)),
    ):
        await enrich_extraction_materiality(extraction)

    assert extraction.dangers[0].materiality == "standard_industry"
    assert extraction.dangers[1].materiality == "material_risk"


@pytest.mark.asyncio
async def test_filter_danger_strings_llm() -> None:
    from src.services.term_materiality_classifier import filter_danger_strings_llm

    payload = """
    {
      "items": [
        {"text": "DMCA repeat infringer policy", "materiality": "standard_industry"},
        {"text": "We sell your personal data", "materiality": "material_risk"}
      ]
    }
    """
    with patch(
        "src.services.term_materiality_classifier.acompletion_with_fallback",
        new=AsyncMock(return_value=_mock_response(payload)),
    ):
        filtered = await filter_danger_strings_llm(
            ["DMCA repeat infringer policy", "We sell your personal data"]
        )

    assert filtered == ["We sell your personal data"]


@pytest.mark.asyncio
async def test_enrich_skips_when_all_labeled() -> None:
    extraction = DocumentExtraction(
        source_content_hash="abc",
        dangers=[
            ExtractedTextItem(value="Sells data", materiality="material_risk"),
        ],
    )
    with patch(
        "src.services.term_materiality_classifier.acompletion_with_fallback",
        new=AsyncMock(),
    ) as mock_llm:
        await enrich_extraction_materiality(extraction)
        mock_llm.assert_not_called()
