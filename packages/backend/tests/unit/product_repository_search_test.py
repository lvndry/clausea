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

    def capture_find(query: dict[str, Any] | None = None) -> MagicMock:
        # The no-search path calls find() unfiltered (no positional query).
        captured_queries.append(query if query is not None else {})
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
    # No-search path uses estimated_document_count() (O(1)) instead of count_documents({}).
    products_collection.estimated_document_count = AsyncMock(return_value=0)

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


def _domains_pattern(query: dict[str, Any]) -> str:
    for clause in query["$or"]:
        if "domains" in clause:
            return clause["domains"]["$regex"]
    raise AssertionError("expected a domains clause in the query")


@pytest.mark.parametrize(
    "search",
    [
        "https://www.anthropic.com/",
        "www.anthropic.com",
        "http://anthropic.com",
        "anthropic.com",
    ],
)
@pytest.mark.asyncio
async def test_find_paginated_normalizes_pasted_urls_for_domain_match(search: str) -> None:
    repo = ProductRepository()
    db, captured_queries = _fake_db_capturing_queries()

    await repo.find_paginated(db, skip=0, limit=10, search=search)

    assert captured_queries, "expected the search query to reach the collection"
    for query in captured_queries:
        assert _domains_pattern(query) == re.escape("anthropic.com")


@pytest.mark.asyncio
async def test_find_paginated_domain_falls_back_when_normalization_is_empty() -> None:
    repo = ProductRepository()
    db, captured_queries = _fake_db_capturing_queries()
    scheme_only = "https://"

    await repo.find_paginated(db, skip=0, limit=10, search=scheme_only)

    # Normalization strips everything, so the domains clause must fall back to the
    # raw escaped term rather than an empty pattern that matches every product.
    for query in captured_queries:
        assert _domains_pattern(query) == re.escape(scheme_only)


@pytest.mark.asyncio
async def test_find_paginated_without_search_uses_empty_query() -> None:
    repo = ProductRepository()
    db, captured_queries = _fake_db_capturing_queries()

    await repo.find_paginated(db, skip=0, limit=10, search="")
    # No regex filter is built, and the count uses the O(1) estimated_document_count.
    assert all(query == {} for query in captured_queries)
    db.products.estimated_document_count.assert_awaited_once()
    db.products.count_documents.assert_not_awaited()
