"""Pipeline worker: claims pending jobs and runs them, out of the web process.

The web service only creates pending pipeline_jobs; this process executes them, so crawls
(Camoufox, large parsing, LLM calls) never run inside the API process. Run it as a separate
service on the same image:  uv run python worker.py

Concurrency and poll interval are env-tunable:
  PIPELINE_WORKER_CONCURRENCY         (default 3)    max jobs running at once
  PIPELINE_WORKER_POLL_SECONDS        (default 3)    idle poll interval
  PIPELINE_WORKER_STALE_SWEEP_SECONDS (default 300)  how often to reap orphaned jobs
"""

from __future__ import annotations

import asyncio
import os
import signal

from aiohttp import web

from src.core.database import close_motor_client, db_session
from src.core.logging import get_logger, setup_logging
from src.repositories.monitoring_schedule_repository import MonitoringScheduleRepository
from src.repositories.pipeline_repository import (
    ORPHANABLE_PIPELINE_STATUSES,
    PipelineRepository,
    StaleReapContext,
)
from src.services.service_factory import create_pipeline_service

logger = get_logger(__name__)

# One replica shares a single Camoufox/Firefox; each concurrent crawl can render heavy
# SPA DOMs into memory. Above a handful of concurrent jobs the container OOM-kills (it died
# at ~13). Cap the effective concurrency to a memory-safe ceiling regardless of the env so a
# too-high setting can't crashloop the worker. Raise only with more RAM or more replicas.
_SAFE_CONCURRENCY_CEILING = 4
_CONCURRENCY = max(
    1, min(int(os.getenv("PIPELINE_WORKER_CONCURRENCY", "3")), _SAFE_CONCURRENCY_CEILING)
)
_POLL_SECONDS = float(os.getenv("PIPELINE_WORKER_POLL_SECONDS", "3"))
_STALE_SWEEP_SECONDS = float(os.getenv("PIPELINE_WORKER_STALE_SWEEP_SECONDS", "300"))
_MONITORING_SWEEP_SECONDS = float(os.getenv("PIPELINE_MONITORING_SWEEP_SECONDS", "3600"))
_SHUTDOWN_GRACE_SECONDS = float(os.getenv("PIPELINE_WORKER_SHUTDOWN_GRACE", "20"))
_PORT_ENV = os.getenv("PORT", "8000")
_HEALTH_PORT = int(_PORT_ENV) if _PORT_ENV.isdigit() else 8000


async def _health(_request: web.Request) -> web.Response:
    """Liveness probe — returns 200 as soon as the process is serving HTTP."""
    return web.json_response({"status": "healthy", "service": "worker"})


async def _start_health_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    # IPv4 only — worker has no inbound private-network clients; Railway healthchecks use IPv4.
    site = web.TCPSite(runner, "0.0.0.0", _HEALTH_PORT)
    await site.start()
    logger.info("Health server listening on 0.0.0.0:%d/health", _HEALTH_PORT)
    return runner


async def _cancel_zombie_tasks(running: dict[asyncio.Task[None], str]) -> int:
    """Cancel in-process tasks whose job is no longer in-progress in MongoDB.

    The stale sweep marks wedged jobs as failed in the DB but previously left the
    matching asyncio tasks running, which blocked concurrency slots until redeploy.
    """
    if not running:
        return 0

    job_ids = list(running.values())
    try:
        async with db_session() as db:
            cursor = db[PipelineRepository.COLLECTION].find(
                {"id": {"$in": job_ids}},
                {"id": 1, "status": 1},
            )
            statuses = {doc["id"]: doc["status"] async for doc in cursor}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Zombie task check failed (continuing): %s", exc)
        return 0

    orphanable = set(ORPHANABLE_PIPELINE_STATUSES)
    cancelled = 0
    for task, job_id in list(running.items()):
        status = statuses.get(job_id)
        if status in orphanable:
            continue
        if task.done():
            continue
        task.cancel()
        cancelled += 1
        logger.warning(
            "Cancelled zombie task for job %s (db status=%s)",
            job_id,
            status or "missing",
        )
    return cancelled


async def _sweep_stale(
    repo: PipelineRepository,
    running: dict[asyncio.Task[None], str] | None = None,
) -> None:
    """Self-heal the queue (boot + periodic): re-queue interrupted/failed jobs, then
    reap crash-orphaned in-progress jobs — retries are unlimited.

    Best-effort: a sweep error must never stop the worker from claiming jobs (a single
    failure here previously crashlooped the whole worker), so failures are logged, not raised.
    """
    try:
        async with db_session() as db:
            # Re-queue gracefully-interrupted jobs first. In rolling deployments a
            # sibling replica may have been SIGTERMed *after* the current worker's boot
            # sweep ran, leaving jobs stuck as status="interrupted" indefinitely. The
            # periodic sweep must close that gap so they don't wait until the next boot.
            interrupted = await repo.requeue_interrupted_jobs(db)
            reaped = await repo.mark_stale_as_failed(db, context=StaleReapContext.periodic_sweep)
            requeued = await repo.requeue_failed_jobs(db)
        if interrupted:
            logger.info("Re-queued %d interrupted job(s) for retry", interrupted)
        if reaped:
            logger.info("Reaped %d stale job(s) as failed", reaped)
        if requeued:
            logger.info("Re-queued %d failed job(s) for retry", requeued)
        if running is not None:
            zombies = await _cancel_zombie_tasks(running)
            if zombies:
                logger.info("Cancelled %d zombie in-process task(s)", zombies)
    except Exception as exc:  # noqa: BLE001 - the queue self-heal must not kill the worker
        logger.error("Stale sweep failed (continuing): %s", exc, exc_info=True)


async def _sweep_monitoring() -> None:
    try:
        monitoring_repo = MonitoringScheduleRepository()
        pipeline_svc = create_pipeline_service()
        triggered = 0
        async with db_session() as db:
            due = await monitoring_repo.find_due(db)
        for schedule in due:
            try:
                async with db_session() as db:
                    product_docs = await db.products.find_one(
                        {"slug": schedule.product_slug}, {"crawl_base_urls": 1, "domains": 1}
                    )
                if product_docs:
                    domains = product_docs.get("domains") or []
                    base_urls = product_docs.get("crawl_base_urls") or []
                    crawl_url = (
                        base_urls[0]
                        if base_urls
                        else (f"https://{domains[0]}" if domains else None)
                    )
                else:
                    crawl_url = None
                if not crawl_url:
                    async with db_session() as db:
                        await db.monitoring_schedules.update_one(
                            {"product_slug": schedule.product_slug},
                            {"$set": {"enabled": False}},
                        )
                    logger.warning(
                        "Disabled monitoring for %s: no crawl URL found", schedule.product_slug
                    )
                    continue
                async with db_session() as db:
                    await pipeline_svc.create_job_for_url(db, crawl_url)
                    await monitoring_repo.mark_triggered(db, schedule.product_slug)
                triggered += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Monitoring sweep failed for %s: %s", schedule.product_slug, exc)
        if triggered:
            logger.info("Monitoring sweep triggered %d re-crawl(s)", triggered)
    except Exception as exc:  # noqa: BLE001
        logger.error("Monitoring sweep failed (continuing): %s", exc, exc_info=True)


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
    health_runner = await _start_health_server()
    try:
        repo = PipelineRepository()

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass  # add_signal_handler is unavailable on Windows; signals are a Unix/prod concern

        await _run_worker_loop(repo, stop, loop)
    finally:
        await health_runner.cleanup()


async def _run_worker_loop(
    repo: PipelineRepository, stop: asyncio.Event, loop: asyncio.AbstractEventLoop
) -> None:
    # Reap jobs orphaned by a previous crash/redeploy before claiming new work.
    # We use a 2-minute threshold (not 0) so that sibling replicas starting within
    # seconds of each other don't orphan each other's freshly-claimed jobs.  Any
    # job running for more than 2 minutes when this replica boots was owned by a
    # genuinely dead process and should be reset.  The periodic sweep (every 5 min)
    # catches the rare case where a crash happens within that 2-minute window.
    async with db_session() as db:
        # First priority: re-queue jobs that were gracefully interrupted by the
        # previous worker process. These are always retryable — they were cut short
        # by SIGTERM, not by a code bug.
        interrupted = await repo.requeue_interrupted_jobs(db)
        if interrupted:
            logger.info("Boot sweep: re-queued %d interrupted job(s)", interrupted)
        # Then reap any stale jobs that weren't caught by the graceful shutdown.
        boot_reaped = await repo.mark_stale_as_failed(
            db, stale_threshold_minutes=2, context=StaleReapContext.worker_boot
        )
        if boot_reaped:
            async with db_session() as db2:
                requeued = await repo.requeue_failed_jobs(db2)
            if boot_reaped or requeued:
                logger.info(
                    "Boot sweep: reset %d orphaned job(s), re-queued %d failed",
                    boot_reaped,
                    requeued,
                )
    last_sweep = loop.time()
    last_monitoring_sweep = loop.time()

    logger.info("Pipeline worker started (concurrency=%d, poll=%.1fs)", _CONCURRENCY, _POLL_SECONDS)
    running: dict[asyncio.Task[None], str] = {}

    while not stop.is_set():
        if loop.time() - last_sweep >= _STALE_SWEEP_SECONDS:
            await _sweep_stale(repo, running)
            last_sweep = loop.time()

        if loop.time() - last_monitoring_sweep >= _MONITORING_SWEEP_SECONDS:
            await _sweep_monitoring()
            last_monitoring_sweep = loop.time()

        if len(running) >= _CONCURRENCY:
            # Stale sweep may have failed jobs in DB while asyncio tasks still hold slots.
            await _cancel_zombie_tasks(running)
            await _sleep_or_stop(stop, _POLL_SECONDS)
            continue

        async with db_session() as db:
            job = await repo.claim_next_pending_job(db)

        if job is None:
            await _sleep_or_stop(stop, _POLL_SECONDS)
            continue

        logger.info("Claimed job %s for %s", job.id, job.product_slug)
        task = asyncio.create_task(_run_job(job.id))
        running[task] = job.id
        task.add_done_callback(running.pop)

    # Graceful shutdown: mark in-flight jobs as interrupted so they can be
    # re-queued immediately on the next boot, then cancel tasks after grace period.
    if running:
        in_flight_ids = list(running.values())
        logger.info(
            "Shutdown: marking %d in-flight job(s) as interrupted",
            len(in_flight_ids),
        )
        try:
            async with db_session() as db:
                await repo.mark_interrupted(db, in_flight_ids)
        except Exception:
            logger.warning("Failed to mark interrupted jobs; falling back to cancellation")

        logger.info(
            "Shutdown: waiting up to %.0fs for %d in-flight job(s) to finish",
            _SHUTDOWN_GRACE_SECONDS,
            len(running),
        )
        try:
            await asyncio.wait_for(
                asyncio.gather(*running, return_exceptions=True),
                timeout=_SHUTDOWN_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("Shutdown grace exceeded; cancelling %d in-flight job(s)", len(running))
            for task in running:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)
    close_motor_client()
    logger.info("Pipeline worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
