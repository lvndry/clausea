from __future__ import annotations

from datetime import datetime

import shortuuid
from pydantic import BaseModel, Field


class MonitoringSchedule(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    product_slug: str
    product_id: str | None = None
    enrolled_at: datetime = Field(default_factory=datetime.now)
    last_crawl_triggered_at: datetime | None = None
    next_crawl_due_at: datetime
    interval_days: int = 30
    enabled: bool = True
