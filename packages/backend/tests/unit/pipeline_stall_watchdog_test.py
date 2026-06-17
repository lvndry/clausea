"""The stall watchdog cancels a wedged pipeline but never a progressing one.

It bounds *inactivity* (no page/doc/step update), not total runtime, so a slow-but-advancing
pipeline runs to the hard ceiling while a stuck one frees its worker slot fast.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.pipeline_job import PipelineJob, PipelineJobStatus
from src.repositories.pipeline_repository import PipelineRepository
from src.services import pipeline_service as ps
from src.services.pipeline_service import PipelineService, _PipelineStalled


def _job(status: PipelineJobStatus, updated_at: datetime) -> PipelineJob:
    job = PipelineJob(product_slug="x", product_name="X", url="https://x.com", status=status)
    job.updated_at = updated_at
    return job


@asynccontextmanager
async def _fake_session():
    yield MagicMock()


@pytest.mark.asyncio
async def test_stall_guard_cancels_a_stuck_pipeline(monkeypatch):
    monkeypatch.setattr(ps, "STALL_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(ps, "db_session", _fake_session)
    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=_job("crawling", datetime.now() - timedelta(hours=1)))
    svc = PipelineService(pipeline_repo=repo)

    cancelled = asyncio.Event()

    async def never_progresses() -> None:
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    core = asyncio.create_task(never_progresses())
    with pytest.raises(_PipelineStalled):
        await svc._await_with_stall_guard(core, "job-x", datetime.now() - timedelta(hours=1))
    assert cancelled.is_set()  # the wedged core was cancelled → worker slot freed


@pytest.mark.asyncio
async def test_stall_guard_lets_a_progressing_pipeline_finish(monkeypatch):
    monkeypatch.setattr(ps, "STALL_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(ps, "db_session", _fake_session)
    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=_job("synthesising", datetime.now()))
    svc = PipelineService(pipeline_repo=repo)

    async def finishes_quickly() -> None:
        await asyncio.sleep(0.05)

    core = asyncio.create_task(finishes_quickly())
    await svc._await_with_stall_guard(core, "job-x", datetime.now())  # no raise
    assert core.done() and core.exception() is None
