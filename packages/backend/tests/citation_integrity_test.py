"""Tests for citation referential integrity: orphan invalidation and UI filtering."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.document import TopicStanceBreakdown, TopicSupportCitation
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository
from src.services.citation_filter import filter_topic_stance_citations


def _build_pi_db(count: int) -> tuple[Any, Any]:
    """Mock db whose ``product_intelligence`` collection reports ``count`` matching citations."""
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[{"total": count}] if count else [])

    pi_collection = MagicMock()
    pi_collection.aggregate = MagicMock(return_value=cursor)
    pi_collection.update_many = AsyncMock(return_value=MagicMock(matched_count=1))

    db = MagicMock()
    db.__getitem__.return_value = pi_collection
    return db, pi_collection


@pytest.mark.asyncio
async def test_mark_citations_stale_for_document_updates_matching_citations() -> None:
    repo = ProductIntelligenceRepository()
    db, pi_collection = _build_pi_db(count=3)

    marked = await repo.mark_citations_stale_for_document(db, "doc-orphan-1")

    assert marked == 3
    pi_collection.update_many.assert_awaited_once()
    args, kwargs = pi_collection.update_many.call_args
    assert args[0] == {"overview.topic_stances.supporting_citations.document_id": "doc-orphan-1"}
    assert args[1]["$set"] == {
        "overview.topic_stances.$[].supporting_citations.$[cite].stale": True
    }
    assert kwargs["array_filters"] == [{"cite.document_id": "doc-orphan-1"}]


@pytest.mark.asyncio
async def test_mark_citations_stale_for_document_skips_when_no_matches() -> None:
    repo = ProductIntelligenceRepository()
    db, pi_collection = _build_pi_db(count=0)

    marked = await repo.mark_citations_stale_for_document(db, "doc-orphan-2")

    assert marked == 0
    pi_collection.update_many.assert_not_awaited()


def _make_citation(
    document_id: str, verified: bool = True, stale: bool = False
) -> TopicSupportCitation:
    return TopicSupportCitation(document_id=document_id, quote="q", verified=verified, stale=stale)


def _make_stance(citations: list[TopicSupportCitation]) -> TopicStanceBreakdown:
    return TopicStanceBreakdown(
        topic="data_sharing",
        status="found",
        stance="high_risk",
        supporting_citations=citations,
    )


def test_filter_removes_unverified_and_stale_citations() -> None:
    stance = _make_stance(
        [
            _make_citation("doc-1", verified=True, stale=False),
            _make_citation("doc-2", verified=False, stale=False),
            _make_citation("doc-3", verified=True, stale=True),
            _make_citation("doc-4", verified=False, stale=True),
        ]
    )

    result = filter_topic_stance_citations([stance])

    assert len(result) == 1
    citations = result[0].supporting_citations
    assert len(citations) == 1
    assert citations[0].document_id == "doc-1"


def test_filter_keeps_stance_with_empty_citations_when_all_filtered() -> None:
    stance = _make_stance(
        [
            _make_citation("doc-2", verified=False),
            _make_citation("doc-3", stale=True),
        ]
    )

    result = filter_topic_stance_citations([stance])

    assert len(result) == 1
    assert result[0].supporting_citations == []


def test_filter_accepts_plain_dicts_and_defaults_missing_stale() -> None:
    stance = {
        "topic": "data_sharing",
        "status": "found",
        "stance": "high_risk",
        "supporting_citations": [
            {"document_id": "doc-1", "quote": "q", "verified": True},
            {"document_id": "doc-2", "quote": "q", "verified": False, "stale": False},
            {"document_id": "doc-3", "quote": "q", "verified": True, "stale": True},
        ],
    }

    result = filter_topic_stance_citations([stance])

    assert len(result) == 1
    assert isinstance(result[0], dict)
    kept = result[0]["supporting_citations"]
    assert [c["document_id"] for c in kept] == ["doc-1"]


def test_filter_does_not_mutate_input() -> None:
    stance = _make_stance(
        [
            _make_citation("doc-1", verified=True),
            _make_citation("doc-2", verified=False),
        ]
    )
    original_count = len(stance.supporting_citations)

    filter_topic_stance_citations([stance])

    assert len(stance.supporting_citations) == original_count
