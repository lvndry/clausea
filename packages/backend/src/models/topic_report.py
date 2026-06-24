"""Product-level topic report models.

These models expose cross-document, evidence-backed topic findings so callers can
render "what all documents say about one topic" with concrete citations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.document import CoverageStatus, InsightCategory

TopicStatus = Literal["found", "missing", "not_disclosed", "ambiguous"]
TopicStance = Literal["fair", "concerning", "harmful", "not_disclosed", "conflicting"]


class TopicCitation(BaseModel):
    """One quoted evidence span tied to a source document."""

    document_id: str
    document_title: str | None = None
    document_url: str | None = None
    quote: str
    section_title: str | None = None
    verified: bool = True


class TopicFinding(BaseModel):
    """A normalized statement under a topic, aggregated across documents."""

    value: str
    document_ids: list[str] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[TopicCitation] = Field(default_factory=list)


class TopicConflict(BaseModel):
    """Cross-document contradiction within a topic."""

    description: str
    severity: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    citations: list[TopicCitation] = Field(default_factory=list)


class TopicReportItem(BaseModel):
    """Per-topic aggregated output for product-level analysis."""

    topic: InsightCategory
    coverage_status: CoverageStatus = "not_analyzed"
    status: TopicStatus = "not_disclosed"
    stance: TopicStance = "not_disclosed"
    rationale: str | None = None
    rationale_key: str | None = None
    rationale_params: dict[str, int | str | None] | None = None
    findings: list[TopicFinding] = Field(default_factory=list)
    conflicts: list[TopicConflict] = Field(default_factory=list)


class ProductTopicReport(BaseModel):
    """All topic-level findings for a product overview."""

    product_slug: str
    generated_at: datetime | None = None
    topics: list[TopicReportItem] = Field(default_factory=list)
