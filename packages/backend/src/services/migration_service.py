"""Migration orchestrator: discovers and applies pending migrations on startup.

Applied migrations are recorded in the ``_migrations`` collection (one document
per migration, keyed by ``migration_id``) so each runs exactly once per
environment. A short-lived lock document in ``_migrations_lock`` prevents two
replicas from running migrations concurrently — important on Railway where a
new replica can spin up while another is mid-migration.

A failed migration is recorded with ``status="failed"`` and re-raised, which
halts the startup sequence (readiness stays 503 until the failure is resolved).
On the next boot the failed migration is retried, because only
``status="applied"`` entries count as done.
"""

from __future__ import annotations

import os
import socket
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.core.logging import get_logger
from src.migrations import registry as default_registry
from src.migrations.registry import MigrationRegistry

logger = get_logger(__name__, component="migration")

MIGRATIONS_COLLECTION = "_migrations"
LOCK_COLLECTION = "_migrations_lock"
LOCK_ID = "migration-runner"
LOCK_TTL_SECONDS = 300


def _host_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class MigrationService:
    """Apply pending migrations in deterministic order, exactly once each."""

    def __init__(self, registry: MigrationRegistry = default_registry) -> None:
        self._registry = registry

    async def run_pending(self, db: AgnosticDatabase) -> dict[str, Any]:
        """Run every registered migration not yet recorded as applied.

        Returns a summary dict with the counts of applied and skipped migrations.
        Safe to call on every startup.
        """
        await self._ensure_schema(db)

        pending_before_lock = self._registry.pending(await self._applied_ids(db))
        if not pending_before_lock:
            logger.info("No pending migrations")
            return {"applied": 0, "skipped": 0}

        if not await self._acquire_lock(db):
            logger.info(
                "Migration lock held by another instance — skipping",
                pending=[m.migration_id for m in pending_before_lock],
            )
            return {"applied": 0, "skipped": len(pending_before_lock)}

        try:
            applied_count = 0
            for migration in self._registry.pending(await self._applied_ids(db)):
                await self._run_one(db, migration)
                applied_count += 1
            logger.info("Migrations complete", applied=applied_count)
            return {"applied": applied_count, "skipped": 0}
        finally:
            await self._release_lock(db)

    async def _run_one(self, db: AgnosticDatabase, migration: Any) -> None:
        start = time.monotonic()
        started_at = datetime.now(UTC)
        logger.info(
            "Applying migration", id=migration.migration_id, description=migration.description
        )
        try:
            detail = await migration.upgrade(db) or {}
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._record(
                db,
                migration_id=migration.migration_id,
                description=migration.description,
                status="applied",
                applied_at=started_at,
                duration_ms=duration_ms,
                detail=detail,
            )
            logger.info(
                "Migration applied",
                id=migration.migration_id,
                duration_ms=duration_ms,
                detail=detail,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._record(
                db,
                migration_id=migration.migration_id,
                description=migration.description,
                status="failed",
                applied_at=started_at,
                duration_ms=duration_ms,
                error=repr(exc),
            )
            logger.exception("Migration failed", id=migration.migration_id)
            raise

    async def _record(self, db: AgnosticDatabase, **fields: Any) -> None:
        migration_id = fields["migration_id"]
        await db[MIGRATIONS_COLLECTION].find_one_and_update(
            {"_id": migration_id},
            {"$set": fields},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def _applied_ids(self, db: AgnosticDatabase) -> set[str]:
        cursor = db[MIGRATIONS_COLLECTION].find(
            {"status": "applied"}, {"_id": 1, "migration_id": 1}
        )
        applied: set[str] = set()
        async for row in cursor:
            applied.add(row.get("migration_id") or row["_id"])
        return applied

    async def _ensure_schema(self, db: AgnosticDatabase) -> None:
        try:
            await db[MIGRATIONS_COLLECTION].create_index(
                "migration_id", unique=True, name="uniq_migration_id"
            )
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                logger.debug("Could not create migration_id index: %s", exc)

        try:
            await db[LOCK_COLLECTION].create_index(
                "locked_at",
                expireAfterSeconds=LOCK_TTL_SECONDS,
                name="ttl_migration_lock",
            )
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                logger.debug("Could not create migration lock index: %s", exc)

    async def _acquire_lock(self, db: AgnosticDatabase) -> bool:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=LOCK_TTL_SECONDS)
        # Clear any stale lock left by a crashed runner so a new instance can
        # take over immediately instead of waiting for the TTL reaper.
        await db[LOCK_COLLECTION].delete_many({"locked_at": {"$lt": cutoff}})
        try:
            await db[LOCK_COLLECTION].insert_one(
                {"_id": LOCK_ID, "locked_at": now, "host": _host_id()}
            )
            return True
        except DuplicateKeyError:
            return False

    async def _release_lock(self, db: AgnosticDatabase) -> None:
        await db[LOCK_COLLECTION].delete_one({"_id": LOCK_ID})
