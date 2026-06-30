from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.document import (
    ComplianceBreakdown,
    ConsumerExplainer,
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentExtraction,
    EvidenceSpan,
    ExtractedDataItem,
)
from src.models.product import Product
from src.models.user import UserTier
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_repository import ProductRepository
from src.services.product_service import ProductService


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    # Mocking collections for legacy or direct access tests if any remain
    db.products = AsyncMock()
    db.documents = MagicMock()
    db.documents.find_one = AsyncMock()
    db.documents.insert_one = AsyncMock()
    db.documents.update_one = AsyncMock()
    db.documents.delete_one = AsyncMock()
    db.documents.find = MagicMock()
    return db


@pytest.fixture
def mock_product_repo() -> MagicMock:
    return MagicMock(spec=ProductRepository)


@pytest.fixture
def mock_document_repo() -> MagicMock:
    return MagicMock(spec=DocumentRepository)


@pytest.fixture
def product_service(mock_product_repo: MagicMock, mock_document_repo: MagicMock) -> ProductService:
    return ProductService(product_repo=mock_product_repo, document_repo=mock_document_repo)


@pytest.mark.asyncio
async def test_get_product_by_slug(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product = Product(
        id="123",
        name="Test Product",
        slug="test-product",
        company_name="Test Company",
        domains=["test.com"],
        categories=["tech"],
        crawl_base_urls=["https://test.com"],
        logo=None,
        visible_to_tiers=[UserTier.FREE, UserTier.PRO],
    )
    mock_product_repo.find_by_slug.return_value = mock_product

    product = await product_service.get_product_by_slug(mock_db, "test-product")
    assert product is not None
    assert product.slug == "test-product"
    assert product.id == "123"
    mock_product_repo.find_by_slug.assert_called_once_with(mock_db, "test-product")


@pytest.mark.asyncio
async def test_get_product_overview(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product_repo.get_product_overview.return_value = {
        "overview": {
            "summary": "Test summary",
            "scores": {
                "transparency": {"score": 8, "justification": "Good"},
                "data_collection_scope": {"score": 5, "justification": "Medium"},
                "user_control": {"score": 7, "justification": "Okay"},
                "third_party_sharing": {"score": 3, "justification": "Bad"},
            },
            "risk_score": 5,
            "grade": "C",
            "verdict": "moderate",
            "keypoints": ["Point 1"],
            "data_collected": ["Email"],
            "data_purposes": ["Ads"],
            "your_rights": ["Access"],
            "dangers": ["Tracking"],
            "benefits": ["Free"],
            "recommended_actions": ["Opt out"],
        }
    }
    mock_product_repo.find_by_slug.return_value = None
    mock_product_repo.get_document_counts.return_value = {"total": 1, "analyzed": 1}
    mock_product_repo.get_document_types.return_value = {"privacy_policy": 1}
    mock_product_repo.get_product_compliance = AsyncMock(return_value=None)

    overview = await product_service.get_product_overview(mock_db, "test-product")
    assert overview is not None
    assert overview.product_slug == "test-product"
    assert overview.grade == "C"
    mock_product_repo.get_product_overview.assert_called_once_with(mock_db, "test-product")


@pytest.mark.asyncio
async def test_get_product_overview_includes_compliance_breakdown(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product_repo.get_product_overview.return_value = {
        "overview": {
            "summary": "Test summary",
            "scores": {
                "transparency": {"score": 8, "justification": "Good"},
                "data_collection_scope": {"score": 5, "justification": "Medium"},
                "user_control": {"score": 7, "justification": "Okay"},
                "third_party_sharing": {"score": 3, "justification": "Bad"},
            },
            "risk_score": 5,
            "verdict": "moderate",
            "compliance_status": {"GDPR": 7},
        }
    }
    mock_product_repo.find_by_slug.return_value = None
    mock_product_repo.get_document_counts.return_value = {"total": 1, "analyzed": 1}
    mock_product_repo.get_document_types.return_value = {"privacy_policy": 1}
    mock_product_repo.get_product_compliance = AsyncMock(
        return_value={
            "GDPR": {
                "score": 7,
                "status": "Partially Compliant",
                "assessment_notes": "Privacy Policy describes EU data subject rights.",
                "strengths": ["Lawful basis for processing stated"],
                "gaps": ["Retention periods not specified"],
            }
        }
    )

    overview = await product_service.get_product_overview(mock_db, "test-product")

    assert overview is not None
    assert overview.compliance is not None
    assert "GDPR" in overview.compliance
    gdpr = overview.compliance["GDPR"]
    assert isinstance(gdpr, ComplianceBreakdown)
    assert gdpr.assessment_notes == "Privacy Policy describes EU data subject rights."
    assert gdpr.strengths == ["Lawful basis for processing stated"]
    assert gdpr.gaps == ["Retention periods not specified"]
    assert gdpr.has_rationale() is True


@pytest.mark.asyncio
async def test_get_product_explainer_uses_canonical_overview_grade(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product_repo.get_product_explainer = AsyncMock(
        return_value={"product_slug": "test-product", "headline": "h", "grade": "D"}
    )
    mock_product_repo.update_product_explainer_grade = AsyncMock()
    mock_product_repo.find_by_slug = AsyncMock(return_value=None)

    with patch(
        "src.services.product_service.ProductIntelligenceRepository.get_overview_grade",
        AsyncMock(return_value="C"),
    ):
        explainer = await product_service.get_product_explainer(mock_db, "test-product")

    assert explainer is not None
    assert explainer["grade"] == "C"
    mock_product_repo.update_product_explainer_grade.assert_awaited_once_with(
        mock_db,
        "test-product",
        "C",
        grade_reason="Moderate risk: notable concerns around data sharing, limited user controls, or vague language.",
    )


@pytest.mark.asyncio
async def test_get_product_explainer_keeps_grade_when_overview_grade_missing(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product_repo.get_product_explainer = AsyncMock(
        return_value={"product_slug": "test-product", "headline": "h", "grade": "B"}
    )
    mock_product_repo.update_product_explainer_grade = AsyncMock()
    mock_product_repo.find_by_slug = AsyncMock(return_value=None)

    with patch(
        "src.services.product_service.ProductIntelligenceRepository.get_overview_grade",
        AsyncMock(return_value=None),
    ):
        explainer = await product_service.get_product_explainer(mock_db, "test-product")

    assert explainer is not None
    assert explainer["grade"] == "B"
    mock_product_repo.update_product_explainer_grade.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_product_explainer_overrides_grade_with_canonical_overview(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product_repo.save_product_explainer = AsyncMock(return_value=True)

    with patch(
        "src.services.product_service.ProductIntelligenceRepository.get_overview_grade",
        AsyncMock(return_value="C"),
    ):
        saved = await product_service.save_product_explainer(
            mock_db,
            "test-product",
            ConsumerExplainer(headline="h", grade="D"),
        )

    assert saved is True
    mock_product_repo.save_product_explainer.assert_awaited_once()
    saved_explainer = mock_product_repo.save_product_explainer.await_args.args[2]
    assert isinstance(saved_explainer, ConsumerExplainer)
    assert saved_explainer.grade == "C"
    assert (
        saved_explainer.grade_reason
        == "Moderate risk: notable concerns around data sharing, limited user controls, or vague language."
    )


@pytest.mark.asyncio
async def test_get_product_explainer_backfills_missing_source_citations(
    product_service: ProductService,
    mock_product_repo: MagicMock,
    mock_document_repo: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_product_repo.get_product_explainer = AsyncMock(
        return_value={
            "headline": "h",
            "grade": "C",
            "watch_out_for": [
                {
                    "title": "Sells data",
                    "severity": "high",
                    "quote": "sell your personal information",
                    "quote_status": "from_extraction",
                }
            ],
        }
    )
    mock_product_repo.find_by_slug = AsyncMock(
        return_value=Product(
            id="prod-1",
            name="Test Product",
            slug="test-product",
            company_name="Test Company",
            domains=["test.com"],
            categories=["tech"],
            crawl_base_urls=["https://test.com"],
            logo=None,
            visible_to_tiers=[UserTier.FREE, UserTier.PRO],
        )
    )
    extraction = DocumentExtraction(
        source_content_hash="hash-1",
        data_collected=[
            ExtractedDataItem(
                data_type="data_0",
                evidence=[
                    EvidenceSpan(
                        document_id="doc-1",
                        url="https://example.com/privacy",
                        quote="We may sell your personal information to advertisers.",
                        start_char=0,
                        end_char=55,
                        verified=True,
                    )
                ],
            )
        ],
    )
    mock_document_repo.find_by_product_id_full = AsyncMock(
        return_value=[
            Document(
                id="doc-1",
                url="https://example.com/privacy",
                product_id="prod-1",
                doc_type="privacy_policy",
                title="Privacy Policy",
                markdown="# Privacy",
                extraction=extraction,
                created_at=datetime(2026, 1, 1),
            )
        ]
    )

    with patch(
        "src.services.product_service.ProductIntelligenceRepository.get_overview_grade",
        AsyncMock(return_value=None),
    ):
        explainer = await product_service.get_product_explainer(mock_db, "test-product")

    assert explainer is not None
    citation = explainer["watch_out_for"][0]["citation"]
    assert citation is not None
    assert citation["document_title"] == "Privacy Policy"
    assert citation["document_url"] == "https://example.com/privacy"


@pytest.mark.asyncio
async def test_get_product_analysis(
    product_service: ProductService,
    mock_product_repo: MagicMock,
    mock_document_repo: MagicMock,
    mock_db: MagicMock,
) -> None:
    # Mock overview payload (stored in product_intelligence)
    mock_product_repo.get_product_overview.return_value = {
        "overview": {
            "summary": "Test summary",
            "scores": {
                "transparency": {"score": 8, "justification": "Good"},
                "data_collection_scope": {"score": 5, "justification": "Medium"},
                "user_control": {"score": 7, "justification": "Okay"},
                "third_party_sharing": {"score": 3, "justification": "Bad"},
            },
            "risk_score": 5,
            "verdict": "moderate",
            "keypoints": ["Point 1"],
        }
    }

    # Mock product
    mock_product = Product(
        id="123",
        name="Test Product",
        company_name="Test Company",
        slug="test-product",
        domains=["test.com"],
        categories=["tech"],
        crawl_base_urls=["https://test.com"],
        visible_to_tiers=[UserTier.FREE],
    )
    mock_product_repo.find_by_slug.return_value = mock_product
    mock_product_repo.get_product_compliance.return_value = None

    # Mock documents
    mock_doc = Document(
        id="doc1",
        title="Privacy Policy",
        doc_type="privacy_policy",
        url="https://test.com/privacy",
        product_id="123",
        markdown="# Privacy",
        analysis=DocumentAnalysis(
            summary='{"summary": "CLEANED SUMMARY", "points": []}',  # Should be cleaned by validator
            scores={
                "transparency": DocumentAnalysisScores(score=8, justification="Good"),
                "data_collection_scope": DocumentAnalysisScores(score=5, justification="Medium"),
                "user_control": DocumentAnalysisScores(score=7, justification="Okay"),
                "third_party_sharing": DocumentAnalysisScores(score=3, justification="Bad"),
                "data_retention_score": DocumentAnalysisScores(score=5, justification="Unknown"),
                "security_score": DocumentAnalysisScores(score=9, justification="Strong"),
            },
            risk_score=5,
            verdict="moderate",
            keypoints=["Key Point"],
        ),
    )
    mock_document_repo.find_by_product_id_full.return_value = [mock_doc]

    analysis = await product_service.get_product_analysis(mock_db, "test-product")
    assert analysis is not None
    assert analysis.overview.product_slug == "test-product"
    assert len(analysis.documents) == 1
    assert analysis.documents[0].id == "doc1"
    assert analysis.documents[0].summary == "CLEANED SUMMARY"


@pytest.mark.asyncio
async def test_get_product_documents(
    product_service: ProductService,
    mock_product_repo: MagicMock,
    mock_document_repo: MagicMock,
    mock_db: MagicMock,
) -> None:
    # Mock product
    mock_product = Product(
        id="123",
        name="Test Product",
        company_name="Test Company",
        slug="test-product",
        domains=["test.com"],
        categories=["tech"],
        crawl_base_urls=["https://test.com"],
        visible_to_tiers=[UserTier.FREE],
    )
    mock_product_repo.find_by_slug.return_value = mock_product

    # Mock doc with JSON summary
    mock_doc = Document(
        id="doc1",
        title="Privacy Policy",
        doc_type="privacy_policy",
        url="https://test.com/privacy",
        product_id="123",
        markdown="# Privacy",
        analysis=DocumentAnalysis(
            summary='{"summary": "JSON SUMMARY", "other": "data"}',
            scores={
                "transparency": DocumentAnalysisScores(score=8, justification="Good"),
                "data_collection_scope": DocumentAnalysisScores(score=5, justification="Medium"),
                "user_control": DocumentAnalysisScores(score=7, justification="Okay"),
                "third_party_sharing": DocumentAnalysisScores(score=3, justification="Bad"),
                "data_retention_score": DocumentAnalysisScores(score=5, justification="Unknown"),
                "security_score": DocumentAnalysisScores(score=9, justification="Strong"),
            },
            risk_score=5,
            verdict="moderate",
            keypoints=["Point A"],
        ),
    )
    mock_document_repo.find_by_product_id_with_analysis.return_value = [mock_doc]

    documents = await product_service.get_product_documents(mock_db, "test-product")
    assert len(documents) == 1
    assert documents[0].id == "doc1"
    assert documents[0].summary == "JSON SUMMARY"
    mock_document_repo.find_by_product_id_with_analysis.assert_called_once_with(mock_db, "123")


@pytest.mark.asyncio
async def test_count_analyzed_products(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    mock_product_repo.count_products_with_overview = AsyncMock(return_value=7)

    count = await product_service.count_analyzed_products(mock_db)

    assert count == 7
    mock_product_repo.count_products_with_overview.assert_awaited_once_with(mock_db)


@pytest.mark.asyncio
async def test_list_analyzed_products_for_sitemap(
    product_service: ProductService, mock_product_repo: MagicMock, mock_db: MagicMock
) -> None:
    rows = [{"product_slug": "notion", "updated_at": None}]
    mock_product_repo.list_analyzed_overviews = AsyncMock(return_value=rows)

    result = await product_service.list_analyzed_products_for_sitemap(mock_db)

    assert result == rows
    mock_product_repo.list_analyzed_overviews.assert_awaited_once_with(mock_db)
