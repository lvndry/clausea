from __future__ import annotations

from datetime import datetime
from typing import Any

import shortuuid
from pydantic import BaseModel, Field


class ProductOverviewHistory(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    product_slug: str
    snapshot_at: datetime = Field(default_factory=datetime.now)
    risk_score: int | None = None
    risk_score_delta: int | None = None
    verdict: str | None = None
    one_line_summary: str | None = None
    changed_overview_fields: list[str] = Field(default_factory=list)
    overview: dict[str, Any] = Field(default_factory=dict)
    job_id: str | None = None
