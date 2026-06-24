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

Run with:  uv run python -m src.migrations.fix_thin_evidence_products
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.core.database import db_session
from src.core.logging import get_logger

logger = get_logger(__name__)

ROBLOX_PRIVACY_URL = "https://www.roblox.com/info/privacy"


async def _apply(
    db,
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


async def fix_thin_evidence_products() -> None:
    """Apply the per-product crawl-config fixes and log a summary of changes."""
    async with db_session() as db:
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

        logger.info("Thin-evidence product config fixes — summary:")
        for row in results:
            slug = row["slug"]
            matched = row["matched"]
            if not matched:
                logger.warning("  %s: NOT FOUND in products collection", slug)
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


if __name__ == "__main__":
    asyncio.run(fix_thin_evidence_products())
