"""Pipeline service for orchestrating background crawl/analysis jobs.

Manages pipeline job lifecycle: creation, status tracking, and background
execution of the full crawl -> summarize -> overview pipeline.
"""

from __future__ import annotations

from datetime import datetime

import shortuuid
import tldextract
from motor.core import AgnosticDatabase

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.pipeline_job import PipelineJob
from src.models.product import Product
from src.pipeline import LegalDocumentPipeline
from src.repositories.pipeline_repository import PipelineRepository
from src.services.service_factory import create_document_service, create_product_service
from src.summarizer import generate_product_overview, summarize_all_product_documents

logger = get_logger(__name__)


def _extract_domain(url: str) -> str:
    """Extract the root domain from a URL.

    Examples:
        https://www.netflix.com/signup -> netflix.com
        https://app.slack.com/client -> slack.com
    """
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}"


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

    async def create_job_for_url(self, db: AgnosticDatabase, url: str) -> PipelineJob:
        """Create a pipeline job for a URL.

        If the product already exists, reuses it. Otherwise, creates a new product
        from the URL domain.

        Args:
            db: Database instance
            url: The URL to crawl and analyze

        Returns:
            The created PipelineJob
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
            # Also check by domain
            product = await product_svc.get_product_by_domain(db, domain)

        if not product:
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

        # Check for existing active job
        active_job = await self._pipeline_repo.find_active_by_product_slug(db, product.slug)
        if active_job:
            logger.info(f"Active pipeline job already exists for {product.slug}: {active_job.id}")
            return active_job

        # Create pipeline job
        job = PipelineJob(
            product_slug=product.slug,
            product_name=product.name,
            url=url,
        )
        await self._pipeline_repo.create(db, job)
        logger.info(f"Created pipeline job {job.id} for {product.slug}")

        return job

    async def _update_step(
        self,
        db: AgnosticDatabase,
        job: PipelineJob,
        step_name: str,
        status: str,
        message: str | None = None,
    ) -> None:
        """Update a specific step in the pipeline job."""
        for step in job.steps:
            if step.name == step_name:
                step.status = status  # type: ignore[assignment]
                step.message = message
                if status == "running":
                    step.started_at = datetime.now()
                elif status in ("completed", "failed"):
                    step.completed_at = datetime.now()
                break
        await self._pipeline_repo.update(db, job)

    async def run_pipeline(self, job_id: str) -> None:
        """Execute the full pipeline for a job in the background.

        This runs: crawl -> summarize -> generate overview.
        Updates the job status at each step.

        Args:
            job_id: The pipeline job ID to execute
        """
        async with get_db() as db:
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

            try:
                # === Step 1: Crawl ===
                job.status = "crawling"
                await self._update_step(
                    db, job, "crawling", "running", "Discovering legal documents..."
                )

                pipeline = LegalDocumentPipeline(
                    max_depth=4,
                    max_pages=500,
                    crawler_strategy="bfs",
                    concurrent_limit=5,
                    delay_between_requests=1.0,
                )
                stats = await pipeline.run([product])

                job.documents_found = stats.total_documents_found
                job.documents_stored = stats.legal_documents_stored
                await self._update_step(
                    db,
                    job,
                    "crawling",
                    "completed",
                    f"Found {stats.legal_documents_stored} legal documents",
                )

                if stats.legal_documents_stored == 0:
                    job.status = "failed"
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
                await summarize_all_product_documents(db, job.product_slug, doc_svc)

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
