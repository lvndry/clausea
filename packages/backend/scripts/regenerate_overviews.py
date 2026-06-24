"""Regenerate product overviews for all or selected products.

Re-runs the overview LLM with the new prompts, grade clamping, consumer
topic copy, citation filter, overview guards, and LLM semantic review.
Existing overviews keep the old format until regenerated.

Usage:
    # Regenerate ALL products with existing overviews (uses MONGO_URI from .env):
    uv run python scripts/regenerate_overviews.py

    # Regenerate specific products:
    uv run python scripts/regenerate_overviews.py reddit spotify signal

    # Dry run — list what would be regenerated, don't call the LLM:
    uv run python scripts/regenerate_overviews.py --dry-run

    # Run against production (uses PRODUCTION_MONGO_URI from .env):
    uv run python scripts/regenerate_overviews.py --production

    # Limit concurrency (default 3):
    uv run python scripts/regenerate_overviews.py --concurrency 1 --production
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _resolve_production() -> bool:
    """Check --production flag and set MONGO_URI before database module imports."""
    if "--production" in sys.argv:
        prod_uri = os.getenv("PRODUCTION_MONGO_URI")
        if not prod_uri:
            print("ERROR: PRODUCTION_MONGO_URI not set in environment")
            sys.exit(1)
        os.environ["MONGO_URI"] = prod_uri
        return True
    return False


_USE_PRODUCTION = _resolve_production()

from src.analyser import generate_product_overview
from src.core.database import db_session
from src.core.logging import get_logger, setup_logging
from src.services.service_factory import create_document_service, create_product_service

logger = get_logger(__name__)


@dataclass
class RegenResult:
    slug: str
    success: bool
    duration_s: float
    grade: str | None = None
    verdict: str | None = None
    error: str | None = None


@dataclass
class RegenSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[RegenResult] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return sum(r.duration_s for r in self.results)


async def regenerate_one(
    db,
    slug: str,
    product_svc,
    doc_svc,
    semaphore: asyncio.Semaphore,
) -> RegenResult:
    async with semaphore:
        t0 = time.perf_counter()
        try:
            overview = await generate_product_overview(
                db,
                slug,
                force_regenerate=True,
                product_svc=product_svc,
                document_svc=doc_svc,
            )
            duration = time.perf_counter() - t0
            grade = getattr(overview, "grade", None)
            verdict = getattr(overview, "verdict", None)
            logger.info(
                "Regenerated %s — grade=%s verdict=%s (%.1fs)",
                slug,
                grade,
                verdict,
                duration,
            )
            return RegenResult(
                slug=slug,
                success=True,
                duration_s=duration,
                grade=grade,
                verdict=verdict,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            duration = time.perf_counter() - t0
            logger.error("Failed to regenerate %s: %s", slug, exc)
            return RegenResult(
                slug=slug,
                success=False,
                duration_s=duration,
                error=str(exc),
            )


async def main(
    slugs: list[str] | None,
    dry_run: bool,
    concurrency: int,
    use_production: bool,
) -> None:
    setup_logging()

    if use_production:
        print("Using PRODUCTION_MONGO_URI")

    product_svc = create_product_service()
    doc_svc = create_document_service()

    async with db_session() as db:
        if slugs:
            target_slugs = slugs
        else:
            cursor = db.product_intelligence.find(
                {"overview": {"$exists": True, "$ne": None}},
                {"product_slug": 1, "_id": 0},
            )
            rows = await cursor.to_list(length=None)
            target_slugs = sorted(row["product_slug"] for row in rows if row.get("product_slug"))

        print(f"Found {len(target_slugs)} product(s) to regenerate.")
        if dry_run:
            for slug in target_slugs:
                print(f"  [dry-run] {slug}")
            return

        print(f"Concurrency: {concurrency}")
        print()

        semaphore = asyncio.Semaphore(concurrency)
        summary = RegenSummary(total=len(target_slugs))

        tasks = [regenerate_one(db, slug, product_svc, doc_svc, semaphore) for slug in target_slugs]

        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            summary.results.append(result)
            if result.success:
                summary.succeeded += 1
                status = f"OK   grade={result.grade} verdict={result.verdict}"
            else:
                summary.failed += 1
                status = f"FAIL {result.error}"
            completed += 1
            print(
                f"  [{completed}/{summary.total}] {result.slug:25s} {status}  ({result.duration_s:.1f}s)"
            )

        print()
        print("=" * 60)
        print(
            f"Done: {summary.succeeded} succeeded, {summary.failed} failed, "
            f"{summary.total} total, {summary.duration_s:.0f}s"
        )
        if summary.failed:
            print("\nFailed products:")
            for r in summary.results:
                if not r.success:
                    print(f"  {r.slug}: {r.error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate product overviews")
    parser.add_argument(
        "slugs",
        nargs="*",
        help="Product slugs to regenerate (default: all with existing overviews)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be regenerated without calling the LLM",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Max concurrent overview generations (default: 3)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use PRODUCTION_MONGO_URI instead of MONGO_URI",
    )
    args = parser.parse_args()

    asyncio.run(main(args.slugs, args.dry_run, args.concurrency, args.production))
