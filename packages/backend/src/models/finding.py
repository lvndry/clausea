from __future__ import annotations

from datetime import datetime
from typing import Any

import shortuuid
from pydantic import BaseModel, Field

from src.models.document import CoverageItem, EvidenceSpan, InsightCategory


class Finding(BaseModel):
    """Normalized extracted fact with evidence."""

    id: str = Field(default_factory=shortuuid.uuid)
    product_id: str
    document_id: str
    version_id: str | None = None
    section_id: str | None = None
    category: InsightCategory
    value: str
    normalized_value: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class AggregatedFinding(BaseModel):
    """Aggregated finding across documents."""

    category: InsightCategory
    value: str
    documents: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None


class FindingConflict(BaseModel):
    """Conflicting statements across documents."""

    category: InsightCategory
    description: str
    document_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    severity: str | None = None


class Aggregation(BaseModel):
    """Product-level aggregation of findings and conflicts."""

    id: str = Field(default_factory=shortuuid.uuid)
    product_id: str
    product_slug: str
    source_version_ids: list[str] = Field(default_factory=list)
    coverage: list[CoverageItem] | None = None
    findings: list[AggregatedFinding] = Field(default_factory=list)
    conflicts: list[FindingConflict] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.now)
