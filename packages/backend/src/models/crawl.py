from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import shortuuid
from pydantic import BaseModel, Field

CrawlSessionStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
CrawlTargetStatus = Literal["candidate", "selected", "fetched", "skipped", "failed"]


class CrawlSession(BaseModel):
    """Represents a single crawl run for a product."""

    id: str = Field(default_factory=shortuuid.uuid)
    product_id: str
    product_slug: str
    seed_urls: list[str] = Field(default_factory=list)
    status: CrawlSessionStatus = "pending"
    settings: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class CrawlTarget(BaseModel):
    """Candidate or selected URL discovered during crawl."""

    id: str = Field(default_factory=shortuuid.uuid)
    session_id: str
    url: str
    canonical_url: str | None = None
    source: str | None = None  # sitemap, footer, nav, heuristic, fallback
    score: float | None = None
    status: CrawlTargetStatus = "candidate"
    discovered_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
    fetched_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawlEvent(BaseModel):
    """Structured event for auditability and debugging."""

    id: str = Field(default_factory=shortuuid.uuid)
    session_id: str
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
