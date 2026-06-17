"""Pipeline job repository for tracking background pipeline executions."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.core.logging import get_logger
from src.models.pipeline_job import TERMINAL_PIPELINE_STATUSES, PipelineErrorCode, PipelineJob
from src.repositories.base_repository import BaseRepository

_TERMINAL_STATUSES = list(TERMINAL_PIPELINE_STATUSES)

# Statuses for a job that was actively executing and can be left orphaned by a worker
# crash. A "pending" job is only queued — never started — so a restart must leave it
# pending for the worker to pick up, not fail it. Only these can be marked stale.
_ORPHANABLE_STATUSES = ["crawling", "summarizing", "generating_overview"]

logger = get_logger(__name__)

_RETRYABLE_PIPELINE_ERRORS = {
    PipelineErrorCode.crawl_failed.value,
    PipelineErrorCode.all_analysis_failed.value,
    PipelineErrorCode.core_docs_unanalyzed.value,
    PipelineErrorCode.overview_not_persisted.value,
    PipelineErrorCode.internal_error.value,
    PipelineErrorCode.timed_out.value,
    PipelineErrorCode.stalled.value,
}
_NON_RETRYABLE_PIPELINE_ERRORS = {
    PipelineErrorCode.product_not_found.value,
    PipelineErrorCode.crawl_robots_blocked.value,
    PipelineErrorCode.no_documents_found.value,
}


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r (must be int), using default=%d", name, raw, default)
        return default


# Recall-first default: allow enough auto-retry headroom to recover from transient
# crawler/render/LLM failures before quarantining a job as poison.
MAX_AUTO_RETRY_ATTEMPTS = _read_positive_int_env("PIPELINE_MAX_AUTO_RETRY_ATTEMPTS", 12)
MAX_REQUEUE_BATCH_SIZE = _read_positive_int_env("PIPELINE_REQUEUE_BATCH_SIZE", 200)


def _is_auto_retryable_failure(error_code: Any) -> bool:
    """Best-effort retryability classifier for failed jobs.

    We keep this forgiving for backward compatibility with historical rows that
    store free-form strings in ``error``.
    """
    code = (str(error_code).strip().lower() if error_code is not None else "")
    if not code:
        return True
    if code in _NON_RETRYABLE_PIPELINE_ERRORS:
        return False
    if code in _RETRYABLE_PIPELINE_ERRORS:
        return True
    # Legacy rows may store free-text values.
    if code in {"cancelled", "canceled", "cancelled by user", "canceled by user"}:
        return False
    if "orphaned" in code:
        return True
    return True


def _retry_block_reason(job: dict[str, Any]) -> str | None:
    attempts = int(job.get("attempts") or 0)
    if attempts >= MAX_AUTO_RETRY_ATTEMPTS:
        return f"attempt limit reached ({attempts}/{MAX_AUTO_RETRY_ATTEMPTS})"
    if not _is_auto_retryable_failure(job.get("error")):
        return f"non-retryable failure ({job.get('error') or 'unknown'})"
    return None


class PipelineRepository(BaseRepository):
    """Repository for pipeline job database operations."""

    COLLECTION = "pipeline_jobs"

    # TODO: Migrate queries from product_slug to product_id for referential integrity

    async def create(self, db: AgnosticDatabase, job: PipelineJob) -> PipelineJob:
        """Insert a new pipeline job.

        Args:
            db: Database instance
            job: PipelineJob to create

        Returns:
            The created PipelineJob
        """
        await db[self.COLLECTION].insert_one(job.model_dump())
        logger.debug(f"Created pipeline job {job.id} for {job.product_slug}")
        return job

    async def find_or_create_active(
        self, db: AgnosticDatabase, job: PipelineJob
    ) -> tuple[PipelineJob, bool]:
        """Atomically find an active job or create a new one.

        Returns (job, created) tuple.
        """
        new_id = job.id
        payload = job.model_dump()
        payload["active"] = True  # a freshly created job is always active
        try:
            existing: dict[str, Any] | None = await db[self.COLLECTION].find_one_and_update(
                {"product_slug": job.product_slug, "active": True},
                {"$setOnInsert": payload},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # A concurrent caller won the insert race; the partial unique index rejected
            # our insert. Return the active job that already exists.
            existing = await db[self.COLLECTION].find_one(
                {"product_slug": job.product_slug, "active": True}
            )
        if existing is None:
            raise RuntimeError(
                f"find_or_create_active returned no document for product_slug={job.product_slug}"
            )
        created = existing.get("id") == new_id
        return PipelineJob(**existing), created

    async def find_by_id(self, db: AgnosticDatabase, job_id: str) -> PipelineJob | None:
        """Get a pipeline job by its ID.

        Args:
            db: Database instance
            job_id: Job ID

        Returns:
            PipelineJob or None if not found
        """
        data: dict[str, Any] | None = await db[self.COLLECTION].find_one({"id": job_id})
        if not data:
            return None
        return PipelineJob(**data)

    async def claim_next_pending_job(self, db: AgnosticDatabase) -> PipelineJob | None:
        """Atomically claim the oldest pending job for execution by a worker.

        Flips status pending -> crawling in one step so two workers (or concurrent claim
        loops) never pick up the same job. Returns the claimed job, or None if none pending.
        """
        data: dict[str, Any] | None = await db[self.COLLECTION].find_one_and_update(
            {"status": "pending"},
            {
                "$set": {"status": "crawling", "started_at": datetime.now(), "active": True},
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not data:
            return None
        return PipelineJob(**data)

    async def find_by_product_slug(
        self, db: AgnosticDatabase, product_slug: str
    ) -> list[PipelineJob]:
        """Get all pipeline jobs for a product, ordered by creation date descending.

        Args:
            db: Database instance
            product_slug: Product slug

        Returns:
            List of PipelineJob instances
        """
        cursor = db[self.COLLECTION].find({"product_slug": product_slug}).sort("created_at", -1)
        results: list[dict[str, Any]] = await cursor.to_list(length=50)
        return [PipelineJob(**item) for item in results]

    async def find_active_by_product_slug(
        self, db: AgnosticDatabase, product_slug: str
    ) -> PipelineJob | None:
        """Get the active (non-terminal) pipeline job for a product.

        Args:
            db: Database instance
            product_slug: Product slug

        Returns:
            PipelineJob or None if no active job
        """
        data: dict[str, Any] | None = await db[self.COLLECTION].find_one(
            {
                "product_slug": product_slug,
                "status": {"$nin": _TERMINAL_STATUSES},
            }
        )
        if not data:
            return None
        return PipelineJob(**data)

    async def update(self, db: AgnosticDatabase, job: PipelineJob) -> None:
        """Update a pipeline job.

        Args:
            db: Database instance
            job: PipelineJob with updated fields
        """
        job.updated_at = datetime.now()
        payload = job.model_dump()
        # Keep the index discriminator in sync with status on every write (status may
        # have been reassigned after construction, which doesn't re-derive `active`).
        payload["active"] = job.status not in _TERMINAL_STATUSES
        await db[self.COLLECTION].update_one(
            {"id": job.id},
            {"$set": payload},
        )
        logger.debug(f"Updated pipeline job {job.id} -> status={job.status}")

    async def update_fields(
        self, db: AgnosticDatabase, job_id: str, fields: dict[str, Any]
    ) -> None:
        """Update specific fields of a pipeline job.

        Args:
            db: Database instance
            job_id: Job ID
            fields: Dictionary of fields to update (supports dot notation)
        """
        status = fields.get("status")
        if isinstance(status, str):
            # Keep the active-index discriminator consistent whenever status is patched.
            fields["active"] = status not in _TERMINAL_STATUSES
        fields["updated_at"] = datetime.now()
        await db[self.COLLECTION].update_one(
            {"id": job_id},
            {"$set": fields},
        )
        logger.debug(f"Partially updated pipeline job {job_id}: {list(fields.keys())}")

    async def requeue_failed_jobs(self, db: AgnosticDatabase) -> int:
        """Re-queue retryable failed jobs for another attempt.

        Makes the worker self-healing: orphaned jobs (failed by mark_stale_as_failed) and
        transient failures retry. ``no_documents`` and other deterministic failures remain
        terminal. Retries are bounded by ``PIPELINE_MAX_AUTO_RETRY_ATTEMPTS`` so poison jobs
        don't churn indefinitely.

        At most one active job per product (enforced by the uniq_active_job_per_product
        partial index): products that already have an active job are skipped, and only one
        failed job per remaining product is revived — reactivating a second would raise a
        DuplicateKeyError.
        """
        fresh_steps = [
            {
                "name": name,
                "status": "pending",
                "message": None,
                "progress_current": None,
                "progress_total": None,
                "progress_percent": None,
                "started_at": None,
                "completed_at": None,
            }
            for name in ("crawling", "summarizing", "generating_overview")
        ]
        claimed_slugs: set[str] = set(
            await db[self.COLLECTION].distinct("product_slug", {"active": True})
        )
        query: dict[str, Any] = {
            "status": "failed",
            "active": {"$ne": True},
            "auto_retry_disabled": {"$ne": True},
        }
        cursor = db[self.COLLECTION].find(query).sort("updated_at", 1)
        candidates: list[dict[str, Any]] = await cursor.to_list(length=MAX_REQUEUE_BATCH_SIZE)

        count = 0
        for job in candidates:
            reason = _retry_block_reason(job)
            if reason:
                await db[self.COLLECTION].update_one(
                    {"id": job["id"], "status": "failed", "active": {"$ne": True}},
                    {
                        "$set": {
                            "auto_retry_disabled": True,
                            "auto_retry_disabled_reason": reason,
                            "updated_at": datetime.now(),
                        }
                    },
                )
                continue
            slug = job["product_slug"]
            if slug in claimed_slugs:  # product already has (or just got) an active job
                continue
            claimed_slugs.add(slug)
            try:
                result = await db[self.COLLECTION].update_one(
                    {
                        "id": job["id"],
                        "status": "failed",
                        "active": {"$ne": True},
                        "auto_retry_disabled": {"$ne": True},
                    },
                    {
                        "$set": {
                            "status": "pending",
                            "active": True,
                            "steps": fresh_steps,
                            "error": None,
                            "error_detail": None,
                            "started_at": None,
                            "completed_at": None,
                            "last_heartbeat": None,
                            "documents_found": 0,
                            "documents_stored": 0,
                            "crawl_errors": [],
                            "crawl_skip_reasons": [],
                            "auto_retry_disabled": False,
                            "auto_retry_disabled_reason": None,
                            "updated_at": datetime.now(),
                        }
                    },
                )
            except DuplicateKeyError:
                # Another worker revived/claimed this product concurrently.
                logger.debug(
                    "Skipped requeue for %s/%s due to concurrent active-job claim",
                    slug,
                    job["id"],
                )
                continue
            if result.modified_count:
                count += 1
        if count:
            logger.info("Re-queued %d failed job(s) for retry", count)
        return count

    async def mark_stale_as_failed(
        self, db: AgnosticDatabase, stale_threshold_minutes: int = 30
    ) -> int:
        """Mark stale in-progress jobs older than the threshold as failed.

        Used on startup to recover from server crashes that left jobs orphaned.
        Uses last_heartbeat if available, otherwise falls back to updated_at.

        Only jobs that were actively executing are eligible — "pending" jobs are queued,
        not orphaned, so a restart leaves them for the worker to pick up rather than
        failing the whole backlog.

        Returns the number of jobs marked as failed.
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(minutes=stale_threshold_minutes)
        result = await db[self.COLLECTION].update_many(
            {
                "status": {"$in": _ORPHANABLE_STATUSES},
                "$or": [
                    {"last_heartbeat": {"$lt": cutoff}},
                    {"last_heartbeat": None, "updated_at": {"$lt": cutoff}},
                    {"last_heartbeat": {"$exists": False}, "updated_at": {"$lt": cutoff}},
                ],
            },
            {
                "$set": {
                    "status": "failed",
                    "active": False,
                    "error": "Server restart — job was orphaned",
                    "auto_retry_disabled": False,
                    "auto_retry_disabled_reason": None,
                    "updated_at": datetime.now(),
                    "completed_at": datetime.now(),
                }
            },
        )
        count = result.modified_count
        if count:
            logger.warning(f"Marked {count} stale pipeline job(s) as failed on startup")
        return count
