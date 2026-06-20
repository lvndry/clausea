from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.tier_deps import check_usage_limit, require_pro
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
    doc = _make_document("other")
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
        doc_type="other",
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


def _mock_request(user_id: str | None) -> MagicMock:
    request = MagicMock()
    if user_id is None:
        request.state.user = None
    else:
        request.state.user = {"user_id": user_id}
    return request


@pytest.mark.asyncio
async def test_require_pro_rejects_unauthenticated() -> None:
    request = _mock_request(None)
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await require_pro(request=request, db=db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_check_usage_limit_allows_unauthenticated_non_product_route() -> None:
    request = _mock_request(None)
    request.method = "GET"
    request.url.path = "/users/tier-limits"
    db = AsyncMock()
    result = await check_usage_limit(request=request, db=db)
    assert result is None


@pytest.mark.asyncio
async def test_check_usage_limit_allows_anonymous_product_preview() -> None:
    request = _mock_request(None)
    request.method = "GET"
    request.url.path = "/products/acme/overview"
    request.headers = {"X-Preview-Token": "preview-token-1"}
    request.client = MagicMock(host="1.2.3.4")
    db = AsyncMock()

    with patch("src.core.tier_deps._preview_usage_svc") as mock_preview_svc:
        mock_preview_svc.check_and_increment = AsyncMock(return_value=(True, 1))
        result = await check_usage_limit(request=request, db=db)

    assert result is None
    mock_preview_svc.check_and_increment.assert_awaited_once_with(
        db,
        token="preview-token-1",
        ip="1.2.3.4",
        increment=True,
    )


@pytest.mark.asyncio
async def test_check_usage_limit_blocks_anonymous_product_preview() -> None:
    request = _mock_request(None)
    request.method = "GET"
    request.url.path = "/products/acme/overview"
    request.headers = {}
    request.client = MagicMock(host="9.9.9.9")
    db = AsyncMock()

    with patch("src.core.tier_deps._preview_usage_svc") as mock_preview_svc:
        mock_preview_svc.check_and_increment = AsyncMock(return_value=(False, 5))
        with pytest.raises(HTTPException) as exc_info:
            await check_usage_limit(request=request, db=db)

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_check_usage_limit_skips_crawler_user_agents() -> None:
    request = _mock_request(None)
    request.method = "GET"
    request.url.path = "/products/acme/overview"
    request.headers = {"user-agent": "Twitterbot/1.0"}
    db = AsyncMock()

    with patch("src.core.tier_deps._preview_usage_svc") as mock_preview_svc:
        result = await check_usage_limit(request=request, db=db)

    assert result is None
    mock_preview_svc.check_and_increment.assert_not_called()


@pytest.mark.asyncio
async def test_check_usage_limit_checks_without_increment_on_documents() -> None:
    request = _mock_request(None)
    request.method = "GET"
    request.url.path = "/products/acme/documents"
    request.headers = {"X-Preview-Token": "preview-token-1"}
    request.client = MagicMock(host="1.2.3.4")
    db = AsyncMock()

    with patch("src.core.tier_deps._preview_usage_svc") as mock_preview_svc:
        mock_preview_svc.check_and_increment = AsyncMock(return_value=(True, 3))
        result = await check_usage_limit(request=request, db=db)

    assert result is None
    mock_preview_svc.check_and_increment.assert_awaited_once_with(
        db,
        token="preview-token-1",
        ip="1.2.3.4",
        increment=False,
    )


@pytest.mark.asyncio
async def test_check_usage_limit_enforces_signed_in_monthly_limit() -> None:
    request = _mock_request("free-user-123")
    request.method = "GET"
    request.url.path = "/products/acme/overview"
    db = AsyncMock()

    with patch(
        "src.core.tier_deps.UsageService.check_usage_limit",
        new=AsyncMock(return_value=(False, {})),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await check_usage_limit(request=request, db=db)

    assert exc_info.value.status_code == 429
    assert "Monthly usage limit" in exc_info.value.detail
