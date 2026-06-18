from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.models.document import CoverageItem, DocumentSummary, EvidenceSpan
from src.models.finding import AggregatedFinding, Aggregation
from src.models.product import Product
from src.models.user import UserTier
from src.routes.products import get_product_topics


def _product() -> Product:
    return Product(
        id="product_1",
        name="Example",
        slug="example",
        domains=["example.com"],
        crawl_base_urls=["https://example.com"],
        visible_to_tiers=[UserTier.FREE],
    )


def _aggregation() -> Aggregation:
    return Aggregation(
        product_id="product_1",
        product_slug="example",
        coverage=[CoverageItem(category="data_collection", status="found")],
        findings=[
            AggregatedFinding(
                category="data_collection",
                value="Email",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We collect your email.",
                    )
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_get_product_topics_404_when_product_missing() -> None:
    service = MagicMock()
    service.get_product_by_slug = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_product_topics(
            slug="missing",
            _request=MagicMock(),
            _usage=None,
            _increment=None,
            db=MagicMock(),
            service=service,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_product_topics_425_when_aggregation_missing() -> None:
    service = MagicMock()
    service.get_product_by_slug = AsyncMock(return_value=_product())

    with patch("src.routes.products.AggregationRepository.get", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_info:
            await get_product_topics(
                slug="example",
                _request=MagicMock(),
                _usage=None,
                _increment=None,
                db=MagicMock(),
                service=service,
            )
    assert exc_info.value.status_code == 425
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "topics_not_ready"


@pytest.mark.asyncio
async def test_get_product_topics_returns_topic_report() -> None:
    service = MagicMock()
    service.get_product_by_slug = AsyncMock(return_value=_product())
    service.get_product_documents = AsyncMock(
        return_value=[
            DocumentSummary(
                id="doc_1",
                title="Privacy Policy",
                doc_type="privacy_policy",
                url="https://example.com/privacy",
            )
        ]
    )

    with patch(
        "src.routes.products.AggregationRepository.get", AsyncMock(return_value=_aggregation())
    ):
        result = await get_product_topics(
            slug="example",
            _request=MagicMock(),
            _usage=None,
            _increment=None,
            db=MagicMock(),
            service=service,
        )

    assert result.product_slug == "example"
    assert len(result.topics) == 1
    topic = result.topics[0]
    assert topic.topic == "data_collection"
    assert topic.status == "found"
    assert topic.findings[0].citations[0].document_title == "Privacy Policy"
