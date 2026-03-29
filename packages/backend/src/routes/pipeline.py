"""Pipeline routes for triggering and monitoring background crawl/analysis jobs.

Provides a DeepWiki-style API: submit a URL, get a job ID, poll for status.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from motor.core import AgnosticDatabase
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.pipeline_job import PipelineJob
from src.repositories.pipeline_repository import PipelineRepository
from src.services.pipeline_scheduler import schedule_pipeline_run
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
    already_indexed: bool = False


@router.post("/crawl", response_model=CrawlResponse, status_code=202)
async def start_crawl(
    request: CrawlRequest,
    background_tasks: BackgroundTasks,
    db: AgnosticDatabase = Depends(get_db),
) -> CrawlResponse:
    """Start a background crawl + analysis pipeline for a URL.

    If the product already exists and has an active job, returns that job.
    Otherwise, creates a new product (if needed) and starts the pipeline.

    The pipeline runs in the background:
    1. Crawl the site for policy documents
    2. Summarize each document
    3. Generate a privacy overview

    Poll GET /pipeline/jobs/{job_id} for status updates.
    """
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    pipeline_svc = create_pipeline_service()

    result = await pipeline_svc.create_job_for_url(db, url)

    # Product already fully indexed – no job needed
    if result.get("already_indexed"):
        return CrawlResponse(
            job_id="",
            product_slug=result["product_slug"],
            product_name=result["product_name"],
            status="completed",
            message=f"{result['product_name']} is already indexed.",
            already_indexed=True,
        )

    job = result["job"]

    # Best-effort: (re)kick background execution for any active job.
    scheduled = await schedule_pipeline_run(job.id, background_tasks)
    message = (
        f"Pipeline started for {job.product_name}. Poll /pipeline/jobs/{job.id} for status."
        if scheduled
        else f"Pipeline already running for {job.product_name}."
    )
    return CrawlResponse(
        job_id=job.id,
        product_slug=job.product_slug,
        product_name=job.product_name,
        status=job.status,
        message=message,
    )


@router.get("/active", response_model=PipelineJob)
async def get_active_job(
    product_slug: str,
    db: AgnosticDatabase = Depends(get_db),
) -> PipelineJob:
    """Get the active (non-terminal) pipeline job for a product, if any.

    Used by the frontend to check for in-progress jobs before firing a new crawl.
    Returns 404 when no active job exists.
    """
    pipeline_svc = create_pipeline_service()

    job = await pipeline_svc.get_active_job_for_product(db, product_slug)
    if not job:
        raise HTTPException(status_code=404, detail="No active job for this product")
    return job


@router.get("/latest", response_model=PipelineJob)
async def get_latest_job(
    product_slug: str,
    db: AgnosticDatabase = Depends(get_db),
) -> PipelineJob:
    """Get the most recent pipeline job for a product (any status).

    Returns active jobs first; falls back to the most recently created job.
    Used by the frontend to detect failed pipelines and show crawl errors.
    """
    pipeline_svc = create_pipeline_service()

    # Prefer active job
    job = await pipeline_svc.get_active_job_for_product(db, product_slug)
    if job:
        return job

    # Fall back to most recent job (including completed/failed)

    repo = PipelineRepository()
    jobs = await repo.find_by_product_slug(db, product_slug)
    if jobs:
        return jobs[0]  # sorted by created_at desc

    raise HTTPException(status_code=404, detail="No pipeline jobs found for this product")


@router.get("/jobs/{job_id}", response_model=PipelineJob)
async def get_job_status(
    job_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> PipelineJob:
    """Get the current status of a pipeline job.

    Returns the full job object with step-by-step progress.
    """
    pipeline_svc = create_pipeline_service()

    job = await pipeline_svc.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    return job


@router.delete("/jobs/{job_id}", status_code=200)
async def cancel_job(
    job_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> dict[str, str]:
    """Cancel a running pipeline job."""
    pipeline_svc = create_pipeline_service()
    job = await pipeline_svc.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    if job.status in ("completed", "failed"):
        raise HTTPException(status_code=409, detail=f"Job already {job.status}")

    repo = PipelineRepository()
    await repo.update_fields(
        db,
        job_id,
        {
            "status": "failed",
            "error": "Cancelled by user",
            "completed_at": datetime.now(),
        },
    )
    return {"status": "cancelled", "job_id": job_id}
