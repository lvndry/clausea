from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.repositories.product_intelligence_repository import (
    ProductIntelligenceRepository,
    _row_to_intelligence,
)


def test_row_to_intelligence_strips_mongo_id() -> None:
    app_id = "app-shortuuid-id"
    row = {
        "_id": ObjectId(),
        "id": app_id,
        "product_id": "prod-1",
        "product_slug": "example",
    }
    intelligence = _row_to_intelligence(row)
    assert intelligence is not None
    assert intelligence.id == app_id
    assert intelligence.product_id == "prod-1"


def test_row_to_intelligence_returns_none_for_missing_row() -> None:
    assert _row_to_intelligence(None) is None


@pytest.mark.asyncio
async def test_get_for_explainer_validates_explainer_blob_only() -> None:
    repo = ProductIntelligenceRepository()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_collection.find_one = AsyncMock(
        return_value={
            "explainer": {
                "headline": "Spectacles privacy in plain English",
                "grade": "C",
            }
        }
    )

    explainer = await repo.get_for_explainer(mock_db, "spectacles")

    assert explainer is not None
    assert explainer.headline == "Spectacles privacy in plain English"
    assert explainer.grade == "C"
    mock_collection.find_one.assert_awaited_once_with(
        {"product_slug": "spectacles"},
        {"_id": 0, "explainer": 1},
    )
