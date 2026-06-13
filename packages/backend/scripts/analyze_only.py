"""Run only the LLM analysis (summarize + overview) on already-crawled docs for a slug.

Lets us complete an analysis-quality evaluation without re-crawling, and in a fresh
process (resets the in-process LLM circuit breaker).

Usage:
    uv run python scripts/analyze_only.py <slug>
"""

from __future__ import annotations

import asyncio
import sys
import time

from src.analyser import analyse_product_documents, generate_product_overview
from src.core.database import db_session
from src.core.logging import setup_logging
from src.services.service_factory import create_document_service, create_product_service


async def main(slug: str) -> None:
    setup_logging()
    async with db_session() as db:
        product_svc = create_product_service()
        doc_svc = create_document_service()

        product = await product_svc.get_product_by_slug(db, slug)
        if not product:
            print(f"No product for slug={slug}")
            return

        t0 = time.perf_counter()
        print(f"Summarizing documents for {slug} ...")
        await analyse_product_documents(db, slug, doc_svc)
        print(f"  summarize done in {time.perf_counter() - t0:.1f}s")

        t1 = time.perf_counter()
        print(f"Generating overview for {slug} ...")
        await generate_product_overview(
            db, slug, force_regenerate=True, product_svc=product_svc, document_svc=doc_svc
        )
        print(f"  overview done in {time.perf_counter() - t1:.1f}s")
        print("DONE")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: analyze_only.py <slug>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
