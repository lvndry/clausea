"""Regression test: find_paginated must match user search input literally.

Raw user input passed into a Mongo $regex can 500 on invalid patterns
(e.g. an unclosed "(") or open a ReDoS vector — the search term has to be
escaped before it reaches the query.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.product_repository import ProductRepository


def _fake_db_capturing_queries() -> tuple[Any, list[dict[str, Any]]]:
    captured_queries: list[dict[str, Any]] = []

    def capture_find(query: dict[str, Any]) -> MagicMock:
        captured_queries.append(query)
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.skip.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[])
        return cursor

    async def capture_count(query: dict[str, Any]) -> int:
        captured_queries.append(query)
        return 0

    products_collection = MagicMock()
    products_collection.find = MagicMock(side_effect=capture_find)
    products_collection.count_documents = AsyncMock(side_effect=capture_count)

    db = MagicMock()
    db.products = products_collection
    return db, captured_queries


@pytest.mark.asyncio
async def test_find_paginated_escapes_regex_metacharacters() -> None:
    repo = ProductRepository()
    db, captured_queries = _fake_db_capturing_queries()
    hostile_search = "(.*+[unclosed"

    products, total = await repo.find_paginated(db, skip=0, limit=10, search=hostile_search)
    assert products == []
    assert total == 0

    assert captured_queries, "expected the search query to reach the collection"
    for query in captured_queries:
        for clause in query["$or"]:
            pattern = next(iter(clause.values()))["$regex"]
            assert pattern == re.escape(hostile_search)
            re.compile(pattern)  # must be a valid (literal) pattern


@pytest.mark.asyncio
async def test_find_paginated_without_search_uses_empty_query() -> None:
    repo = ProductRepository()
    db, captured_queries = _fake_db_capturing_queries()

    await repo.find_paginated(db, skip=0, limit=10, search="")
    assert all(query == {} for query in captured_queries)
