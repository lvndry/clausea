"""Unified product-level intelligence storage (rollup + LLM outputs)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import shortuuid
from pydantic import BaseModel, Field

from src.models.document import (
    ComplianceBreakdown,
    ConsumerExplainer,
    CoverageItem,
    InsightCategory,
    MetaSummary,
    ProductDeepAnalysis,
)


class RollupItem(BaseModel):
    """Slim cross-document finding (no evidence — hydrated at read time)."""

    category: InsightCategory
    value: str
    document_ids: list[str] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None


class RollupConflict(BaseModel):
    """Cross-document conflict pointer (no evidence — hydrated at read time)."""

    category: InsightCategory
    description: str
    document_ids: list[str] = Field(default_factory=list)
    severity: str | None = None


class ProductRollup(BaseModel):
    """Product-level rollup cache built from document extractions."""

    coverage: list[CoverageItem] = Field(default_factory=list)
    items: list[RollupItem] = Field(default_factory=list)
    conflicts: list[RollupConflict] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


class OverviewSnapshot(BaseModel):
    """Slim overview history entry (no full overview blob)."""

    snapshot_at: datetime = Field(default_factory=datetime.now)
    overview_hash: str
    risk_score: int | None = None
    risk_score_delta: int | None = None
    verdict: str | None = None
    one_line_summary: str | None = None
    changed_overview_fields: list[str] = Field(default_factory=list)
    job_id: str | None = None


class ProductIntelligence(BaseModel):
    """One document per product: rollup cache + LLM-generated outputs."""

    id: str = Field(default_factory=shortuuid.uuid)
    product_id: str
    product_slug: str
    source_hashes: dict[str, str] = Field(default_factory=dict)

    rollup: ProductRollup | None = None
    overview: MetaSummary | None = None
    explainer: ConsumerExplainer | None = None
    compliance: dict[str, ComplianceBreakdown] | None = None
    deep_analysis: ProductDeepAnalysis | None = None
    deep_analysis_document_signature: str | None = None

    overview_history: list[OverviewSnapshot] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=datetime.now)
    rollup_generated_at: datetime | None = None
    overview_generated_at: datetime | None = None
    updated_at: datetime = Field(default_factory=datetime.now)
