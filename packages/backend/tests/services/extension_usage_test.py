from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.extension_usage import ExtensionUsageService

ANONYMOUS_LIMIT = 3


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.find_one = AsyncMock()
    collection.update_one = AsyncMock()
    # Support both attribute and dict access
    db.extension_anonymous_usage = collection
    db.__getitem__ = MagicMock(return_value=collection)
    return db


@pytest.mark.asyncio
async def test_allows_first_use(mock_db):
    mock_db.extension_anonymous_usage.find_one.return_value = None
    svc = ExtensionUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is True
    assert count == 1


@pytest.mark.asyncio
async def test_allows_up_to_limit(mock_db):
    mock_db.extension_anonymous_usage.find_one.return_value = {"token": "uuid-1", "count": 2}
    svc = ExtensionUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is True
    assert count == 3


@pytest.mark.asyncio
async def test_blocks_over_limit(mock_db):
    mock_db.extension_anonymous_usage.find_one.return_value = {"token": "uuid-1", "count": 3}
    svc = ExtensionUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is False
    assert count == 3


@pytest.mark.asyncio
async def test_different_tokens_are_independent(mock_db):
    """UUID from install A does not affect install B even on same IP."""
    mock_db.extension_anonymous_usage.find_one.return_value = None
    svc = ExtensionUsageService()
    allowed_a, _ = await svc.check_and_increment(mock_db, token="uuid-A", ip="5.5.5.5")
    allowed_b, _ = await svc.check_and_increment(mock_db, token="uuid-B", ip="5.5.5.5")
    assert allowed_a is True
    assert allowed_b is True
