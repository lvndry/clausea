"""The overview synthesis fires its liveness ping at each long sub-step boundary.

`generate_product_overview` runs rollup build and an LLM synthesis with no DB write of its own.
On a large core-doc set that span can outlast the pipeline stall window, so it accepts an
`on_progress` callback fired before each long sub-step. The pipeline wires that to its
job-heartbeat write; outside the pipeline a None callback must be a no-op.

The LLM, rollup engine, and services are all mocked — no real network or DB calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

from src.analyser import generate_product_overview
from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores


def _core_doc() -> Document:
    analysis = DocumentAnalysis(
        summary="x",
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
        critical_clauses=[],
    )
    return Document(
        url="https://example.com/privacy",
        product_id="p1",
        doc_type="privacy_policy",  # type: ignore[arg-type]
        markdown="",
        analysis=analysis,
    )


def _overview_response() -> ModelResponse:
    payload = {
        "summary": "ok",
        "scores": {
            "transparency": {"score": 5, "justification": ""},
            "data_collection_scope": {"score": 5, "justification": ""},
            "user_control": {"score": 5, "justification": ""},
            "third_party_sharing": {"score": 5, "justification": ""},
        },
        "risk_score": 5,
        "verdict": "moderate",
    }
    response = MagicMock(spec=ModelResponse)
    response.model = "test-model"
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


def _services() -> tuple[MagicMock, MagicMock]:
    product = MagicMock()
    product.id = "p1"
    product.name = "Example"
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)
    product_svc.save_product_overview = AsyncMock(return_value=True)
    document_svc = MagicMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=[_core_doc()])
    return product_svc, document_svc


def _patch_aggregation_and_llm():
    aggregation = MagicMock()
    aggregation.conflicts = []
    aggregation.coverage = []
    aggregation_service = MagicMock()
    aggregation_service.build_product_aggregation = AsyncMock(return_value=aggregation)
    return (
        patch("src.analyser.ProductRollupService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback",
            AsyncMock(return_value=_overview_response()),
        ),
    )


@pytest.mark.asyncio
async def test_overview_fires_heartbeat_at_each_sub_step():
    product_svc, document_svc = _services()
    pings = 0

    async def on_progress() -> None:
        nonlocal pings
        pings += 1

    agg_patch, llm_patch = _patch_aggregation_and_llm()
    with agg_patch, llm_patch:
        await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
            on_progress=on_progress,
        )

    # One ping before the rollup build and one before the LLM synthesis — the two
    # spans that can each run long enough to stall an otherwise-healthy job.
    assert pings == 2


@pytest.mark.asyncio
async def test_overview_none_callback_is_noop():
    """A None callback leaves generate_product_overview behaving exactly as before."""
    product_svc, document_svc = _services()

    agg_patch, llm_patch = _patch_aggregation_and_llm()
    with agg_patch, llm_patch:
        result = await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
            on_progress=None,
        )

    assert result.verdict == "moderate"
    product_svc.save_product_overview.assert_awaited_once()
