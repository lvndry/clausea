from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.models.document import CoverageItem, DocumentSummary, EvidenceSpan
from src.models.product import Product
from src.models.product_intelligence import ProductIntelligence, ProductRollup, RollupItem
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


def _intelligence() -> ProductIntelligence:
    return ProductIntelligence(
        product_id="product_1",
        product_slug="example",
        rollup=ProductRollup(
            coverage=[CoverageItem(category="data_collection", status="found")],
            items=[
                RollupItem(
                    category="data_collection",
                    value="Email",
                    document_ids=["doc_1"],
                )
            ],
        ),
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
async def test_get_product_topics_425_when_rollup_missing() -> None:
    service = MagicMock()
    service.get_product_by_slug = AsyncMock(return_value=_product())

    with (
        patch(
            "src.routes.products.ProductIntelligenceRepository.get_topic_report_cached",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.routes.products.ProductIntelligenceRepository.get_rollup_for_topics",
            AsyncMock(return_value=None),
        ),
    ):
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

    from src.models.document import Document, DocumentExtraction, ExtractedDataItem

    doc = Document(
        id="doc_1",
        product_id="product_1",
        url="https://example.com/privacy",
        title="Privacy Policy",
        doc_type="privacy_policy",
        markdown="We collect your email.",
        extraction=DocumentExtraction(
            source_content_hash="abc",
            data_collected=[
                ExtractedDataItem(
                    data_type="Email",
                    evidence=[
                        EvidenceSpan(
                            document_id="doc_1",
                            quote="We collect your email.",
                            url="https://example.com/privacy",
                        )
                    ],
                )
            ],
        ),
    )

    with (
        patch(
            "src.routes.products.ProductIntelligenceRepository.get_topic_report_cached",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.routes.products.ProductIntelligenceRepository.get_rollup_for_topics",
            AsyncMock(return_value=_intelligence()),
        ),
        patch(
            "src.routes.products.DocumentRepository.find_by_ids_with_extraction",
            AsyncMock(return_value=[doc]),
        ),
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
