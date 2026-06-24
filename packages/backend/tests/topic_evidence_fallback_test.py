"""Tests for topic_evidence_fallback: recover citations from document extractions."""

from __future__ import annotations

from typing import Any, cast

import pytest

from src.models.document import (
    Document,
    DocumentExtraction,
    EvidenceSpan,
    ExtractedChildrenPolicy,
    ExtractedDataItem,
    ExtractedDataPurposeLink,
    TopicStanceBreakdown,
    TopicSupportCitation,
)
from src.services.topic_evidence_fallback import attach_fallback_evidence


def _privacy_document() -> Document:
    return Document(
        id="doc_1",
        product_id="product_1",
        url="https://example.com/privacy",
        title="Privacy Policy",
        doc_type="privacy_policy",
        markdown="We collect your email and share it with advertising partners.",
        extraction=DocumentExtraction(
            source_content_hash="abc",
            data_collected=[
                ExtractedDataItem(
                    data_type="Email address",
                    evidence=[
                        EvidenceSpan(
                            document_id="doc_1",
                            quote="We collect your email address.",
                            url="https://example.com/privacy",
                            section_title="Information We Collect",
                        ),
                        EvidenceSpan(
                            document_id="doc_1",
                            quote="",
                            url="https://example.com/privacy",
                        ),
                    ],
                ),
                ExtractedDataItem(
                    data_type="Device identifier",
                    evidence=[
                        EvidenceSpan(
                            document_id="doc_1",
                            quote="We collect device identifiers for analytics.",
                            url="https://example.com/privacy",
                        ),
                    ],
                ),
            ],
        ),
    )


@pytest.mark.asyncio
async def test_attach_fallback_evidence_attaches_citations_for_found_topic_with_zero_citations() -> (
    None
):
    stance = TopicStanceBreakdown(
        topic="data_collection",
        status="found",
        stance="moderate_risk",
        supporting_citations=[],
    )

    attached = await attach_fallback_evidence([stance], [_privacy_document()])

    assert attached == 2
    citations = stance.supporting_citations
    assert len(citations) == 2
    assert all(citation.document_id == "doc_1" for citation in citations)
    assert all(citation.document_title == "Privacy Policy" for citation in citations)
    assert all(citation.document_url == "https://example.com/privacy" for citation in citations)
    assert all(citation.verified is True for citation in citations)
    quotes = [citation.quote for citation in citations]
    assert "We collect your email address." in quotes
    assert "We collect device identifiers for analytics." in quotes
    assert citations[0].section_title == "Information We Collect"


@pytest.mark.asyncio
async def test_attach_fallback_evidence_skips_missing_topic_stances() -> None:
    stance = TopicStanceBreakdown(
        topic="data_sale",
        status="missing",
        stance="not_disclosed",
        supporting_citations=[],
    )

    attached = await attach_fallback_evidence([stance], [_privacy_document()])

    assert attached == 0
    assert stance.supporting_citations == []


@pytest.mark.asyncio
async def test_attach_fallback_evidence_skips_topic_stances_with_existing_citations() -> None:
    existing = TopicSupportCitation(
        document_id="doc_1",
        document_title="Privacy Policy",
        document_url="https://example.com/privacy",
        quote="Existing verified quote.",
        verified=True,
    )
    stance = TopicStanceBreakdown(
        topic="data_collection",
        status="found",
        stance="moderate_risk",
        supporting_citations=[existing],
    )

    attached = await attach_fallback_evidence([stance], [_privacy_document()])

    assert attached == 0
    assert stance.supporting_citations == [existing]


@pytest.mark.asyncio
async def test_attach_fallback_evidence_caps_at_three_citations() -> None:
    document = Document(
        id="doc_1",
        product_id="product_1",
        url="https://example.com/privacy",
        title="Privacy Policy",
        doc_type="privacy_policy",
        markdown="...",
        extraction=DocumentExtraction(
            source_content_hash="abc",
            data_collected=[
                ExtractedDataItem(
                    data_type=f"Data type {index}",
                    evidence=[
                        EvidenceSpan(
                            document_id="doc_1",
                            quote=f"Quote number {index}.",
                            url="https://example.com/privacy",
                        )
                    ],
                )
                for index in range(6)
            ],
        ),
    )
    stance = TopicStanceBreakdown(
        topic="data_collection",
        status="found",
        stance="moderate_risk",
        supporting_citations=[],
    )

    attached = await attach_fallback_evidence([stance], [document])

    assert attached == 3
    assert len(stance.supporting_citations) == 3


@pytest.mark.asyncio
async def test_attach_fallback_evidence_filters_data_purposes_by_keyword() -> None:
    document = Document(
        id="doc_1",
        product_id="product_1",
        url="https://example.com/privacy",
        title="Privacy Policy",
        doc_type="privacy_policy",
        markdown="...",
        extraction=DocumentExtraction(
            source_content_hash="abc",
            data_purposes=[
                ExtractedDataPurposeLink(
                    data_type="Email",
                    purposes=["advertising"],
                    evidence=[
                        EvidenceSpan(
                            document_id="doc_1",
                            quote="We use email for advertising partners.",
                            url="https://example.com/privacy",
                        )
                    ],
                ),
                ExtractedDataPurposeLink(
                    data_type="Usage data",
                    purposes=["analytics"],
                    evidence=[
                        EvidenceSpan(
                            document_id="doc_1",
                            quote="We use usage data for analytics.",
                            url="https://example.com/privacy",
                        )
                    ],
                ),
            ],
        ),
    )
    stance = TopicStanceBreakdown(
        topic="advertising",
        status="found",
        stance="moderate_risk",
        supporting_citations=[],
    )

    attached = await attach_fallback_evidence([stance], [document])

    assert attached == 1
    assert len(stance.supporting_citations) == 1
    assert stance.supporting_citations[0].quote == "We use email for advertising partners."


@pytest.mark.asyncio
async def test_attach_fallback_evidence_handles_children_policy_single_object() -> None:
    document = Document(
        id="doc_1",
        product_id="product_1",
        url="https://example.com/privacy",
        title="Privacy Policy",
        doc_type="privacy_policy",
        markdown="...",
        extraction=DocumentExtraction(
            source_content_hash="abc",
            children_policy=ExtractedChildrenPolicy(
                minimum_age=13,
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        quote="Our service is not directed to children under 13.",
                        url="https://example.com/privacy",
                    )
                ],
            ),
        ),
    )
    stance = TopicStanceBreakdown(
        topic="children",
        status="found",
        stance="moderate_risk",
        supporting_citations=[],
    )

    attached = await attach_fallback_evidence([stance], [document])

    assert attached == 1
    assert (
        stance.supporting_citations[0].quote == "Our service is not directed to children under 13."
    )


@pytest.mark.asyncio
async def test_attach_fallback_evidence_accepts_dict_topic_stances_and_documents() -> None:
    stance: dict[str, Any] = {
        "topic": "data_collection",
        "status": "found",
        "stance": "moderate_risk",
        "supporting_citations": [],
    }
    document: dict[str, Any] = {
        "id": "doc_1",
        "url": "https://example.com/privacy",
        "title": "Privacy Policy",
        "extraction": {
            "source_content_hash": "abc",
            "data_collected": [
                {
                    "data_type": "Email",
                    "evidence": [
                        {
                            "document_id": "doc_1",
                            "quote": "We collect your email.",
                            "url": "https://example.com/privacy",
                            "section_title": "Collection",
                        }
                    ],
                }
            ],
        },
    }

    attached = await attach_fallback_evidence(
        cast(list[TopicStanceBreakdown], [stance]),
        cast(list[Document], [document]),
    )

    assert attached == 1
    citations = stance["supporting_citations"]
    assert len(citations) == 1
    assert citations[0].document_id == "doc_1"
    assert citations[0].document_title == "Privacy Policy"
    assert citations[0].quote == "We collect your email."
    assert citations[0].section_title == "Collection"
    assert citations[0].verified is True
