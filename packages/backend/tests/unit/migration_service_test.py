"""Tests for the MigrationService orchestrator.

Covers the exactly-once, ordering, lock, and failure-recording guarantees
without touching a real MongoDB — the service is driven entirely through the
AgnosticDatabase protocol, so a MagicMock stand-in is sufficient.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from src.migrations.base import Migration
from src.migrations.registry import MigrationRegistry, autodiscover
from src.services.migration_service import (
    LOCK_COLLECTION,
    MIGRATIONS_COLLECTION,
    MigrationService,
)


class _StubMigration(Migration):
    def __init__(self, migration_id: str, *, fail: bool = False) -> None:
        self.migration_id = migration_id
        self.description = f"stub {migration_id}"
        self.fail = fail
        self.call_count = 0
        self.last_db: object | None = None

    async def upgrade(self, db: object) -> dict[str, object]:
        self.call_count += 1
        self.last_db = db
        if self.fail:
            raise RuntimeError("boom")
        return {"ok": True}


class _AsyncIter:
    """Minimal async iterator over a list — substitutes for a Motor cursor."""

    def __init__(self, items: list[dict]) -> None:
        self._it = iter(items)

    def __aiter__(self) -> _AsyncIter:
        return self

    async def __anext__(self) -> dict:
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


def _build_mock_db(applied_docs: list[dict] | None = None) -> MagicMock:
    """A MagicMock database that records migration/lock writes."""
    db = MagicMock()

    # _migrations collection
    migrations_col = MagicMock()
    migrations_col.find_one_and_update = AsyncMock(return_value={"_id": "x"})
    migrations_col.create_index = AsyncMock()
    # `find` must return a fresh async iterator each call — the service iterates
    # the applied-ids cursor more than once.
    migrations_col.find.side_effect = lambda *_a, **_kw: _AsyncIter(applied_docs or [])

    # lock collection
    lock_col = MagicMock()
    lock_col.insert_one = AsyncMock(return_value={"insertedId": "lock"})
    lock_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    lock_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
    lock_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    lock_col.create_index = AsyncMock()

    def _getitem(name: str) -> MagicMock:
        if name == MIGRATIONS_COLLECTION:
            return migrations_col
        if name == LOCK_COLLECTION:
            return lock_col
        return MagicMock()

    db.__getitem__.side_effect = _getitem
    return db


def _registry(*migrations: Migration) -> MigrationRegistry:
    reg = MigrationRegistry()
    for m in migrations:
        reg.register(m)
    return reg


@pytest.mark.asyncio
async def test_applies_all_pending_migrations_in_order():
    a = _StubMigration("000_a")
    b = _StubMigration("001_b")
    c = _StubMigration("002_c")
    service = MigrationService(_registry(a, b, c))
    db = _build_mock_db(applied_docs=[])

    summary = await service.run_pending(db)

    assert summary == {"applied": 3, "skipped": 0}
    assert a.call_count == 1
    assert b.call_count == 1
    assert c.call_count == 1
    # Each migration received the db handle.
    for migration in (a, b, c):
        assert migration.last_db is db


@pytest.mark.asyncio
async def test_skips_already_applied_migrations():
    a = _StubMigration("000_a")
    b = _StubMigration("001_b")
    service = MigrationService(_registry(a, b))
    db = _build_mock_db(applied_docs=[{"_id": "000_a", "migration_id": "000_a"}])

    summary = await service.run_pending(db)

    assert summary == {"applied": 1, "skipped": 0}
    assert a.call_count == 0
    assert b.call_count == 1


@pytest.mark.asyncio
async def test_records_failure_and_reraises():
    bad = _StubMigration("000_bad", fail=True)
    service = MigrationService(_registry(bad))
    db = _build_mock_db(applied_docs=[])

    with pytest.raises(RuntimeError, match="boom"):
        await service.run_pending(db)

    migrations_col = db[MIGRATIONS_COLLECTION]
    status_seen = [
        call.args[1]["$set"]["status"]
        for call in migrations_col.find_one_and_update.await_args_list
    ]
    assert "failed" in status_seen
    # And it was NOT also recorded as applied
    assert "applied" not in status_seen


@pytest.mark.asyncio
async def test_failed_migration_is_retried_on_next_boot():
    flaky = _StubMigration("000_flaky", fail=True)
    service = MigrationService(_registry(flaky))

    # First boot: fails, recorded as "failed"
    db1 = _build_mock_db(applied_docs=[])
    with pytest.raises(RuntimeError):
        await service.run_pending(db1)

    # Second boot: only "applied" docs count as done, so the failed one is pending again.
    # Simulate it failing again to prove it was retried.
    db2 = _build_mock_db(applied_docs=[])
    with pytest.raises(RuntimeError):
        await service.run_pending(db2)
    assert flaky.call_count == 2


@pytest.mark.asyncio
async def test_no_pending_migrations_returns_zero():
    a = _StubMigration("000_a")
    service = MigrationService(_registry(a))
    db = _build_mock_db(applied_docs=[{"_id": "a", "migration_id": "000_a"}])

    summary = await service.run_pending(db)

    assert summary == {"applied": 0, "skipped": 0}
    assert a.call_count == 0


@pytest.mark.asyncio
async def test_lock_held_skips_without_running():
    a = _StubMigration("000_a")
    service = MigrationService(_registry(a))
    db = _build_mock_db(applied_docs=[])
    # Pre-occupy the lock: insert_one raises DuplicateKeyError
    db[LOCK_COLLECTION].insert_one = AsyncMock(side_effect=DuplicateKeyError("taken"))

    summary = await service.run_pending(db)

    assert summary == {"applied": 0, "skipped": 1}
    assert a.call_count == 0


@pytest.mark.asyncio
async def test_lock_released_after_success():
    a = _StubMigration("000_a")
    service = MigrationService(_registry(a))
    db = _build_mock_db(applied_docs=[])

    await service.run_pending(db)

    db[LOCK_COLLECTION].delete_one.assert_awaited()


@pytest.mark.asyncio
async def test_lock_release_only_deletes_own_lock():
    """_release_lock filters by host so it never deletes another replica's lock."""
    a = _StubMigration("000_a")
    service = MigrationService(_registry(a))
    db = _build_mock_db(applied_docs=[])

    await service.run_pending(db)

    delete_filter = db[LOCK_COLLECTION].delete_one.await_args.args[0]
    assert delete_filter["_id"] == "migration-runner"
    assert "host" in delete_filter  # scoped to this process, not unscoped


@pytest.mark.asyncio
async def test_lock_refreshed_before_each_migration():
    """Each migration is preceded by a lock refresh so the TTL doesn't expire."""
    a = _StubMigration("000_a")
    b = _StubMigration("001_b")
    c = _StubMigration("002_c")
    service = MigrationService(_registry(a, b, c))
    db = _build_mock_db(applied_docs=[])

    await service.run_pending(db)

    assert db[LOCK_COLLECTION].update_one.await_count == 3
    for call in db[LOCK_COLLECTION].update_one.await_args_list:
        update_filter = call.args[0]
        assert update_filter["_id"] == "migration-runner"
        assert "host" in update_filter
        assert "locked_at" in call.args[1]["$set"]


@pytest.mark.asyncio
async def test_lock_released_after_failure():
    bad = _StubMigration("000_bad", fail=True)
    service = MigrationService(_registry(bad))
    db = _build_mock_db(applied_docs=[])

    with pytest.raises(RuntimeError):
        await service.run_pending(db)

    db[LOCK_COLLECTION].delete_one.assert_awaited()


@pytest.mark.asyncio
async def test_records_applied_with_detail_and_timing():
    a = _StubMigration("000_a")
    service = MigrationService(_registry(a))
    db = _build_mock_db(applied_docs=[])

    await service.run_pending(db)

    call = db[MIGRATIONS_COLLECTION].find_one_and_update.await_args
    fields = call.args[1]["$set"]
    assert fields["status"] == "applied"
    assert fields["migration_id"] == "000_a"
    assert fields["detail"] == {"ok": True}
    assert isinstance(fields["applied_at"], datetime)
    assert fields["applied_at"].tzinfo is UTC
    assert fields["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_registry_orders_by_migration_id_lexicographically():
    reg = _registry(
        _StubMigration("002_late"),
        _StubMigration("000_early"),
        _StubMigration("001_mid"),
    )
    ids = [m.migration_id for m in reg.all()]
    assert ids == ["000_early", "001_mid", "002_late"]


def test_autodiscover_finds_numbered_migration_files():
    """autodiscover scans the src.migrations package for NNN_*.py files."""
    discovered = autodiscover()
    ids = [m.migration_id for m in discovered]
    assert "000_rename_companies_to_products" in ids
    assert "001_fix_thin_evidence_products" in ids
    assert "002_backfill_orphan_citations" in ids
    assert "003_migrate_topic_stances" in ids
    # Files without the NNN_ prefix (e.g. fix_product_names, base, registry) are excluded.
    assert all(not mid.startswith("fix_") for mid in ids)


def test_autodiscover_returns_migrations_in_filename_order():
    discovered = autodiscover()
    ids = [m.migration_id for m in discovered]
    assert ids == sorted(ids)
