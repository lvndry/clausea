from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores
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
    db.product_overviews = AsyncMock()
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
        visible_to_tiers=[UserTier.FREE, UserTier.BUSINESS, UserTier.ENTERPRISE],
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

    overview = await product_service.get_product_overview(mock_db, "test-product")
    assert overview is not None
    assert overview.product_slug == "test-product"
    assert overview.risk_score == 5
    mock_product_repo.get_product_overview.assert_called_once_with(mock_db, "test-product")


@pytest.mark.asyncio
async def test_get_product_analysis(
    product_service: ProductService,
    mock_product_repo: MagicMock,
    mock_document_repo: MagicMock,
    mock_db: MagicMock,
) -> None:
    # Mock overview payload (stored in product_overviews)
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

    # Mock documents
    mock_doc = Document(
        id="doc1",
        title="Privacy Policy",
        doc_type="privacy_policy",
        url="https://test.com/privacy",
        product_id="123",
        markdown="# Privacy",
        text="Privacy",
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
    mock_document_repo.find_by_product_id.return_value = [mock_doc]

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
        text="Privacy",
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
    mock_document_repo.find_by_product_id.return_value = [mock_doc]

    documents = await product_service.get_product_documents(mock_db, "test-product")
    assert len(documents) == 1
    assert documents[0].id == "doc1"
    assert documents[0].summary == "JSON SUMMARY"
    mock_document_repo.find_by_product_id.assert_called_once_with(mock_db, "123")
