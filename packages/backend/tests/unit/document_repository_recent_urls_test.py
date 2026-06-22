"""find_recent_urls_by_product returns only docs written within the freshness window.

Backs crawl resume: a retried crawl skips re-fetching docs stored recently, while
docs older than the cutoff are still re-fetched so scheduled monitoring detects
policy changes. The recency filter lives in the Mongo query ($gte on updated_at,
falling back to created_at), so this test drives a small in-memory collection that
applies that query and asserts the cutoff is honoured.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

import pytest
from motor.core import AgnosticDatabase

from src.repositories.document_repository import DocumentRepository


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def sort(self, keys: list[tuple[str, int]]) -> _FakeCursor:
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeDocuments:
    """Minimal stand-in for db.documents that understands the recent-urls query."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def find(self, query: dict[str, Any], projection: dict[str, Any]) -> _FakeCursor:
        if "$and" in query:
            membership_clause, recency_clause = query["$and"]
            membership_or = membership_clause["$or"]
            product_id = next(
                (
                    clause.get("product_id") or clause.get("product_ids")
                    for clause in membership_or
                    if isinstance(clause, dict)
                ),
                None,
            )
            if not product_id:
                raise KeyError("product_id")
            or_clauses = recency_clause["$or"]
        else:
            # Backwards-compat: older repository query shape used top-level product_id + $or.
            product_id = query["product_id"]
            or_clauses = query["$or"]
        updated_cutoff = or_clauses[0]["updated_at"]["$gte"]
        created_cutoff = or_clauses[1]["created_at"]["$gte"]

        matched: list[dict[str, Any]] = []
        for row in self._rows:
            row_product_ids = row.get("product_ids")
            is_member = row.get("product_id") == product_id or (
                isinstance(row_product_ids, list) and product_id in row_product_ids
            )
            if not is_member:
                continue
            recent = (row.get("updated_at") and row["updated_at"] >= updated_cutoff) or (
                row.get("created_at") and row["created_at"] >= created_cutoff
            )
            if recent:
                # Honour the {"_id": 0, "url": 1} projection.
                matched.append({"url": row.get("url")})
        return _FakeCursor(matched)


class _FakeDb:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.documents = _FakeDocuments(rows)


@pytest.mark.asyncio
async def test_returns_recent_excludes_stale() -> None:
    now = datetime.now()
    cutoff = now - timedelta(hours=24)
    rows = [
        {
            "product_id": "prod-1",
            "url": "https://acme.com/fresh",
            "updated_at": now - timedelta(hours=1),
        },
        {
            "product_id": "prod-1",
            "url": "https://acme.com/stale",
            "updated_at": now - timedelta(days=10),
        },
    ]
    repo = DocumentRepository()
    urls = await repo.find_recent_urls_by_product(
        cast(AgnosticDatabase, _FakeDb(rows)), "prod-1", cutoff
    )
    assert urls == ["https://acme.com/fresh"]


@pytest.mark.asyncio
async def test_created_at_fallback_for_docs_without_updated_at() -> None:
    # Legacy rows written before updated_at existed are still recognised via created_at.
    now = datetime.now()
    cutoff = now - timedelta(hours=24)
    rows = [
        {
            "product_id": "prod-1",
            "url": "https://acme.com/legacy-fresh",
            "created_at": now - timedelta(hours=2),
        },
    ]
    repo = DocumentRepository()
    urls = await repo.find_recent_urls_by_product(
        cast(AgnosticDatabase, _FakeDb(rows)), "prod-1", cutoff
    )
    assert urls == ["https://acme.com/legacy-fresh"]


@pytest.mark.asyncio
async def test_scopes_to_product() -> None:
    now = datetime.now()
    cutoff = now - timedelta(hours=24)
    rows = [
        {
            "product_id": "prod-1",
            "url": "https://acme.com/mine",
            "updated_at": now,
        },
        {
            "product_id": "prod-2",
            "url": "https://other.com/theirs",
            "updated_at": now,
        },
    ]
    repo = DocumentRepository()
    urls = await repo.find_recent_urls_by_product(
        cast(AgnosticDatabase, _FakeDb(rows)), "prod-1", cutoff
    )
    assert urls == ["https://acme.com/mine"]
