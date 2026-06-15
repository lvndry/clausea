"""A worker restart must not fail queued (pending) jobs.

mark_stale_as_failed recovers jobs orphaned by a crash. A "pending" job is only queued —
never started — so a restart must leave it pending for the worker to pick up. Failing the
whole backlog on every restart would be fatal for a large re-run.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.pipeline_repository import _ORPHANABLE_STATUSES, PipelineRepository


@pytest.mark.asyncio
async def test_mark_stale_targets_only_in_progress_not_pending():
    collection = MagicMock()
    collection.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    db = MagicMock()
    db.__getitem__.return_value = collection

    await PipelineRepository().mark_stale_as_failed(db)

    query = collection.update_many.call_args.args[0]
    assert query["status"] == {"$in": _ORPHANABLE_STATUSES}
    assert "pending" not in _ORPHANABLE_STATUSES
    # The orphanable set is exactly the actively-executing statuses.
    assert set(_ORPHANABLE_STATUSES) == {"crawling", "summarizing", "generating_overview"}
