"""Pipeline worker: claims pending jobs and runs them, out of the web process.

The web service only creates pending pipeline_jobs; this process executes them, so crawls
(Camoufox, large parsing, LLM calls) never run inside the API process. Run it as a separate
service on the same image:  uv run python worker.py

Concurrency and poll interval are env-tunable:
  PIPELINE_WORKER_CONCURRENCY         (default 2)    max jobs running at once
  PIPELINE_WORKER_POLL_SECONDS        (default 3)    idle poll interval
  PIPELINE_WORKER_STALE_SWEEP_SECONDS (default 300)  how often to reap orphaned jobs
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
_STALE_SWEEP_SECONDS = float(os.getenv("PIPELINE_WORKER_STALE_SWEEP_SECONDS", "300"))


async def _sweep_stale(repo: PipelineRepository) -> None:
    """Reap jobs orphaned by a crash. Runs at startup and periodically: mark_stale only
    catches jobs already past the staleness threshold, so a one-shot boot sweep leaves jobs
    orphaned shortly before the restart stuck until the next boot. Active jobs refresh their
    timestamp well within the threshold, so a running job is never reaped."""
    async with db_session() as db:
        reaped = await repo.mark_stale_as_failed(db)
    if reaped:
        logger.info("Reaped %d stale job(s) as failed", reaped)


async def _run_job(job_id: str) -> None:
    """Execute one pipeline job; run_pipeline opens and owns its own db session."""
    try:
        await create_pipeline_service().run_pipeline(job_id)
    except Exception as exc:  # noqa: BLE001 - a single job must never kill the worker
        logger.error("Worker job %s failed: %s", job_id, exc, exc_info=True)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    """Wait up to `seconds`, returning early if shutdown was signalled."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def main() -> None:
    setup_logging()
    repo = PipelineRepository()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # add_signal_handler is unavailable on Windows; signals are a Unix/prod concern

    # Reap jobs orphaned by a previous crash before claiming new work.
    await _sweep_stale(repo)
    last_sweep = loop.time()

    logger.info("Pipeline worker started (concurrency=%d, poll=%.1fs)", _CONCURRENCY, _POLL_SECONDS)
    running: set[asyncio.Task[None]] = set()

    while not stop.is_set():
        if loop.time() - last_sweep >= _STALE_SWEEP_SECONDS:
            await _sweep_stale(repo)
            last_sweep = loop.time()

        if len(running) >= _CONCURRENCY:
            await _sleep_or_stop(stop, _POLL_SECONDS)
            continue

        async with db_session() as db:
            job = await repo.claim_next_pending_job(db)

        if job is None:
            await _sleep_or_stop(stop, _POLL_SECONDS)
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
