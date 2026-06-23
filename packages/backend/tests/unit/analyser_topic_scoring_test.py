import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

from src.analyser import generate_product_overview
from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores, EvidenceSpan
from src.models.finding import AggregatedFinding, HydratedRollup


def _core_doc() -> Document:
    analysis = DocumentAnalysis(
        summary="x",
        scores={
            "transparency": DocumentAnalysisScores(grade="C", justification=""),
            "data_collection_scope": DocumentAnalysisScores(grade="C", justification=""),
            "user_control": DocumentAnalysisScores(grade="C", justification=""),
            "third_party_sharing": DocumentAnalysisScores(grade="C", justification=""),
            "data_retention_score": DocumentAnalysisScores(grade="C", justification=""),
            "security_score": DocumentAnalysisScores(grade="C", justification=""),
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
        analysis=analysis,
    )


def _overview_response() -> ModelResponse:
    payload = {
        "summary": "ok",
        "grade": "C",
        "grade_justification": "Mixed practices across documents.",
        "scores": {
            "transparency": {"grade": "C", "justification": ""},
            "data_collection_scope": {"grade": "C", "justification": ""},
            "user_control": {"grade": "C", "justification": ""},
            "third_party_sharing": {"grade": "C", "justification": ""},
        },
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


def _aggregation() -> HydratedRollup:
    return HydratedRollup(
        product_id="p1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="data_sale",
                value="sells_data: yes",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We may sell data to advertising partners.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We may sell personal information to advertising partners.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="Sale of personal data may occur as described in this privacy policy.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="Users can opt out in account settings.",
                    ),
                ],
            )
        ],
        coverage=[],
        conflicts=[],
    )


@pytest.mark.asyncio
async def test_generate_product_overview_llm_call_is_temperature_zero() -> None:
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.build_product_aggregation = AsyncMock(return_value=_aggregation())
    llm_mock = AsyncMock(return_value=_overview_response())

    with (
        patch("src.analyser.ProductRollupService", return_value=aggregation_service),
        patch("src.analyser.acompletion_with_fallback", llm_mock),
    ):
        await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    assert llm_mock.await_args is not None
    assert llm_mock.await_args.kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_generate_product_overview_uses_llm_grades() -> None:
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.build_product_aggregation = AsyncMock(return_value=_aggregation())

    with (
        patch("src.analyser.ProductRollupService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback", AsyncMock(return_value=_overview_response())
        ),
        patch("src.analyser.compose_product_risk_from_topics", return_value=9),
        patch("src.analyser._weighted_product_risk_score", return_value=2),
    ):
        result = await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    # LLM grade C → risk 5 after reconciliation.
    assert result.grade == "C"
    assert result.risk_score == 5
    assert result.topic_stances
    assert result.topic_stances[0].rationale_key == "topic.findings_summary"
    assert result.topic_stances[0].headline_claim is not None
    assert result.topic_stances[0].supporting_citations
    assert len(result.topic_stances[0].supporting_citations) == 4
    quotes = {citation.quote for citation in result.topic_stances[0].supporting_citations}
    assert "We may sell data to advertising partners." in quotes
    assert "Users can opt out in account settings." in quotes
    assert result.topic_stances[0].why_it_matters is not None
    assert result.topic_stances[0].recommended_action is not None
