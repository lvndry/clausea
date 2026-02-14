"""Pipeline routes for triggering and monitoring background crawl/analysis jobs.

Provides a DeepWiki-style API: submit a URL, get a job ID, poll for status.
"""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.pipeline_job import PipelineJob
from src.services.service_factory import create_pipeline_service

logger = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class CrawlRequest(BaseModel):
    """Request body for triggering a crawl pipeline."""

    url: str


class CrawlResponse(BaseModel):
    """Response after submitting a crawl request."""

    job_id: str
    product_slug: str
    product_name: str
    status: str
    message: str


@router.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest) -> CrawlResponse:
    """Start a background crawl + analysis pipeline for a URL.

    If the product already exists and has an active job, returns that job.
    Otherwise, creates a new product (if needed) and starts the pipeline.

    The pipeline runs in the background:
    1. Crawl the site for legal documents
    2. Summarize each document
    3. Generate a privacy overview

    Poll GET /pipeline/jobs/{job_id} for status updates.
    """
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    pipeline_svc = create_pipeline_service()

    async with get_db() as db:
        job = await pipeline_svc.create_job_for_url(db, url)

        # If the job was just created (pending status), start the pipeline
        if job.status == "pending":
            # Fire-and-forget the pipeline execution
            asyncio.create_task(_run_pipeline_background(job.id))

            return CrawlResponse(
                job_id=job.id,
                product_slug=job.product_slug,
                product_name=job.product_name,
                status=job.status,
                message=f"Pipeline started for {job.product_name}. Poll /pipeline/jobs/{job.id} for status.",
            )

        # Job already exists (active)
        return CrawlResponse(
            job_id=job.id,
            product_slug=job.product_slug,
            product_name=job.product_name,
            status=job.status,
            message=f"Pipeline already running for {job.product_name}.",
        )


@router.get("/jobs/{job_id}", response_model=PipelineJob)
async def get_job_status(job_id: str) -> PipelineJob:
    """Get the current status of a pipeline job.

    Returns the full job object with step-by-step progress.
    """
    pipeline_svc = create_pipeline_service()

    async with get_db() as db:
        job = await pipeline_svc.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Pipeline job not found")
        return job


async def _run_pipeline_background(job_id: str) -> None:
    """Wrapper to run the pipeline in the background and handle errors."""
    try:
        pipeline_svc = create_pipeline_service()
        await pipeline_svc.run_pipeline(job_id)
    except Exception as e:
        logger.error(f"Background pipeline failed for job {job_id}: {e}", exc_info=True)
