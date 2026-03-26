"""Pipeline service for orchestrating background crawl/analysis jobs.

Manages pipeline job lifecycle: creation, status tracking, and background
execution of the full crawl -> summarize -> overview pipeline.
"""

import asyncio
from datetime import datetime
from typing import Any

import shortuuid
from motor.core import AgnosticDatabase

from src.core.config import config
from src.core.database import db_session
from src.core.logging import get_logger
from src.models.document import Document
from src.models.pipeline_job import CrawlError, PipelineJob
from src.models.product import Product
from src.pipeline import LegalDocumentPipeline
from src.repositories.pipeline_repository import PipelineRepository
from src.services.service_factory import create_document_service, create_product_service
from src.summarizer import generate_product_overview, summarize_all_product_documents
from src.utils.domain import extract_domain as _extract_domain

logger = get_logger(__name__)

MAX_PIPELINE_DURATION_SECONDS = 1800


def _domain_to_product_name(domain: str) -> str:
    """Convert a domain to a human-readable product name.

    Examples:
        netflix.com -> Netflix
        notion.so -> Notion
        open-ai.com -> Open Ai
    """
    name_part = domain.split(".")[0]
    return name_part.replace("-", " ").replace("_", " ").title()


def _domain_to_slug(domain: str) -> str:
    """Convert a domain to a URL-safe slug.

    Examples:
        netflix.com -> netflix
        open-ai.com -> open-ai
    """
    return domain.split(".")[0].lower()


class PipelineService:
    """Orchestrates background pipeline jobs."""

    def __init__(self, pipeline_repo: PipelineRepository) -> None:
        self._pipeline_repo = pipeline_repo

    async def get_job(self, db: AgnosticDatabase, job_id: str) -> PipelineJob | None:
        """Get a pipeline job by ID."""
        return await self._pipeline_repo.find_by_id(db, job_id)

    async def get_active_job_for_product(
        self, db: AgnosticDatabase, product_slug: str
    ) -> PipelineJob | None:
        """Get the active (running) pipeline job for a product, if any."""
        return await self._pipeline_repo.find_active_by_product_slug(db, product_slug)

    async def create_job_for_url(self, db: AgnosticDatabase, url: str) -> dict:
        """Create a pipeline job for a URL.

        If the product is already fully indexed (completed overview exists), returns
        ``{"already_indexed": True, "product_slug": ..., "product_name": ...}``.

        If an active job exists, returns ``{"already_indexed": False, "job": <active_job>}``.

        Otherwise, creates a new product (if needed) and a new pending job, returning
        ``{"already_indexed": False, "job": <new_job>}``.

        Args:
            db: Database instance
            url: The URL to crawl and analyze

        Returns:
            A dict describing the outcome (see above).
        """
        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        domain = _extract_domain(url)
        slug = _domain_to_slug(domain)

        product_svc = create_product_service()

        # Check if product already exists
        product = await product_svc.get_product_by_slug(db, slug)

        if not product:
            # Also check by domain with base-domain fallback
            product = await product_svc.find_by_domain_variant(db, domain)

        if product:
            # Check if product is already fully indexed (has a completed overview)
            overview = await product_svc.get_product_overview_data(db, product.slug)
            if overview:
                logger.info(f"Product {product.slug} is already indexed – skipping pipeline")
                return {
                    "already_indexed": True,
                    "product_slug": product.slug,
                    "product_name": product.name,
                }
        else:
            # Create new product from URL
            product = Product(
                id=shortuuid.uuid(),
                name=_domain_to_product_name(domain),
                slug=slug,
                domains=[domain],
                crawl_base_urls=[url],
            )
            await product_svc.create_product(db, product)
            logger.info(f"Created new product '{product.name}' ({product.slug}) from URL: {url}")

        job = PipelineJob(
            product_slug=product.slug,
            product_id=product.id,
            product_name=product.name,
            url=url,
        )
        job, created = await self._pipeline_repo.find_or_create_active(db, job)
        if created:
            logger.info(f"Created pipeline job {job.id} for {product.slug}")
        else:
            logger.info(f"Active pipeline job already exists for {product.slug}: {job.id}")

        return {"already_indexed": False, "job": job}

    async def _update_step(
        self,
        db: AgnosticDatabase,
        job: PipelineJob,
        step_name: str,
        status: str,
        message: str | None = None,
    ) -> None:
        """Update a specific step in the pipeline job."""
        update_data: dict[str, Any] = {
            "status": job.status,
            "documents_found": job.documents_found,
            "documents_stored": job.documents_stored,
        }
        for i, step in enumerate(job.steps):
            if step.name == step_name:
                step.status = status  # type: ignore[assignment]
                step.message = message

                update_data[f"steps.{i}.status"] = status
                update_data[f"steps.{i}.message"] = message

                if status == "running":
                    now = datetime.now()
                    step.started_at = now
                    update_data[f"steps.{i}.started_at"] = now
                elif status in ("completed", "failed"):
                    now = datetime.now()
                    step.completed_at = now
                    update_data[f"steps.{i}.completed_at"] = now

                    # Clear progress fields on completion/failure to ensure clean UI state
                    step.progress_current = None
                    step.progress_total = None
                    step.progress_percent = None
                    update_data[f"steps.{i}.progress_current"] = None
                    update_data[f"steps.{i}.progress_total"] = None
                    update_data[f"steps.{i}.progress_percent"] = None
                break

        await self._pipeline_repo.update_fields(db, job.id, update_data)

    async def _update_step_progress(
        self,
        db: AgnosticDatabase,
        job: PipelineJob,
        step_name: str,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        """Update progress metadata for a specific step."""
        # Note: We do NOT update top-level status or document counts here.
        # This prevents late-running progress tasks (e.g. from discovery phase)
        # from overwriting more recent state changes in MongoDB.
        update_data: dict[str, Any] = {}

        for i, step in enumerate(job.steps):
            if step.name == step_name:
                # IMPORTANT: Skip updates if the step is already terminal.
                # This prevents late "Discovery: 0/500..." messages from overwriting
                # the final "Found X documents" message.
                if step.status in ("completed", "failed"):
                    logger.debug(
                        f"Skipping progress update for terminal step {step_name} in job {job.id}"
                    )
                    return

                if current is not None:
                    step.progress_current = current
                    update_data[f"steps.{i}.progress_current"] = current
                if total is not None:
                    step.progress_total = total
                    update_data[f"steps.{i}.progress_total"] = total

                if (
                    step.progress_current is not None
                    and step.progress_total is not None
                    and step.progress_total > 0
                ):
                    percent = (step.progress_current / step.progress_total) * 100
                    step.progress_percent = min(100.0, round(percent, 2))
                    update_data[f"steps.{i}.progress_percent"] = step.progress_percent

                if message is not None:
                    step.message = message
                    update_data[f"steps.{i}.message"] = message
                break

        if not update_data:
            return

        await self._pipeline_repo.update_fields(db, job.id, update_data)

    async def run_pipeline(self, job_id: str) -> None:
        """Execute the full pipeline for a job in the background.

        This runs: crawl -> summarize -> generate overview.
        Updates the job status at each step.

        Args:
            job_id: The pipeline job ID to execute
        """
        async with db_session() as db:
            job = await self._pipeline_repo.find_by_id(db, job_id)
            if not job:
                logger.error(f"Pipeline job {job_id} not found")
                return

            product_svc = create_product_service()
            product = await product_svc.get_product_by_slug(db, job.product_slug)
            if not product:
                job.status = "failed"
                job.error = f"Product {job.product_slug} not found"
                await self._pipeline_repo.update(db, job)
                return

            async def _run_pipeline_core() -> None:
                try:
                    if job.started_at is None:
                        job.started_at = datetime.now()
                        await self._pipeline_repo.update_fields(
                            db, job.id, {"started_at": job.started_at}
                        )

                    # === Step 1: Crawl ===
                    job.status = "crawling"
                    await self._update_step(
                        db, job, "crawling", "running", "Discovering legal documents..."
                    )

                    # Track progress tasks to ensure they are all processed before switching phases.
                    # This prevents a race condition where a late 'Discovery' update overwrites
                    # the subsequent 'summarizing' job status in MongoDB.
                    crawl_tasks: list[asyncio.Task] = []

                    # Create progress callback for crawl phase
                    async def _on_crawl_progress(phase: str, current: int, total: int) -> None:
                        remaining = max(total - current, 0)
                        phase_name = "Discovery" if phase == "discovery" else "Deep Crawl"
                        # We wrap this in a task so the crawler doesn't block on DB I/O,
                        # but we keep track of it to await it before phase transitions.
                        task = asyncio.create_task(
                            self._update_step_progress(
                                db,
                                job,
                                "crawling",
                                current=current,
                                total=total,
                                message=f"{phase_name}: {current}/{total} pages scanned ({remaining} remaining)",
                            )
                        )
                        crawl_tasks.append(task)

                    pipeline = LegalDocumentPipeline(
                        max_depth=config.crawler.max_depth,
                        max_pages=config.crawler.max_pages,
                        crawler_strategy="bfs",
                        concurrent_limit=config.crawler.concurrent_limit,
                        delay_between_requests=config.crawler.delay_between_requests,
                        progress_callback=_on_crawl_progress,
                    )
                    stats = await pipeline.run([product])

                    # Drain pending progress tasks before finalizing the crawl step
                    if crawl_tasks:
                        await asyncio.gather(*crawl_tasks, return_exceptions=True)

                    job.documents_found = stats.total_documents_found
                    job.documents_stored = stats.legal_documents_stored

                    # Persist per-URL crawl failures on the job
                    if stats.crawl_errors:
                        job.crawl_errors = [CrawlError(**err) for err in stats.crawl_errors]

                    await self._update_step(
                        db,
                        job,
                        "crawling",
                        "completed",
                        f"Found {stats.legal_documents_stored} legal documents",
                    )

                    if stats.legal_documents_stored == 0:
                        job.status = "failed"

                        # Build a descriptive error based on crawl error types
                        robots_blocked = [
                            e for e in job.crawl_errors if e.error_type == "robots_txt_blocked"
                        ]
                        if robots_blocked and len(robots_blocked) == len(job.crawl_errors):
                            job.error = (
                                "This site blocks automated access via robots.txt. "
                                "We were unable to crawl any legal documents."
                            )
                        elif robots_blocked:
                            job.error = (
                                f"Some pages were blocked by robots.txt ({len(robots_blocked)} "
                                f"of {len(job.crawl_errors)} failed URLs). "
                                "No legal documents could be found."
                            )
                        elif job.crawl_errors:
                            job.error = (
                                f"Crawling failed for {len(job.crawl_errors)} URL(s). "
                                "No legal documents could be found."
                            )
                        else:
                            job.error = "No legal documents found on this site"

                        job.completed_at = datetime.now()
                        await self._update_step(
                            db,
                            job,
                            "summarizing",
                            "failed",
                            "Skipped - no documents to analyze",
                        )
                        await self._update_step(
                            db,
                            job,
                            "generating_overview",
                            "failed",
                            "Skipped - no documents to analyze",
                        )
                        await self._pipeline_repo.update(db, job)
                        return

                    # === Step 2: Summarize ===
                    job.status = "summarizing"
                    await self._update_step(
                        db, job, "summarizing", "running", "Analyzing document contents..."
                    )

                    doc_svc = create_document_service()
                    expected_total = int(job.documents_stored or job.documents_found or 0)
                    if expected_total > 0:
                        await self._update_step_progress(
                            db,
                            job,
                            "summarizing",
                            current=0,
                            total=expected_total,
                            message=f"Queued {expected_total} documents for analysis",
                        )

                    async def _on_summarize_progress(index: int, total: int, doc: Document) -> None:
                        remaining = max(total - index, 0)
                        title = f": {doc.title}" if doc.title else ""
                        await self._update_step_progress(
                            db,
                            job,
                            "summarizing",
                            current=index,
                            total=total,
                            message=f"Analyzing document {index}/{total}{title} ({remaining} left)",
                        )

                    await summarize_all_product_documents(
                        db,
                        job.product_slug,
                        doc_svc,
                        progress_callback=_on_summarize_progress,
                    )

                    await self._update_step(
                        db, job, "summarizing", "completed", "All documents analyzed"
                    )

                    # === Step 3: Generate Overview ===
                    job.status = "generating_overview"
                    await self._update_step(
                        db,
                        job,
                        "generating_overview",
                        "running",
                        "Generating privacy overview...",
                    )

                    product_svc_for_overview = create_product_service()
                    doc_svc_for_overview = create_document_service()
                    await generate_product_overview(
                        db,
                        job.product_slug,
                        force_regenerate=True,
                        product_svc=product_svc_for_overview,
                        document_svc=doc_svc_for_overview,
                    )

                    await self._update_step(
                        db,
                        job,
                        "generating_overview",
                        "completed",
                        "Privacy overview ready",
                    )

                    # === Done ===
                    job.status = "completed"
                    job.completed_at = datetime.now()
                    await self._pipeline_repo.update(db, job)
                    logger.info(
                        f"Pipeline job {job.id} completed for {job.product_slug} "
                        f"({job.documents_stored} documents)"
                    )

                    # Notify subscribers (best-effort)
                    try:
                        from src.services.service_factory import (
                            create_indexation_notification_service,
                        )

                        notify_svc = create_indexation_notification_service()
                        await notify_svc.notify_indexation_completed(
                            db,
                            product_slug=job.product_slug,
                            product_name=product.name,
                            documents_found=int(job.documents_stored or job.documents_found),
                        )
                    except Exception as notify_exc:  # noqa: BLE001
                        logger.warning(
                            "indexation completion notify failed",
                            product_slug=job.product_slug,
                            error=str(notify_exc),
                        )

                except Exception as e:
                    logger.error(
                        f"Pipeline job {job.id} failed: {e}",
                        exc_info=True,
                    )
                    job.status = "failed"
                    job.error = str(e)
                    job.completed_at = datetime.now()

                    # Mark any running steps as failed
                    for step in job.steps:
                        if step.status == "running":
                            step.status = "failed"
                            step.message = f"Failed: {e}"
                            step.completed_at = datetime.now()

                    await self._pipeline_repo.update(db, job)

            try:
                await asyncio.wait_for(
                    _run_pipeline_core(),
                    timeout=MAX_PIPELINE_DURATION_SECONDS,
                )
            except TimeoutError:
                logger.error(
                    "Pipeline job %s timed out after %s seconds",
                    job_id,
                    MAX_PIPELINE_DURATION_SECONDS,
                )
                job.status = "failed"
                job.error = "Pipeline timed out after 30 minutes"
                job.completed_at = datetime.now()
                for step in job.steps:
                    if step.status == "running":
                        step.status = "failed"
                        step.message = "Pipeline timed out after 30 minutes"
                        step.completed_at = datetime.now()
                await self._pipeline_repo.update(db, job)
