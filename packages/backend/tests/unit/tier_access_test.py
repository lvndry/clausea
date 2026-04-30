from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.models.document import CORE_DOC_TYPES, Document
from src.models.user import UserTier
from src.routes.products import _can_access_document
from src.services.document_service import DocumentService


def _make_document(doc_type: str) -> Document:
    return Document(
        url=f"https://example.com/{doc_type}",
        title=doc_type,
        product_id="prod-1",
        doc_type=doc_type,  # type: ignore[arg-type]
        markdown="text",
        text="text",
    )


def test_core_doc_types_include_gdpr_policy() -> None:
    assert "gdpr_policy" in CORE_DOC_TYPES


def test_assign_tier_relevance_marks_core_docs() -> None:
    doc = _make_document("privacy_policy")
    DocumentService._assign_tier_relevance(doc)
    assert doc.tier_relevance == "core"


def test_assign_tier_relevance_marks_extended_docs() -> None:
    doc = _make_document("unclassified")
    DocumentService._assign_tier_relevance(doc)
    assert doc.tier_relevance == "extended"


def test_can_access_document_for_pro_user() -> None:
    assert _can_access_document(
        tier=UserTier.PRO,
        doc_type="data_processing_agreement",
        tier_relevance="extended",
    )


def test_can_access_document_for_free_user_core_by_type() -> None:
    assert _can_access_document(
        tier=UserTier.FREE,
        doc_type="terms_of_service",
        tier_relevance="extended",
    )


def test_cannot_access_document_for_free_user_extended() -> None:
    assert not _can_access_document(
        tier=UserTier.FREE,
        doc_type="unclassified",
        tier_relevance="extended",
    )


@pytest.mark.asyncio
async def test_product_deep_analysis_blocked_for_free_user() -> None:
    """Product-level deep analysis requires Pro — free users get HTTP 402."""
    from src.core.tier_deps import require_pro

    mock_request = MagicMock()
    mock_request.state.user = {"user_id": "free-user-123"}
    mock_db = AsyncMock()

    mock_user = MagicMock()
    mock_user.tier = UserTier.FREE

    with patch("src.core.tier_deps.create_user_service") as mock_factory:
        mock_svc = AsyncMock()
        mock_svc.get_user_by_id.return_value = mock_user
        mock_factory.return_value = mock_svc

        with pytest.raises(HTTPException) as exc_info:
            await require_pro(request=mock_request, db=mock_db)

    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_product_deep_analysis_allowed_for_pro_user() -> None:
    """Pro users can access the product-level deep analysis."""
    from src.core.tier_deps import require_pro

    mock_request = MagicMock()
    mock_request.state.user = {"user_id": "pro-user-456"}
    mock_db = AsyncMock()

    mock_user = MagicMock()
    mock_user.tier = UserTier.PRO

    with patch("src.core.tier_deps.create_user_service") as mock_factory:
        mock_svc = AsyncMock()
        mock_svc.get_user_by_id.return_value = mock_user
        mock_factory.return_value = mock_svc

        result = await require_pro(request=mock_request, db=mock_db)

    assert result is None  # no exception = access granted
