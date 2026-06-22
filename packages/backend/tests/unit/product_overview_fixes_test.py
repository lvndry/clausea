"""Tests for product_id and headline_claim fixes in product overview pipeline.

Bug 1: product_id was never written to product_overviews documents.
Bug 2: headline_claim was absent from MetaSummary / PRODUCT_OVERVIEW_JSON_SCHEMA
       so it was never populated from the LLM response.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

from src.analyser import generate_product_overview
from src.models.document import (
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    MetaSummary,
    ProductOverview,
)
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_repository import ProductRepository
from src.services.product_service import ProductService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta_summary(**extra: object) -> MetaSummary:
    base = {
        "summary": "Test summary",
        "scores": {
            "transparency": {"score": 5, "justification": "ok"},
            "data_collection_scope": {"score": 5, "justification": "ok"},
            "user_control": {"score": 5, "justification": "ok"},
            "third_party_sharing": {"score": 5, "justification": "ok"},
        },
        "risk_score": 5,
        "verdict": "moderate",
    }
    base.update(extra)
    return MetaSummary.model_validate(base)


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
        analysis=analysis,
    )


def _llm_response(payload: dict) -> ModelResponse:
    response = MagicMock(spec=ModelResponse)
    response.model = "test-model"
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


def _base_llm_payload(**extra: object) -> dict:
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
    payload.update(extra)
    return payload


def _services(product_id: str = "p1") -> tuple[MagicMock, MagicMock]:
    product = MagicMock()
    product.id = product_id
    product.name = "Example"
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)
    product_svc.save_product_overview = AsyncMock(return_value=None)
    document_svc = MagicMock()
    document_svc.get_product_documents_by_slug = AsyncMock(return_value=[_core_doc()])
    return product_svc, document_svc


# ---------------------------------------------------------------------------
# Bug 1: product_id propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_product_overview_passes_product_id_to_save() -> None:
    """generate_product_overview must pass product.id to save_product_overview."""
    product_svc, document_svc = _services(product_id="abc-123")
    aggregation_service = MagicMock()
    aggregation_service.rebuild_findings_for_product = AsyncMock(return_value=None)
    aggregation_service.build_product_aggregation = AsyncMock(
        return_value=MagicMock(
            findings=[],
            coverage=[],
            conflicts=[],
            product_id="abc-123",
            product_slug="example",
        )
    )

    with (
        patch("src.analyser.AggregationService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback",
            AsyncMock(return_value=_llm_response(_base_llm_payload())),
        ),
    ):
        await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    product_svc.save_product_overview.assert_awaited_once()
    _kwargs = product_svc.save_product_overview.call_args.kwargs
    assert _kwargs.get("product_id") == "abc-123", (
        "product_id must be forwarded from product.id to save_product_overview"
    )


@pytest.mark.asyncio
async def test_product_service_passes_product_id_to_repo() -> None:
    """ProductService.save_product_overview must forward product_id to the repo."""
    mock_repo = MagicMock(spec=ProductRepository)
    mock_repo.save_product_overview = AsyncMock(return_value=None)
    svc = ProductService(
        product_repo=mock_repo,
        document_repo=MagicMock(spec=DocumentRepository),
    )
    meta = _make_meta_summary()

    await svc.save_product_overview(
        MagicMock(),
        product_slug="test-slug",
        meta_summary=meta,
        job_id="job-1",
        product_id="prod-xyz",
    )

    mock_repo.save_product_overview.assert_awaited_once()
    _kwargs = mock_repo.save_product_overview.call_args.kwargs
    assert _kwargs.get("product_id") == "prod-xyz"
    assert _kwargs.get("job_id") == "job-1"


@pytest.mark.asyncio
async def test_product_repo_writes_product_id_to_summary_data() -> None:
    """ProductRepository.save_product_overview must write product_id into the upserted doc."""
    from src.repositories.product_repository import ProductRepository as Repo

    mock_db = MagicMock()
    mock_db.product_overviews = MagicMock()
    mock_db.product_overviews.find_one = AsyncMock(return_value=None)
    mock_db.product_overviews.update_one = AsyncMock(
        return_value=MagicMock(matched_count=0, modified_count=0, upserted_id="new")
    )

    history_repo_mock = MagicMock()
    history_repo_mock.save_snapshot = AsyncMock(return_value=None)

    meta = _make_meta_summary()
    repo = Repo()

    with patch(
        "src.repositories.product_repository.ProductOverviewHistoryRepository",
        return_value=history_repo_mock,
    ):
        await repo.save_product_overview(
            mock_db,
            product_slug="test-slug",
            meta_summary=meta,
            product_id="prod-456",
        )

    mock_db.product_overviews.update_one.assert_awaited_once()
    _args, _kwargs = mock_db.product_overviews.update_one.call_args
    upserted_doc = _args[1]["$set"]
    assert upserted_doc.get("product_id") == "prod-456", (
        "product_id must be written into the $set payload"
    )
    assert upserted_doc.get("product_slug") == "test-slug"


@pytest.mark.asyncio
async def test_product_repo_omits_product_id_when_none() -> None:
    """product_id=None must not be written as a null field (avoids overwriting valid data)."""
    from src.repositories.product_repository import ProductRepository as Repo

    mock_db = MagicMock()
    mock_db.product_overviews = MagicMock()
    mock_db.product_overviews.find_one = AsyncMock(return_value=None)
    mock_db.product_overviews.update_one = AsyncMock(
        return_value=MagicMock(matched_count=0, modified_count=0, upserted_id="new")
    )

    history_repo_mock = MagicMock()
    history_repo_mock.save_snapshot = AsyncMock(return_value=None)

    meta = _make_meta_summary()
    repo = Repo()

    with patch(
        "src.repositories.product_repository.ProductOverviewHistoryRepository",
        return_value=history_repo_mock,
    ):
        await repo.save_product_overview(
            mock_db,
            product_slug="test-slug",
            meta_summary=meta,
            product_id=None,
        )

    _args, _ = mock_db.product_overviews.update_one.call_args
    upserted_doc = _args[1]["$set"]
    assert "product_id" not in upserted_doc, "product_id must not be written when it is None"


# ---------------------------------------------------------------------------
# Bug 2: headline_claim propagation
# ---------------------------------------------------------------------------


def test_meta_summary_accepts_headline_claim() -> None:
    """MetaSummary must accept and expose a headline_claim field."""
    meta = _make_meta_summary(headline_claim="Acme sells your data to brokers.")
    assert meta.headline_claim == "Acme sells your data to brokers."


def test_meta_summary_headline_claim_defaults_to_none() -> None:
    """headline_claim must default to None when absent from LLM response."""
    meta = _make_meta_summary()
    assert meta.headline_claim is None


def test_transform_to_overview_maps_headline_claim() -> None:
    """_transform_to_overview must copy headline_claim from MetaSummary to ProductOverview."""
    mock_repo = MagicMock(spec=ProductRepository)
    svc = ProductService(
        product_repo=mock_repo,
        document_repo=MagicMock(spec=DocumentRepository),
    )
    meta = _make_meta_summary(headline_claim="Tracks users across the web.")
    overview: ProductOverview = svc._transform_to_overview(meta, "test-slug")
    assert overview.headline_claim == "Tracks users across the web."


def test_transform_to_overview_headline_claim_none_when_missing() -> None:
    """ProductOverview.headline_claim must be None when MetaSummary has no headline_claim."""
    mock_repo = MagicMock(spec=ProductRepository)
    svc = ProductService(
        product_repo=mock_repo,
        document_repo=MagicMock(spec=DocumentRepository),
    )
    meta = _make_meta_summary()
    overview: ProductOverview = svc._transform_to_overview(meta, "test-slug")
    assert overview.headline_claim is None


@pytest.mark.asyncio
async def test_generate_product_overview_parses_headline_claim_from_llm() -> None:
    """generate_product_overview must parse headline_claim from the LLM JSON response."""
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.rebuild_findings_for_product = AsyncMock(return_value=None)
    aggregation_service.build_product_aggregation = AsyncMock(
        return_value=MagicMock(
            findings=[],
            coverage=[],
            conflicts=[],
            product_id="p1",
            product_slug="example",
        )
    )
    payload = _base_llm_payload(
        headline_claim="Example collects browsing data for targeted advertising."
    )

    with (
        patch("src.analyser.AggregationService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback",
            AsyncMock(return_value=_llm_response(payload)),
        ),
    ):
        result = await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    assert result.headline_claim == "Example collects browsing data for targeted advertising.", (
        "headline_claim from LLM JSON must be carried through to the returned MetaSummary"
    )


@pytest.mark.asyncio
async def test_generate_product_overview_headline_claim_none_when_llm_omits_it() -> None:
    """headline_claim must be None when the LLM does not return it."""
    product_svc, document_svc = _services()
    aggregation_service = MagicMock()
    aggregation_service.rebuild_findings_for_product = AsyncMock(return_value=None)
    aggregation_service.build_product_aggregation = AsyncMock(
        return_value=MagicMock(
            findings=[],
            coverage=[],
            conflicts=[],
            product_id="p1",
            product_slug="example",
        )
    )

    with (
        patch("src.analyser.AggregationService", return_value=aggregation_service),
        patch(
            "src.analyser.acompletion_with_fallback",
            AsyncMock(return_value=_llm_response(_base_llm_payload())),
        ),
    ):
        result = await generate_product_overview(
            MagicMock(),
            "example",
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )

    assert result.headline_claim is None
