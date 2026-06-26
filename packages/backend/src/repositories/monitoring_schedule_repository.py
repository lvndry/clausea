from __future__ import annotations

import random
from datetime import datetime, timedelta

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.monitoring_schedule import MonitoringSchedule

logger = get_logger(__name__)


def _next_due(interval_days: int) -> datetime:
    return datetime.now() + timedelta(days=interval_days) + timedelta(hours=random.randint(0, 23))


class MonitoringScheduleRepository:
    async def enroll(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        product_id: str | None = None,
        interval_days: int = 30,
    ) -> None:
        schedule = MonitoringSchedule(
            product_slug=product_slug,
            product_id=product_id,
            next_crawl_due_at=_next_due(interval_days),
            interval_days=interval_days,
        )
        await db.monitoring_schedules.update_one(
            {"product_slug": product_slug},
            {"$setOnInsert": schedule.model_dump()},
            upsert=True,
        )
        logger.debug(
            "Enrolled %s in monitoring schedule (interval=%dd)", product_slug, interval_days
        )

    async def find_due(self, db: AgnosticDatabase, limit: int = 50) -> list[MonitoringSchedule]:
        now = datetime.now()
        cursor = (
            db.monitoring_schedules.find({"next_crawl_due_at": {"$lte": now}, "enabled": True})
            .sort("next_crawl_due_at", 1)
            .limit(limit)
        )
        rows = await cursor.to_list(length=limit)
        return [MonitoringSchedule(**row) for row in rows]

    async def mark_triggered(self, db: AgnosticDatabase, product_slug: str) -> None:
        schedule = await db.monitoring_schedules.find_one({"product_slug": product_slug})
        interval_days = (schedule or {}).get("interval_days", 30)
        await db.monitoring_schedules.update_one(
            {"product_slug": product_slug},
            {
                "$set": {
                    "last_crawl_triggered_at": datetime.now(),
                    "next_crawl_due_at": _next_due(interval_days),
                }
            },
        )
