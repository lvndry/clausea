from bson import ObjectId

from src.repositories.product_intelligence_repository import _row_to_intelligence


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
