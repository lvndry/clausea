from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.extension_usage import ANONYMOUS_LIMIT, ExtensionUsageService


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update = AsyncMock()
    collection.find_one = AsyncMock()
    # db[COLLECTION] is the production access path; attribute access is wired to the same object
    db.extension_anonymous_usage = collection
    db.__getitem__ = MagicMock(return_value=collection)
    return db


@pytest.mark.asyncio
async def test_allows_first_use(mock_db):
    # find_one_and_update returns the updated doc (count=1 after $inc)
    mock_db.extension_anonymous_usage.find_one_and_update.return_value = {
        "token": "uuid-1",
        "count": 1,
    }
    svc = ExtensionUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is True
    assert count == 1


@pytest.mark.asyncio
async def test_allows_up_to_limit(mock_db):
    # find_one_and_update returns doc with count at limit (ANONYMOUS_LIMIT)
    mock_db.extension_anonymous_usage.find_one_and_update.return_value = {
        "token": "uuid-1",
        "count": ANONYMOUS_LIMIT,
    }
    svc = ExtensionUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is True
    assert count == ANONYMOUS_LIMIT


@pytest.mark.asyncio
async def test_blocks_over_limit(mock_db):
    # find_one_and_update returns None when filter doesn't match (count >= limit)
    mock_db.extension_anonymous_usage.find_one_and_update.return_value = None
    mock_db.extension_anonymous_usage.find_one.return_value = {
        "token": "uuid-1",
        "count": ANONYMOUS_LIMIT,
    }
    svc = ExtensionUsageService()
    allowed, count = await svc.check_and_increment(mock_db, token="uuid-1", ip="1.2.3.4")
    assert allowed is False
    assert count == ANONYMOUS_LIMIT


@pytest.mark.asyncio
async def test_different_tokens_are_independent(mock_db):
    """UUID from install A does not affect install B even on same IP."""
    mock_db.extension_anonymous_usage.find_one_and_update.return_value = {
        "token": "uuid-A",
        "count": 1,
    }
    svc = ExtensionUsageService()
    allowed_a, _ = await svc.check_and_increment(mock_db, token="uuid-A", ip="5.5.5.5")
    allowed_b, _ = await svc.check_and_increment(mock_db, token="uuid-B", ip="5.5.5.5")
    assert allowed_a is True
    assert allowed_b is True
