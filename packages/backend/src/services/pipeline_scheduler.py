"""Shared pipeline job scheduling.

Centralises the in-process deduplication set and the background-task
scheduling logic that was previously duplicated between
``routes/pipeline.py`` and ``routes/extension.py``.
"""

from __future__ import annotations

import asyncio

from fastapi import BackgroundTasks

from src.core.logging import get_logger
from src.services.service_factory import create_pipeline_service

logger = get_logger(__name__)

_RUNNING_JOB_IDS: set[str] = set()
_RUNNING_JOB_LOCK = asyncio.Lock()


async def schedule_pipeline_run(job_id: str, background_tasks: BackgroundTasks) -> bool:
    """Best-effort scheduler for background pipeline execution.

    Idempotent per-process: repeated calls for the same *job_id* will not
    enqueue duplicate background tasks.

    Returns ``True`` if the task was newly scheduled, ``False`` if it was
    already tracked.
    """
    async with _RUNNING_JOB_LOCK:
        if job_id in _RUNNING_JOB_IDS:
            return False
        _RUNNING_JOB_IDS.add(job_id)

    main_loop = asyncio.get_running_loop()

    async def _run_pipeline_async(j_id: str) -> None:
        try:
            pipeline_svc = create_pipeline_service()
            await pipeline_svc.run_pipeline(j_id)
        except Exception as exc:
            logger.error(f"Background pipeline failed for job {j_id}: {exc}", exc_info=True)

    def _runner_sync() -> None:
        # Run the pipeline in a new event loop in a separate thread
        # to avoid blocking the main FastAPI event loop with CPU-bound work
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            new_loop.run_until_complete(_run_pipeline_async(job_id))
        finally:
            # Clean up motor client for this loop
            from src.core.database import close_motor_client

            close_motor_client(new_loop)
            new_loop.close()

            # Clean up the lock in the main loop
            async def _cleanup():
                async with _RUNNING_JOB_LOCK:
                    _RUNNING_JOB_IDS.discard(job_id)

            asyncio.run_coroutine_threadsafe(_cleanup(), main_loop)

    background_tasks.add_task(_runner_sync)
    return True
