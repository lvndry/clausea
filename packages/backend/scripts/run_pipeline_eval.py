"""One-off driver: run the full pipeline for a single URL and report per-step results.

Uses the exact production path (PipelineService.create_job_for_url + run_pipeline) so the
output reflects real quality. Not part of the app — intended for manual quality evaluation.

Usage:
    uv run python scripts/run_pipeline_eval.py https://example.com
"""

from __future__ import annotations

import asyncio
import sys
import time

from src.core.database import db_session
from src.core.logging import get_logger, setup_logging
from src.services.service_factory import create_pipeline_service

logger = get_logger(__name__)


async def main(url: str) -> None:
    setup_logging()
    pipeline_svc = create_pipeline_service()

    async with db_session() as db:
        result = await pipeline_svc.create_job_for_url(db, url)

    if result.get("already_indexed"):
        print(f"ALREADY_INDEXED: {result['product_slug']} ({result['product_name']})")
        return

    job = result["job"]
    print(f"JOB_CREATED: id={job.id} slug={job.product_slug} name={job.product_name}")
    print(f"Running full pipeline for {url} ...")

    start = time.perf_counter()
    # run_pipeline opens its own db_session and runs crawl -> summarize -> overview
    await pipeline_svc.run_pipeline(job.id)
    elapsed = time.perf_counter() - start

    async with db_session() as db:
        final = await pipeline_svc.get_job(db, job.id)

    print(f"\n=== PIPELINE FINISHED in {elapsed:.1f}s ===")
    if final is None:
        print("Job not found after run (unexpected).")
        return

    print(f"status        : {final.status}")
    print(f"documents_found : {final.documents_found}")
    print(f"documents_stored: {final.documents_stored}")
    if final.error:
        print(f"error         : {final.error}")
    print("steps:")
    for step in final.steps:
        print(f"  - {step.name:22s} {step.status:10s} {step.message or ''}")
    if final.crawl_errors:
        print(f"crawl_errors ({len(final.crawl_errors)}):")
        for ce in final.crawl_errors[:10]:
            print(f"  - {ce.error_type:18s} {ce.url}  {ce.error_message or ''}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: run_pipeline_eval.py <url>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
