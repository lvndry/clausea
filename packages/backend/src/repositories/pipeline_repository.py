"""Pipeline job repository for tracking background pipeline executions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument

from src.core.logging import get_logger
from src.models.pipeline_job import PipelineJob
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


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
        existing: dict[str, Any] | None = await db[self.COLLECTION].find_one_and_update(
            {
                "product_slug": job.product_slug,
                "status": {"$nin": ["completed", "failed"]},
            },
            {"$setOnInsert": job.model_dump()},
            upsert=True,
            return_document=ReturnDocument.AFTER,
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
                "status": {"$nin": ["completed", "failed"]},
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
        await db[self.COLLECTION].update_one(
            {"id": job.id},
            {"$set": job.model_dump()},
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
        fields["updated_at"] = datetime.now()
        await db[self.COLLECTION].update_one(
            {"id": job_id},
            {"$set": fields},
        )
        logger.debug(f"Partially updated pipeline job {job_id}: {list(fields.keys())}")

    async def mark_stale_as_failed(
        self, db: AgnosticDatabase, stale_threshold_minutes: int = 30
    ) -> int:
        """Mark all non-terminal jobs older than the threshold as failed.

        Used on startup to recover from server crashes that left jobs orphaned.
        Uses last_heartbeat if available, otherwise falls back to updated_at.

        Returns the number of jobs marked as failed.
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(minutes=stale_threshold_minutes)
        result = await db[self.COLLECTION].update_many(
            {
                "status": {"$nin": ["completed", "failed"]},
                "$or": [
                    {"last_heartbeat": {"$lt": cutoff}},
                    {"last_heartbeat": None, "updated_at": {"$lt": cutoff}},
                    {"last_heartbeat": {"$exists": False}, "updated_at": {"$lt": cutoff}},
                ],
            },
            {
                "$set": {
                    "status": "failed",
                    "error": "Server restart — job was orphaned",
                    "updated_at": datetime.now(),
                    "completed_at": datetime.now(),
                }
            },
        )
        count = result.modified_count
        if count:
            logger.warning(f"Marked {count} stale pipeline job(s) as failed on startup")
        return count
