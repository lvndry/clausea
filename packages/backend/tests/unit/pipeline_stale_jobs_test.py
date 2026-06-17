"""A worker restart must not fail queued (pending) jobs.

mark_stale_as_failed recovers jobs orphaned by a crash. A "pending" job is only queued —
never started — so a restart must leave it pending for the worker to pick up. Failing the
whole backlog on every restart would be fatal for a large re-run.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.pipeline_job import PipelineErrorCode
from src.repositories import pipeline_repository as pr
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
    assert set(eligible) == {"crawling", "synthesising", "generating_overview"}


def _failed_jobs_collection(active_slugs, candidates):
    """Mock collection: distinct() returns active slugs, find().to_list() returns candidates."""
    collection = MagicMock()
    collection.distinct = AsyncMock(return_value=active_slugs)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=candidates)
    collection.find = MagicMock(return_value=cursor)
    collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return collection


@pytest.mark.asyncio
async def test_requeue_failed_respects_retry_policy(monkeypatch):
    monkeypatch.setattr(pr, "MAX_AUTO_RETRY_ATTEMPTS", 3)

    collection = _failed_jobs_collection(
        active_slugs=[],
        candidates=[
            {
                "id": "a",
                "product_slug": "alpha",
                "attempts": 1,
                "error": PipelineErrorCode.internal_error.value,
            },
            {
                "id": "b",
                "product_slug": "beta",
                "attempts": 3,
                "error": PipelineErrorCode.internal_error.value,
            },
            {
                "id": "c",
                "product_slug": "gamma",
                "attempts": 1,
                "error": PipelineErrorCode.no_documents_found.value,
            },
            {"id": "d", "product_slug": "delta", "attempts": 1, "error": "Cancelled by user"},
        ],
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    requeued = await PipelineRepository().requeue_failed_jobs(db)

    query = collection.find.call_args.args[0]
    # Only failed/non-active/non-disabled jobs are considered.
    assert query["status"] == "failed"
    assert query["active"] == {"$ne": True}
    assert query["auto_retry_disabled"] == {"$ne": True}
    assert "attempts" not in query
    # One retryable + under-budget job was requeued.
    assert requeued == 1

    by_id = {
        call.args[0]["id"]: call.args[1]["$set"] for call in collection.update_one.call_args_list
    }
    assert by_id["a"]["status"] == "pending"
    assert by_id["b"]["auto_retry_disabled"] is True
    assert "attempt limit reached" in by_id["b"]["auto_retry_disabled_reason"]
    assert by_id["c"]["auto_retry_disabled"] is True
    assert "non-retryable failure" in by_id["c"]["auto_retry_disabled_reason"]
    assert by_id["d"]["auto_retry_disabled"] is True


@pytest.mark.asyncio
async def test_requeue_failed_resets_attempt_local_crawl_state():
    collection = _failed_jobs_collection(
        active_slugs=[],
        candidates=[
            {
                "id": "a",
                "product_slug": "alpha",
                "attempts": 1,
                "error": PipelineErrorCode.internal_error.value,
                "documents_found": 42,
                "documents_stored": 7,
                "crawl_errors": [{"url": "https://example.com/p", "error_type": "http_error"}],
                "crawl_skip_reasons": [
                    {"url": "https://example.com/t", "reason": "non_policy_classification"}
                ],
            }
        ],
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    requeued = await PipelineRepository().requeue_failed_jobs(db)

    assert requeued == 1
    update = collection.update_one.call_args.args[1]["$set"]
    assert update["status"] == "pending"
    assert update["documents_found"] == 0
    assert update["documents_stored"] == 0
    assert update["crawl_errors"] == []
    assert update["crawl_skip_reasons"] == []
    assert all(step["status"] == "pending" for step in update["steps"])


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
