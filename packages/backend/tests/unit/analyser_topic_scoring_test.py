import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

import src.analyser as analyser_module
from src.analyser import generate_product_overview
from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores
from src.models.finding import AggregatedFinding, Aggregation


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
        risk_score=4,
        verdict="moderate",
        keypoints=[],
        critical_clauses=[],
    )
    return Document(
        id="doc_1",
        title="Privacy Policy",
        url="https://example.com/privacy",
        product_id="p1",
        doc_type="privacy_policy",  # type: ignore[arg-type]
        markdown="",
        text="",
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


def _aggregation() -> Aggregation:
    return Aggregation(
        product_id="p1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="data_sale",
                value="sells_data: yes",
                documents=["doc_1"],
                evidence=[],
            )
        ],
        coverage=[],
        conflicts=[],
    )


@pytest.mark.asyncio
async def test_generate_product_overview_llm_call_is_temperature_zero() -> None:
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.rebuild_findings_for_product = AsyncMock(return_value=None)
    aggregation_service.build_product_aggregation = AsyncMock(return_value=_aggregation())
    llm_mock = AsyncMock(return_value=_overview_response())

    with (
        patch("src.analyser.AggregationService", return_value=aggregation_service),
        patch("src.analyser.acompletion_with_fallback", llm_mock),
    ):
        await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    assert llm_mock.await_args.kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_generate_product_overview_uses_topic_scoring_when_flag_enabled(monkeypatch) -> None:
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.rebuild_findings_for_product = AsyncMock(return_value=None)
    aggregation_service.build_product_aggregation = AsyncMock(return_value=_aggregation())

    monkeypatch.setattr(analyser_module.config.features, "topic_stance_scoring", True)

    with (
        patch("src.analyser.AggregationService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback", AsyncMock(return_value=_overview_response())
        ),
        patch("src.analyser.compose_product_risk_from_topics", return_value=7),
        patch("src.analyser._weighted_product_risk_score", return_value=2),
    ):
        result = await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    assert result.risk_score == 7
    assert result.topic_stances


@pytest.mark.asyncio
async def test_generate_product_overview_uses_legacy_scoring_when_flag_disabled(
    monkeypatch,
) -> None:
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.rebuild_findings_for_product = AsyncMock(return_value=None)
    aggregation_service.build_product_aggregation = AsyncMock(return_value=_aggregation())

    monkeypatch.setattr(analyser_module.config.features, "topic_stance_scoring", False)

    with (
        patch("src.analyser.AggregationService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback", AsyncMock(return_value=_overview_response())
        ),
        patch("src.analyser.compose_product_risk_from_topics", return_value=7),
        patch("src.analyser._weighted_product_risk_score", return_value=2),
    ):
        result = await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    assert result.risk_score == 2
