"""Backfill rollups and overviews for selected products.

Usage:
    uv run python scripts/backfill_topic_evidence.py figma github mistralai
    uv run python scripts/backfill_topic_evidence.py --use-production figma github
    uv run python scripts/backfill_topic_evidence.py --skip-overview figma

Notes:
- By default this uses local MONGO_URI.
- --use-production switches to PRODUCTION_MONGO_URI.
- Overview regeneration can trigger LLM synthesis; use --skip-overview to rebuild
  only the product rollup cache.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from dotenv import load_dotenv

load_dotenv()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill topic evidence for product slugs.")
    parser.add_argument("slugs", nargs="+", help="Product slugs to backfill")
    parser.add_argument(
        "--use-production",
        action="store_true",
        help="Use PRODUCTION_MONGO_URI instead of local MONGO_URI",
    )
    parser.add_argument(
        "--skip-overview",
        action="store_true",
        help="Only rebuild rollups; do not regenerate overview",
    )
    return parser.parse_args()


async def _backfill_slug(
    *,
    slug: str,
    db,
    product_svc,
    doc_svc,
    rollup_svc,
    skip_overview: bool,
) -> None:
    product = await product_svc.get_product_by_slug(db, slug)
    if not product:
        print(f"[skip] {slug}: product not found")
        return

    print(f"[start] {slug}")
    t0 = time.perf_counter()

    aggregation = await rollup_svc.build_product_rollup(
        db, product_id=product.id, product_slug=slug
    )
    print(
        f"  rollup: findings={len(aggregation.findings)} conflicts={len(aggregation.conflicts)} "
        f"coverage={len(aggregation.coverage)}"
    )

    if not skip_overview:
        from src.analyser import generate_product_overview

        overview = await generate_product_overview(
            db,
            slug,
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=doc_svc,
        )
        print(
            f"  overview: risk={overview.risk_score} verdict={overview.verdict} "
            f"topic_stances={len(overview.topic_stances or [])}"
        )

    print(f"[done] {slug} in {time.perf_counter() - t0:.1f}s")


async def _run(args: argparse.Namespace) -> int:
    if args.use_production:
        production_uri = os.getenv("PRODUCTION_MONGO_URI")
        if not production_uri:
            print("PRODUCTION_MONGO_URI is not set")
            return 1
        os.environ["MONGO_URI"] = production_uri

    from src.core.database import db_session
    from src.core.logging import setup_logging
    from src.repositories.document_repository import DocumentRepository
    from src.services.product_rollup_service import ProductRollupService
    from src.services.service_factory import create_document_service, create_product_service

    setup_logging()

    product_svc = create_product_service()
    doc_svc = create_document_service()
    rollup_svc = ProductRollupService(document_repo=DocumentRepository())

    async with db_session() as db:
        for slug in args.slugs:
            await _backfill_slug(
                slug=slug,
                db=db,
                product_svc=product_svc,
                doc_svc=doc_svc,
                rollup_svc=rollup_svc,
                skip_overview=args.skip_overview,
            )
    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
