"""Worker must cancel in-process tasks when the DB no longer shows them as in-progress."""

from __future__ import annotations

import asyncio
import contextlib
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


class _SlowCursor:
    """Yields after an await so callers can mutate `running` mid-query."""

    def __init__(self, docs: list[dict[str, str]], on_first_row: asyncio.Event) -> None:
        self._docs = docs
        self._on_first_row = on_first_row

    def __aiter__(self):
        self._iter = iter(self._docs)
        self._first = True
        return self

    async def __anext__(self):
        if self._first:
            self._first = False
            self._on_first_row.set()
            await asyncio.sleep(0)
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


async def _cancel_hanging_task(task: asyncio.Task[None]) -> None:
    if not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_cancel_zombie_tasks_cancels_failed_jobs() -> None:
    async def _hang_forever() -> None:
        await asyncio.Event().wait()

    zombie_task = asyncio.create_task(_hang_forever())
    finished_task = asyncio.create_task(asyncio.sleep(0))
    await finished_task

    running = {
        zombie_task: "job-zombie",
        finished_task: "job-finished",
    }

    collection = MagicMock()
    collection.find.return_value = _FakeCursor(
        [
            {"id": "job-zombie", "status": "failed"},
            {"id": "job-finished", "status": "failed"},
        ]
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    try:
        with patch("worker.db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            cancelled = await _cancel_zombie_tasks(running)

        assert cancelled == 1
        await asyncio.sleep(0)
        assert zombie_task.cancelled() or zombie_task.cancelling()
    finally:
        await _cancel_hanging_task(zombie_task)


@pytest.mark.asyncio
async def test_cancel_zombie_tasks_leaves_in_progress_jobs() -> None:
    async def _hang_forever() -> None:
        await asyncio.Event().wait()

    active_task = asyncio.create_task(_hang_forever())
    running = {active_task: "job-active"}

    collection = MagicMock()
    collection.find.return_value = _FakeCursor([{"id": "job-active", "status": "synthesising"}])
    db = MagicMock()
    db.__getitem__.return_value = collection

    try:
        with patch("worker.db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            cancelled = await _cancel_zombie_tasks(running)

        assert cancelled == 0
        assert not active_task.cancelled()
        assert not active_task.cancelling()
    finally:
        await _cancel_hanging_task(active_task)


@pytest.mark.asyncio
async def test_cancel_zombie_tasks_does_not_cancel_tasks_added_during_db_query() -> None:
    async def _hang_forever() -> None:
        await asyncio.Event().wait()

    zombie_task = asyncio.create_task(_hang_forever())
    running = {zombie_task: "job-zombie"}
    gate = asyncio.Event()
    new_task: asyncio.Task[None] | None = None

    collection = MagicMock()
    collection.find.return_value = _SlowCursor(
        [{"id": "job-zombie", "status": "failed"}],
        gate,
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    async def _add_task_mid_query() -> None:
        nonlocal new_task
        await gate.wait()
        new_task = asyncio.create_task(_hang_forever())
        running[new_task] = "job-new"

    add_task = asyncio.create_task(_add_task_mid_query())

    try:
        with patch("worker.db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            cancelled = await _cancel_zombie_tasks(running)

        await add_task
        assert new_task is not None
        assert cancelled == 1
        assert zombie_task.cancelled() or zombie_task.cancelling()
        assert not new_task.cancelled()
        assert not new_task.cancelling()
    finally:
        add_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await add_task
        await _cancel_hanging_task(zombie_task)
        if new_task is not None:
            await _cancel_hanging_task(new_task)
