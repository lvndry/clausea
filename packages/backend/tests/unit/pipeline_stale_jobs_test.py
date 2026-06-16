"""A worker restart must not fail queued (pending) jobs.

mark_stale_as_failed recovers jobs orphaned by a crash. A "pending" job is only queued —
never started — so a restart must leave it pending for the worker to pick up. Failing the
whole backlog on every restart would be fatal for a large re-run.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.pipeline_repository import PipelineRepository


@pytest.mark.asyncio
async def test_mark_stale_targets_only_in_progress_not_pending():
    collection = MagicMock()
    collection.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    db = MagicMock()
    db.__getitem__.return_value = collection

    await PipelineRepository().mark_stale_as_failed(db)

    eligible = collection.update_many.call_args.args[0]["status"]["$in"]
    # A queued job was never started, so a restart must not fail it.
    assert "pending" not in eligible
    # Only actively-executing statuses can be orphaned by a crash.
    assert set(eligible) == {"crawling", "summarizing", "generating_overview"}


def _failed_jobs_collection(active_slugs, candidates):
    """Mock collection: distinct() returns active slugs, find().to_list() returns candidates."""
    collection = MagicMock()
    collection.distinct = AsyncMock(return_value=active_slugs)
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=candidates)
    collection.find = MagicMock(return_value=cursor)
    collection.update_one = AsyncMock()
    return collection


@pytest.mark.asyncio
async def test_requeue_failed_retries_unlimited_regardless_of_attempts():
    # Retries are unlimited: a job mostly accrues attempts from redeploys orphaning long
    # crawls, not real defects, so there is no attempt ceiling. Even a high-attempt job
    # must be requeued.
    collection = _failed_jobs_collection(
        active_slugs=[],
        candidates=[
            {"id": "a", "product_slug": "alpha", "attempts": 1},
            {"id": "b", "product_slug": "beta", "attempts": 99},
        ],
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    requeued = await PipelineRepository().requeue_failed_jobs(db)

    query = collection.find.call_args.args[0]
    # Only failed jobs are retried; no_documents stays terminal.
    assert query["status"] == "failed"
    # No attempt cap: the query must not filter on attempts at all.
    assert "$or" not in query
    assert "attempts" not in query
    update = collection.update_one.call_args.args[1]
    assert update["$set"]["status"] == "pending"
    # Steps reset so a retry doesn't carry stale terminal step state.
    assert all(s["status"] == "pending" for s in update["$set"]["steps"])
    # The 99-attempt job is requeued too.
    assert requeued == 2


@pytest.mark.asyncio
async def test_requeue_never_creates_second_active_job_per_product():
    # Regression: reactivating a failed job for a product that already has an active job (or
    # a second failed job for the same product) violates uniq_active_job_per_product and
    # previously crashed the worker on boot.
    collection = _failed_jobs_collection(
        active_slugs=["foo"],  # foo already has an active job
        candidates=[
            {"id": "1", "product_slug": "foo"},  # skipped — already active
            {"id": "2", "product_slug": "bar"},  # requeued
            {"id": "3", "product_slug": "bar"},  # skipped — bar already revived above
            {"id": "4", "product_slug": "baz"},  # requeued
        ],
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    requeued = await PipelineRepository().requeue_failed_jobs(db)

    assert requeued == 2
    revived_ids = {call.args[0]["id"] for call in collection.update_one.call_args_list}
    assert revived_ids == {"2", "4"}
