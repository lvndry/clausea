"""Worker must cancel in-process tasks when the DB no longer shows them as in-progress."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker import _cancel_zombie_tasks


class _FakeCursor:
    def __init__(self, docs: list[dict[str, str]]) -> None:
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_cancel_zombie_tasks_cancels_failed_jobs() -> None:
    async def _hang_forever() -> None:
        await asyncio.Event().wait()

    task_alive = asyncio.create_task(_hang_forever())
    task_done = asyncio.create_task(asyncio.sleep(0))
    await task_done

    running = {
        task_alive: "job-still-running",
        task_done: "job-already-done",
    }

    collection = MagicMock()
    collection.find.return_value = _FakeCursor(
        [
            {"id": "job-still-running", "status": "failed"},
            {"id": "job-already-done", "status": "failed"},
        ]
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    with patch("worker.db_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
        cancelled = await _cancel_zombie_tasks(running)

    assert cancelled == 1
    await asyncio.sleep(0)
    assert task_alive.cancelled() or task_alive.cancelling()
    task_alive.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task_alive


@pytest.mark.asyncio
async def test_cancel_zombie_tasks_leaves_in_progress_jobs() -> None:
    async def _hang_forever() -> None:
        await asyncio.Event().wait()

    task = asyncio.create_task(_hang_forever())
    running = {task: "job-active"}

    collection = MagicMock()
    collection.find.return_value = _FakeCursor([{"id": "job-active", "status": "synthesising"}])
    db = MagicMock()
    db.__getitem__.return_value = collection

    with patch("worker.db_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
        cancelled = await _cancel_zombie_tasks(running)

    assert cancelled == 0
    assert not task.cancelled()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
