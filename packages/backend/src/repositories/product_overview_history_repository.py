from __future__ import annotations

from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.product_overview_history import ProductOverviewHistory

logger = get_logger(__name__)

_TRACKED_OVERVIEW_FIELDS = [
    "risk_score",
    "verdict",
    "one_line_summary",
    "dangers",
    "keypoints",
    "summary",
]


def _changed_overview_fields(prev: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [field for field in _TRACKED_OVERVIEW_FIELDS if prev.get(field) != current.get(field)]


class ProductOverviewHistoryRepository:
    async def save_snapshot(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        overview_data: dict[str, Any],
        prev_overview_data: dict[str, Any] | None,
        job_id: str | None = None,
    ) -> None:
        risk_score = overview_data.get("risk_score")
        prev_risk = prev_overview_data.get("risk_score") if prev_overview_data else None
        risk_score_delta = (
            (risk_score - prev_risk) if (risk_score is not None and prev_risk is not None) else None
        )
        changed = _changed_overview_fields(prev_overview_data or {}, overview_data)

        snapshot = ProductOverviewHistory(
            product_slug=product_slug,
            risk_score=risk_score,
            risk_score_delta=risk_score_delta,
            verdict=overview_data.get("verdict"),
            one_line_summary=overview_data.get("one_line_summary"),
            changed_overview_fields=changed,
            overview=overview_data,
            job_id=job_id,
        )
        await db.product_overview_history.insert_one(snapshot.model_dump())
        logger.debug(
            "Saved overview snapshot for %s (delta=%s changed=%s)",
            product_slug,
            risk_score_delta,
            changed,
        )

    async def find_by_product(
        self, db: AgnosticDatabase, product_slug: str, limit: int = 50
    ) -> list[ProductOverviewHistory]:
        cursor = (
            db.product_overview_history.find({"product_slug": product_slug})
            .sort("snapshot_at", -1)
            .limit(limit)
        )
        rows = await cursor.to_list(length=limit)
        return [ProductOverviewHistory(**row) for row in rows]
