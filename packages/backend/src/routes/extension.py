"""Extension routes for browser extension integration.

Provides lightweight endpoints optimized for the browser extension popup.
"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from motor.core import AgnosticDatabase
from pydantic import BaseModel, EmailStr

from src.core.database import get_db
from src.core.logging import get_logger
from src.repositories.pipeline_repository import PipelineRepository
from src.services.pipeline_scheduler import schedule_pipeline_run
from src.services.service_factory import (
    create_indexation_notification_service,
    create_pipeline_service,
    create_product_service,
)
from src.utils.domain import extract_domain

logger = get_logger(__name__)

router = APIRouter(prefix="/extension", tags=["extension"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class ExtensionCrawlError(BaseModel):
    """Lightweight crawl error info for the extension popup."""

    url: str
    error_type: str
    error_message: str | None = None


class ExtensionCheckResponse(BaseModel):
    """Lightweight response for browser extension popup."""

    found: bool
    slug: str | None = None
    product_name: str | None = None
    product_status: Literal["unknown", "analyzing", "failed", "ready"] = "unknown"
    pipeline_active: bool = False
    pipeline_failed: bool = False
    pipeline_error: str | None = None
    crawl_errors: list[ExtensionCrawlError] | None = None
    verdict: (
        Literal["very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"]
        | None
    ) = None
    risk_score: int | None = None
    one_line_summary: str | None = None
    top_concerns: list[str] | None = None
    analysis_url: str | None = None


class ExtensionAnalyzeRequest(BaseModel):
    """Request body for triggering analysis from the extension."""

    url: str


class ExtensionAnalyzeResponse(BaseModel):
    """Response after triggering analysis."""

    status: Literal["started", "already_running", "already_indexed"]
    product_slug: str
    product_name: str
    job_id: str | None = None


class ExtensionSubscribeRequest(BaseModel):
    """Subscribe an email for indexation completion notification."""

    product_slug: str
    email: EmailStr


class ExtensionSubscribeResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ExtensionJobStatus(BaseModel):
    status: str
    progress_percent: float | None = None
    error: str | None = None
    retry_after_seconds: int = 3


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/check", response_model=ExtensionCheckResponse)
async def check_url(
    url: str = Query(..., description="The URL to check (e.g., https://netflix.com/signup)"),
    db: AgnosticDatabase = Depends(get_db),
) -> ExtensionCheckResponse:
    """Check if we have privacy analysis for a given URL.

    This endpoint is optimized for browser extension use:
    - Fast response time (no JIT generation)
    - Lightweight payload
    - CORS-friendly

    The extension uses this to:
    1. Light up the icon (green/yellow/red) based on verdict
    2. Show a quick summary in the popup
    3. Link to the full analysis on clausea.co
    4. Indicate whether an analysis pipeline is already running
    """
    domain = extract_domain(url)
    logger.debug(f"Extension check for URL: {url} -> domain: {domain}")

    product_svc = create_product_service()
    pipeline_svc = create_pipeline_service()

    # Try to find product by domain (with base-domain fallback)
    product = await product_svc.find_by_domain_variant(db, domain)

    if not product:
        return ExtensionCheckResponse(found=False, product_status="unknown")

    # Check for active pipeline job
    active_job = await pipeline_svc.get_active_job_for_product(db, product.slug)

    # Get the overview if available
    overview = await product_svc.get_product_overview(db, product.slug)

    if not overview:
        # Product exists but no analysis yet — check for a recent failed job
        failed_job = None
        if not active_job:
            pipeline_repo = PipelineRepository()
            recent_jobs = await pipeline_repo.find_by_product_slug(db, product.slug)
            for rj in recent_jobs:
                if rj.status == "failed":
                    failed_job = rj
                    break

        crawl_errors = None
        if failed_job and failed_job.crawl_errors:
            crawl_errors = [
                ExtensionCrawlError(
                    url=e.url,
                    error_type=e.error_type,
                    error_message=e.error_message,
                )
                for e in failed_job.crawl_errors[:5]  # limit payload size
            ]

        product_status: Literal["unknown", "analyzing", "failed", "ready"] = (
            "analyzing"
            if active_job is not None
            else "failed"
            if failed_job is not None
            else "analyzing"
        )
        return ExtensionCheckResponse(
            found=False,
            slug=product.slug,
            product_name=product.name,
            product_status=product_status,
            pipeline_active=active_job is not None,
            pipeline_failed=failed_job is not None,
            pipeline_error=failed_job.error if failed_job else None,
            crawl_errors=crawl_errors,
            analysis_url=f"https://clausea.co/products/{product.slug}",
        )

    # Extract top 3 concerns from dangers or keypoints
    top_concerns = None
    if overview.dangers:
        top_concerns = overview.dangers[:3]
    elif overview.keypoints:
        # Filter for concerning keypoints (heuristic: contains risk words)
        risk_keywords = ["share", "sell", "track", "collect", "third", "advertis", "retain"]
        concerning = [
            kp for kp in overview.keypoints if any(word in kp.lower() for word in risk_keywords)
        ]
        top_concerns = concerning[:3] if concerning else overview.keypoints[:3]

    product_status: Literal["unknown", "analyzing", "failed", "ready"] = (
        "analyzing" if active_job is not None else "ready"
    )
    return ExtensionCheckResponse(
        found=True,
        slug=product.slug,
        product_name=overview.product_name,
        product_status=product_status,
        pipeline_active=active_job is not None,
        verdict=overview.verdict,
        risk_score=overview.risk_score,
        one_line_summary=overview.one_line_summary,
        top_concerns=top_concerns,
        analysis_url=f"https://clausea.co/products/{product.slug}",
    )


@router.get("/status/{job_id}", response_model=ExtensionJobStatus)
async def get_job_status_lightweight(
    job_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> ExtensionJobStatus:
    """Lightweight job status for extension polling."""
    repo = PipelineRepository()
    job = await repo.find_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    progress_percent: float | None = None
    if job.steps:
        completed_steps = sum(1 for s in job.steps if s.status == "completed")
        total_steps = len(job.steps)
        if total_steps > 0:
            progress_percent = round(completed_steps / total_steps * 100, 1)
            for step in job.steps:
                if step.progress_percent is not None and step.status == "running":
                    step_base = completed_steps / total_steps * 100
                    step_contrib = step.progress_percent / total_steps
                    progress_percent = round(step_base + step_contrib, 1)
                    break

    retry_after = 3
    if job.status == "crawling":
        retry_after = 5
    elif job.status in ("completed", "failed"):
        retry_after = 0

    return ExtensionJobStatus(
        status=job.status,
        progress_percent=progress_percent,
        error=job.error,
        retry_after_seconds=retry_after,
    )


@router.get("/domains", response_model=list[str])
async def get_supported_domains(
    db: AgnosticDatabase = Depends(get_db),
) -> list[str]:
    """Get list of all domains we have analysis for.

    The extension can use this to:
    1. Pre-cache which domains to watch for
    2. Show "X domains protected" in the popup
    """
    pipeline = [
        {
            "$lookup": {
                "from": "documents",
                "localField": "id",
                "foreignField": "product_id",
                "as": "docs",
            }
        },
        {"$match": {"docs": {"$ne": []}, "domains": {"$exists": True, "$ne": []}}},
        {"$unwind": "$domains"},
        {"$group": {"_id": "$domains"}},
    ]
    results = await db.products.aggregate(pipeline).to_list(length=None)
    return [r["_id"] for r in results if r.get("_id")]


@router.post("/analyze", response_model=ExtensionAnalyzeResponse, status_code=202)
async def analyze_url(
    payload: ExtensionAnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: AgnosticDatabase = Depends(get_db),
) -> ExtensionAnalyzeResponse:
    """Trigger the analysis pipeline for a URL.

    Creates the product from URL metadata (domain, name, slug) if it doesn't
    exist, then starts the background pipeline.

    Idempotent: if a pipeline is already running for this domain, returns the
    existing job. If the product is already fully indexed, reports that.
    """
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Normalize to domain root so the crawler starts from a sensible position
    domain = extract_domain(url)
    normalized_url = f"https://{domain}"

    pipeline_svc = create_pipeline_service()

    result = await pipeline_svc.create_job_for_url(db, normalized_url)

    if result.get("already_indexed"):
        return ExtensionAnalyzeResponse(
            status="already_indexed",
            product_slug=result["product_slug"],
            product_name=result["product_name"],
        )

    job = result["job"]
    scheduled = await schedule_pipeline_run(job.id, background_tasks)

    return ExtensionAnalyzeResponse(
        status="started" if scheduled else "already_running",
        product_slug=job.product_slug,
        product_name=job.product_name,
        job_id=job.id,
    )


@router.post("/subscribe", response_model=ExtensionSubscribeResponse, status_code=201)
async def subscribe_email(
    payload: ExtensionSubscribeRequest,
    db: AgnosticDatabase = Depends(get_db),
) -> ExtensionSubscribeResponse:
    """Subscribe an email to be notified when analysis completes for a product.

    Uses the existing IndexationNotificationService which automatically sends
    an email when the pipeline finishes.
    """
    notify_svc = create_indexation_notification_service()

    # Verify the product exists
    product_svc = create_product_service()
    product = await product_svc.get_product_by_slug(db, payload.product_slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await notify_svc.subscribe(
        db,
        product_slug=payload.product_slug,
        email=str(payload.email),
    )

    logger.info(
        "extension email subscription",
        product_slug=payload.product_slug,
        email=str(payload.email),
    )

    return ExtensionSubscribeResponse()
