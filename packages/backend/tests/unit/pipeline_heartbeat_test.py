"""Crawl-progress updates refresh the job heartbeat so steady progress keeps it alive.

The stall guard cancels a job whose updated_at goes stale; the cross-process sweeper prefers
last_heartbeat. A per-page progress update therefore writes both, even when the monotonic
progress clamp leaves no other field changed, so a slow-but-advancing crawl is never killed.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.pipeline_job import PipelineJob
from src.repositories.pipeline_repository import PipelineRepository
from src.services.pipeline_service import PipelineService


def _job() -> PipelineJob:
    return PipelineJob(product_slug="x", product_name="X", url="https://x.com", status="crawling")


@pytest.mark.asyncio
async def test_progress_update_bumps_last_heartbeat():
    repo = MagicMock(spec=PipelineRepository)
    repo.update_fields = AsyncMock(return_value=None)
    svc = PipelineService(pipeline_repo=repo)
    job = _job()

    await svc._update_step_progress(
        MagicMock(), job, "crawling", current=10, total=100, message="Crawling..."
    )

    assert repo.update_fields.await_count == 1
    _db, job_id, fields = repo.update_fields.await_args.args
    assert job_id == job.id
    assert "last_heartbeat" in fields
    assert job.last_heartbeat is not None
    # update_fields itself also bumps updated_at, the field the in-process stall guard reads.


@pytest.mark.asyncio
async def test_repeat_progress_at_clamped_percent_still_heartbeats():
    """Even when the monotonic clamp blocks a percent change, the heartbeat still fires."""
    repo = MagicMock(spec=PipelineRepository)
    repo.update_fields = AsyncMock(return_value=None)
    svc = PipelineService(pipeline_repo=repo)
    job = _job()

    # First update advances the high-water mark.
    await svc._update_step_progress(MagicMock(), job, "crawling", current=80, total=100)
    # Second update would move the bar backwards (frontier grew); percent is clamped, but the
    # crawl is still making progress and must keep the job alive.
    await svc._update_step_progress(MagicMock(), job, "crawling", current=80, total=200)

    assert repo.update_fields.await_count == 2
    _db, _job_id, fields = repo.update_fields.await_args.args
    assert "last_heartbeat" in fields


@pytest.mark.asyncio
async def test_terminal_step_progress_does_not_heartbeat():
    """A late progress update for a finished step is dropped — no heartbeat, no overwrite."""
    repo = MagicMock(spec=PipelineRepository)
    repo.update_fields = AsyncMock(return_value=None)
    svc = PipelineService(pipeline_repo=repo)
    job = _job()
    job.steps[0].status = "completed"

    await svc._update_step_progress(MagicMock(), job, "crawling", current=10, total=100)

    repo.update_fields.assert_not_awaited()
