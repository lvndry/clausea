"""Fix product crawl configs for the 7 products flagged by the thin-evidence audit.

The audit found broken crawls caused by misconfigured robots handling, anti-bot 403s,
and a subdomain-drift bug that let ``aws.amazon.com`` leak into the amazon crawl scope.
This migration patches the per-product crawl settings so the next pipeline run crawls
the right scope:

- ``booking``  : SPA shell problem is a browser-rendering issue, not robots. Leave
                 crawl_base_urls untouched; ensure crawl_ignore_robots is False.
- ``roblox``   : Zendesk help centre 403s the bot. Ignore robots for the crawl and
                 add the canonical Roblox privacy URL to crawl_base_urls.
- ``messenger``: Facebook robots.txt blocks ``/`` entirely. Ignore robots for the crawl.
- ``amazon``   : ``aws.amazon.com`` drifted into the crawl via the old subdomain matcher.
                 Deny it explicitly via crawl_denied_domains.

Idempotent: every write is a ``$set`` to a target value or ``$addToSet``, so re-runs
converge on the same desired state with no-op modifications.
"""

from __future__ import annotations

import asyncio
from typing import Any

from motor.core import AgnosticDatabase

from src.core.database import db_session
from src.core.logging import get_logger
from src.migrations.base import Migration

logger = get_logger(__name__)

ROBLOX_PRIVACY_URL = "https://www.roblox.com/info/privacy"


async def _apply(
    db: AgnosticDatabase,
    slug: str,
    set_fields: dict[str, Any],
    add_to_set: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    before = await db.products.find_one({"slug": slug}, {"_id": 0})
    update: dict[str, Any] = {"$set": set_fields}
    if add_to_set:
        update["$addToSet"] = {field: {"$each": values} for field, values in add_to_set.items()}
    result = await db.products.update_one({"slug": slug}, update)
    after = await db.products.find_one({"slug": slug}, {"_id": 0})
    return {
        "slug": slug,
        "matched": result.matched_count,
        "modified": result.modified_count,
        "before": before,
        "after": after,
    }


async def fix_thin_evidence_products(db: AgnosticDatabase) -> dict[str, Any]:
    """Apply the per-product crawl-config fixes and return a summary."""
    results: list[dict[str, Any]] = []

    results.append(await _apply(db, "booking", {"crawl_ignore_robots": False}))
    results.append(
        await _apply(
            db,
            "roblox",
            {"name": "Roblox", "crawl_ignore_robots": True},
            {"crawl_base_urls": [ROBLOX_PRIVACY_URL]},
        )
    )
    results.append(await _apply(db, "messenger", {"crawl_ignore_robots": True}))
    results.append(
        await _apply(
            db,
            "amazon",
            {},
            {"crawl_denied_domains": ["aws.amazon.com"]},
        )
    )

    summary: dict[str, Any] = {"products": {}}
    for row in results:
        slug = row["slug"]
        if not row["matched"]:
            logger.warning("  %s: NOT FOUND in products collection", slug)
            summary["products"][slug] = {"found": False}
            continue
        before = row["before"] or {}
        after = row["after"] or {}
        changed: list[str] = []
        for field in ("crawl_ignore_robots", "crawl_denied_domains", "crawl_base_urls", "name"):
            if before.get(field) != after.get(field):
                changed.append(f"{field}: {before.get(field)!r} -> {after.get(field)!r}")
        if changed:
            logger.info("  %s: %s", slug, "; ".join(changed))
        else:
            logger.info("  %s: no change (already correct)", slug)
        summary["products"][slug] = {"found": True, "changed": changed}
    return summary


class FixThinEvidenceProducts(Migration):
    migration_id = "001_fix_thin_evidence_products"
    description = "Patch crawl configs (robots/denied domains) for thin-evidence audit products"

    async def upgrade(self, db: AgnosticDatabase) -> dict[str, Any]:
        return await fix_thin_evidence_products(db)


if __name__ == "__main__":

    async def _run() -> None:
        async with db_session() as db:
            await fix_thin_evidence_products(db)

    asyncio.run(_run())
