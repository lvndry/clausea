from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.product_preview_usage import (
    ANONYMOUS_LIMIT,
    ProductPreviewUsageService,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update = AsyncMock()
    collection.find_one = AsyncMock()
    collection.update_one = AsyncMock()
    db.product_preview_usage = collection
    db.__getitem__ = MagicMock(return_value=collection)
    return db


@pytest.mark.asyncio
async def test_allows_first_use_with_token(mock_db):
    mock_db.product_preview_usage.find_one.side_effect = [None]
    mock_db.product_preview_usage.find_one_and_update.return_value = {
        "token": "uuid-1",
        "count": 1,
    }
    svc = ProductPreviewUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is True
    assert count == 1


@pytest.mark.asyncio
async def test_allows_up_to_limit(mock_db):
    with patch.object(ProductPreviewUsageService, "_current_month_key", return_value="2026-06"):
        mock_db.product_preview_usage.find_one.side_effect = [
            {"token": "uuid-1", "count": ANONYMOUS_LIMIT - 1, "month_key": "2026-06"},
        ]
        mock_db.product_preview_usage.find_one_and_update.return_value = {
            "token": "uuid-1",
            "count": ANONYMOUS_LIMIT,
            "month_key": "2026-06",
        }
        svc = ProductPreviewUsageService()
        allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
        assert allowed is True
        assert count == ANONYMOUS_LIMIT


@pytest.mark.asyncio
async def test_blocks_over_limit(mock_db):
    with patch.object(ProductPreviewUsageService, "_current_month_key", return_value="2026-06"):
        mock_db.product_preview_usage.find_one.return_value = {
            "token": "uuid-1",
            "count": ANONYMOUS_LIMIT,
            "month_key": "2026-06",
        }
        svc = ProductPreviewUsageService()
        allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
        assert allowed is False
        assert count == ANONYMOUS_LIMIT


@pytest.mark.asyncio
async def test_resets_count_on_new_month(mock_db):
    with patch.object(ProductPreviewUsageService, "_current_month_key", return_value="2026-07"):
        mock_db.product_preview_usage.find_one.side_effect = [
            {"token": "uuid-1", "count": ANONYMOUS_LIMIT, "month_key": "2026-06"},
        ]
        mock_db.product_preview_usage.find_one_and_update.return_value = {
            "token": "uuid-1",
            "count": 1,
            "month_key": "2026-07",
        }
        svc = ProductPreviewUsageService()
        allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")

    assert allowed is True
    assert count == 1
    mock_db.product_preview_usage.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_different_tokens_are_independent_on_same_ip(mock_db):
    mock_db.product_preview_usage.find_one.side_effect = [None, None]
    mock_db.product_preview_usage.find_one_and_update.return_value = {
        "token": "uuid-A",
        "count": 1,
    }
    svc = ProductPreviewUsageService()
    allowed_a, _ = await svc.check_and_increment(mock_db, token="uuid-A", ip="5.5.5.5")
    allowed_b, _ = await svc.check_and_increment(mock_db, token="uuid-B", ip="5.5.5.5")
    assert allowed_a is True
    assert allowed_b is True


@pytest.mark.asyncio
async def test_ip_fallback_when_no_token(mock_db):
    mock_db.product_preview_usage.find_one.side_effect = [None]
    mock_db.product_preview_usage.find_one_and_update.return_value = {
        "ip": "9.9.9.9",
        "count": 1,
    }
    svc = ProductPreviewUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token=None, ip="9.9.9.9")
    assert allowed is True
    assert count == 1


@pytest.mark.asyncio
async def test_check_without_increment_allows_when_under_limit(mock_db):
    with patch.object(ProductPreviewUsageService, "_current_month_key", return_value="2026-06"):
        mock_db.product_preview_usage.find_one.return_value = {
            "token": "uuid-1",
            "count": 2,
            "month_key": "2026-06",
        }
        svc = ProductPreviewUsageService()
        allowed, count = await svc.check_and_increment(
            mock_db, token="uuid-1", ip="1.2.3.4", increment=False
        )
        assert allowed is True
        assert count == 2


@pytest.mark.asyncio
async def test_check_without_increment_blocks_when_at_limit(mock_db):
    with patch.object(ProductPreviewUsageService, "_current_month_key", return_value="2026-06"):
        mock_db.product_preview_usage.find_one.return_value = {
            "token": "uuid-1",
            "count": ANONYMOUS_LIMIT,
            "month_key": "2026-06",
        }
        svc = ProductPreviewUsageService()
        allowed, count = await svc.check_and_increment(
            mock_db, token="uuid-1", ip="1.2.3.4", increment=False
        )
        assert allowed is False
        assert count == ANONYMOUS_LIMIT


@pytest.mark.asyncio
async def test_check_without_increment_resets_on_new_month(mock_db):
    with patch.object(ProductPreviewUsageService, "_current_month_key", return_value="2026-07"):
        mock_db.product_preview_usage.find_one.return_value = {
            "token": "uuid-1",
            "count": ANONYMOUS_LIMIT,
            "month_key": "2026-06",
        }
        svc = ProductPreviewUsageService()
        allowed, count = await svc.check_and_increment(
            mock_db, token="uuid-1", ip="1.2.3.4", increment=False
        )
        assert allowed is True
        assert count == 0
