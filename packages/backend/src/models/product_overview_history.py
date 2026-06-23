from __future__ import annotations

from datetime import datetime

import shortuuid
from pydantic import BaseModel, Field


class ProductOverviewHistory(BaseModel):
    """Slim overview change snapshot (no full overview blob)."""

    id: str = Field(default_factory=shortuuid.uuid)
    product_slug: str
    snapshot_at: datetime = Field(default_factory=datetime.now)
    overview_hash: str
    risk_score: int | None = None
    risk_score_delta: int | None = None
    verdict: str | None = None
    one_line_summary: str | None = None
    changed_overview_fields: list[str] = Field(default_factory=list)
    job_id: str | None = None
