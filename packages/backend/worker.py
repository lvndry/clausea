"""Pipeline worker: claims pending jobs and runs them, out of the web process.

The web service only creates pending pipeline_jobs; this process executes them, so crawls
(Camoufox, large parsing, LLM calls) never run inside the API process. Run it as a separate
service on the same image:  uv run python worker.py

Concurrency and poll interval are env-tunable:
  PIPELINE_WORKER_CONCURRENCY  (default 2)  max jobs running at once
  PIPELINE_WORKER_POLL_SECONDS (default 3)  idle poll interval
"""

from __future__ import annotations

import asyncio
import os
import signal

from src.core.database import close_motor_client, db_session
from src.core.logging import get_logger, setup_logging
from src.repositories.pipeline_repository import PipelineRepository
from src.services.service_factory import create_pipeline_service

logger = get_logger(__name__)

_CONCURRENCY = max(1, int(os.getenv("PIPELINE_WORKER_CONCURRENCY", "2")))
_POLL_SECONDS = float(os.getenv("PIPELINE_WORKER_POLL_SECONDS", "3"))


async def _run_job(job_id: str) -> None:
    """Execute one pipeline job; run_pipeline opens and owns its own db session."""
    try:
        await create_pipeline_service().run_pipeline(job_id)
    except Exception as exc:  # noqa: BLE001 - a single job must never kill the worker
        logger.error("Worker job %s failed: %s", job_id, exc, exc_info=True)


async def main() -> None:
    setup_logging()
    repo = PipelineRepository()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    # Reap jobs orphaned by a previous crash before claiming new work.
    async with db_session() as db:
        reaped = await repo.mark_stale_as_failed(db)
        if reaped:
            logger.info("Worker startup: marked %d stale job(s) as failed", reaped)

    logger.info("Pipeline worker started (concurrency=%d, poll=%.1fs)", _CONCURRENCY, _POLL_SECONDS)
    running: set[asyncio.Task[None]] = set()

    while not stop.is_set():
        if len(running) >= _CONCURRENCY:
            await asyncio.sleep(_POLL_SECONDS)
            continue

        async with db_session() as db:
            job = await repo.claim_next_pending_job(db)

        if job is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=_POLL_SECONDS)
            except TimeoutError:
                pass
            continue

        logger.info("Claimed job %s for %s", job.id, job.product_slug)
        task = asyncio.create_task(_run_job(job.id))
        running.add(task)
        task.add_done_callback(running.discard)

    if running:
        logger.info("Shutdown: waiting for %d in-flight job(s) to finish", len(running))
        await asyncio.gather(*running, return_exceptions=True)
    close_motor_client()
    logger.info("Pipeline worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
