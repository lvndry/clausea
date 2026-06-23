"""Pipeline service for orchestrating background crawl/analysis jobs.

Manages pipeline job lifecycle: creation, status tracking, and background
execution of the full crawl -> synthesise -> overview pipeline.
"""

import asyncio
import contextlib
import os
from datetime import datetime
from typing import Any, Literal

import shortuuid
from motor.core import AgnosticDatabase

from src.analyser import (
    analyse_product_documents,
    generate_product_compliance,
    generate_product_consumer_explainer,
    generate_product_overview,
)
from src.core.database import db_session
from src.core.logging import get_logger
from src.models.document import Document
from src.models.pipeline_job import (
    TERMINAL_PIPELINE_STATUSES,
    CrawlError,
    CrawlSkip,
    PipelineErrorCode,
    PipelineJob,
)
from src.models.product import Product
from src.pipeline import PolicyDocumentPipeline
from src.prompts.analysis_prompts import OVERVIEW_CORE_DOC_TYPES
from src.repositories.finding_repository import FindingRepository
from src.repositories.monitoring_schedule_repository import MonitoringScheduleRepository
from src.repositories.pipeline_repository import PipelineRepository
from src.repositories.product_repository import ProductRepository
from src.services.service_factory import create_document_service, create_product_service
from src.utils.domain import extract_domain as _extract_domain

logger = get_logger(__name__)

# Optional absolute wall-clock backstop, OFF by default (0 / unset → no cap). Liveness comes from
# the stall guard (below) plus the crawler's max_pages work bound, so a legitimately long crawl of
# a large/multi-jurisdiction site runs to completion. Set PIPELINE_MAX_DURATION_SECONDS > 0 only if
# you want a hard ceiling regardless of forward progress.
MAX_PIPELINE_DURATION_SECONDS = float(os.getenv("PIPELINE_MAX_DURATION_SECONDS", "0"))
# Abort a job that makes no forward progress (no heartbeat bump) for this long.
# The crawler's own CRAWL_BOT_WALL_ABORT (20 consecutive failures) handles the
# "completely blocked site" case early — this stall guard is the backstop for genuinely
# hung/wedged processes (OOM, deadlock, etc.) that never update their heartbeat.
# 3 600 s (60 min) is generous enough for legitimately large multi-jurisdiction crawls.
STALL_TIMEOUT_SECONDS = float(os.getenv("PIPELINE_STALL_TIMEOUT_SECONDS", "3600"))


class _PipelineStalled(Exception):
    """Raised internally when a job makes no progress within STALL_TIMEOUT_SECONDS."""


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

    async def create_job_for_url(
        self, db: AgnosticDatabase, url: str, seed_urls: list[str] | None = None
    ) -> dict:
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

        # Persist extension-provided seeds into the product so every future re-crawl
        # can reach them. Sites behind anti-bot walls are unreachable without these
        # URLs — discarding them after one use means monitoring re-crawls will find
        # zero documents. $addToSet ensures no duplicates.
        if seed_urls:
            product_repo = ProductRepository()
            await product_repo.add_crawl_seeds(db, product.id, seed_urls)
            logger.info(
                "persisted %d extension seed(s) to product %s crawl_base_urls",
                len(seed_urls),
                product.slug,
            )

        job = PipelineJob(
            product_slug=product.slug,
            product_id=product.id,
            product_name=product.name,
            url=url,
            seed_urls=seed_urls or [],
        )
        job, created = await self._pipeline_repo.find_or_create_active(db, job)
        if created:
            logger.info(f"Created pipeline job {job.id} for {product.slug}")
        else:
            logger.info(f"Active pipeline job already exists for {product.slug}: {job.id}")

        return {"already_indexed": False, "job": job}

    async def _await_with_stall_guard(
        self, core_task: asyncio.Task[None], job_id: str, started_at: datetime
    ) -> None:
        """Await the pipeline core, cancelling it if the job stalls (no progress for the timeout).

        Progress is any step/page/document update, each of which bumps the job's updated_at. A
        pipeline that is still advancing — even slowly through the model cascade — is never
        cancelled; only one wedged with zero forward progress is, freeing the worker slot rather
        than holding it indefinitely. This is the primary liveness bound now that the absolute
        wall-clock cap is off by default.
        """
        poll = min(60.0, STALL_TIMEOUT_SECONDS)
        while True:
            done, _ = await asyncio.wait({core_task}, timeout=poll)
            if core_task in done:
                await core_task  # propagate any error the core didn't handle internally
                return

            async with db_session() as watchdog_db:
                fresh = await self._pipeline_repo.find_by_id(watchdog_db, job_id)
            if fresh is None or fresh.status in TERMINAL_PIPELINE_STATUSES:
                await core_task
                return

            last_progress = fresh.updated_at or started_at
            if (datetime.now() - last_progress).total_seconds() > STALL_TIMEOUT_SECONDS:
                core_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await core_task
                raise _PipelineStalled

    async def _mark_aborted(
        self, db: AgnosticDatabase, job: PipelineJob, code: PipelineErrorCode, detail: str
    ) -> None:
        """Mark a job failed after a stall/timeout abort, flagging any running steps."""
        job.status = "failed"
        job.error = code
        job.error_detail = detail
        job.completed_at = datetime.now()
        for step in job.steps:
            if step.status == "running":
                step.status = "failed"
                step.message = detail
                step.completed_at = datetime.now()
        await self._pipeline_repo.update(db, job)

    async def _update_step(
        self,
        db: AgnosticDatabase,
        job: PipelineJob,
        step_name: str,
        status: Literal["pending", "running", "completed", "failed"],
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
                step.status = status
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
                    candidate = min(100.0, round(percent, 2))
                    # Progress must never move backwards. During crawling the
                    # frontier grows as new links are discovered, so a raw
                    # current/total ratio oscillates downward; the discovery and
                    # deep-crawl passes also share this step on fresh crawler stats,
                    # which would otherwise reset the bar mid-crawl. Clamp to a
                    # monotonic high-water mark so the UI bar only ever advances.
                    monotonic = max(step.progress_percent or 0.0, candidate)
                    if monotonic != step.progress_percent:
                        step.progress_percent = monotonic
                        update_data[f"steps.{i}.progress_percent"] = monotonic

                if message is not None:
                    step.message = message
                    update_data[f"steps.{i}.message"] = message

                # Steady crawl progress must keep the job alive. The in-process stall
                # guard checks updated_at (bumped by update_fields) and the cross-process
                # stale-job sweeper prefers last_heartbeat; set the latter here so both
                # see forward progress even when the monotonic clamp leaves no other
                # field changed. The crawler reports every PROGRESS_REPORT_INTERVAL pages,
                # which stays well inside the stall window even at slow speeds.
                now = datetime.now()
                job.last_heartbeat = now
                update_data["last_heartbeat"] = now
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
                job.error = PipelineErrorCode.product_not_found
                job.error_detail = f"Product {job.product_slug} not found"
                await self._pipeline_repo.update(db, job)
                return

            async def _run_pipeline_core() -> None:
                try:
                    if job.started_at is None:
                        job.started_at = datetime.now()
                        await self._pipeline_repo.update_fields(
                            db, job.id, {"started_at": job.started_at}
                        )

                    # Purge any findings left over from a previous attempt.
                    # On retries (attempts > 1) the per-document delete-then-insert loop
                    # in rebuild_findings_for_product only clears findings for documents
                    # it reaches before the next crash. Across several crash/retry cycles
                    # this causes unbounded accumulation (one product reached 7 000+
                    # findings, filling the Atlas M0 quota). Purging up front on retries
                    # makes each retry a clean rebuild while leaving findings intact on
                    # first-time runs, so a crawl failure never wipes a previously
                    # successful analysis.
                    if job.attempts > 1:
                        stale_count = await FindingRepository().delete_findings_for_product(
                            db, product.id
                        )
                        logger.info(
                            "Cleared %d stale finding(s) for %s before pipeline retry (attempt %d)",
                            stale_count,
                            job.product_slug,
                            job.attempts,
                        )
                    else:
                        logger.info(
                            "First attempt for %s — skipping stale findings purge",
                            job.product_slug,
                        )

                    # === Step 1: Crawl ===
                    job.status = "crawling"
                    await self._update_step(
                        db, job, "crawling", "running", "Discovering policy documents..."
                    )

                    # Track progress tasks to ensure they are all processed before switching phases.
                    # This prevents a race condition where a late 'Discovery' update overwrites
                    # the subsequent 'synthesising' job status in MongoDB.
                    crawl_tasks: list[asyncio.Task] = []

                    # Create progress callback for crawl phase.
                    #
                    # `current` is pages successfully fetched; `total` is the discovered
                    # frontier. We deliberately do NOT emit a percentage or "X remaining"
                    # for crawling: the frontier is a moving target (it grows as links are
                    # found) and is inflated by speculative policy-URL probes that mostly
                    # 404, so any ratio is fiction. Report an honest count and let the UI
                    # render this step as indeterminate. (The synthesising step, which has a
                    # real fixed total, keeps its genuine percentage.)
                    async def _on_crawl_progress(_phase: str, current: int, _total: int) -> None:
                        pages = "page" if current == 1 else "pages"
                        # We wrap this in a task so the crawler doesn't block on DB I/O,
                        # but we keep track of it to await it before phase transitions.
                        task = asyncio.create_task(
                            self._update_step_progress(
                                db,
                                job,
                                "crawling",
                                message=f"Discovering documents — {current} {pages} read so far",
                            )
                        )
                        crawl_tasks.append(task)

                    pipeline = PolicyDocumentPipeline(
                        progress_callback=_on_crawl_progress, job_id=job.id
                    )
                    stats = await pipeline.run([product])

                    # Drain pending progress tasks before finalizing the crawl step
                    if crawl_tasks:
                        await asyncio.gather(*crawl_tasks, return_exceptions=True)

                    # Update the product display name when the crawler found a better one in
                    # page metadata (e.g. og:site_name "OpenAI" vs domain-derived "Openai").
                    brand_name: str | None = getattr(stats, "brand_name", None)
                    if brand_name and brand_name != product.name:
                        try:
                            product_svc_upd = create_product_service()
                            await product_svc_upd.update_product_name(db, product.id, brand_name)
                            logger.info(
                                "Product name updated: '%s' → '%s' (%s)",
                                product.name,
                                brand_name,
                                job.product_slug,
                            )
                            product.name = brand_name
                            job.product_name = brand_name
                            await self._pipeline_repo.update_fields(
                                db, job.id, {"product_name": brand_name}
                            )
                        except Exception as name_exc:
                            logger.warning(
                                "Brand name update failed for %s: %s",
                                job.product_slug,
                                name_exc,
                            )

                    job.documents_found = stats.total_documents_found
                    job.documents_stored = stats.policy_documents_stored

                    # Reset attempt-local crawl diagnostics so a retry cannot inherit
                    # stale errors/skips from a previous failed attempt.
                    job.crawl_errors = []
                    job.crawl_skip_reasons = []

                    # Persist per-URL crawl failures on the job
                    if stats.crawl_errors:
                        job.crawl_errors = [CrawlError(**err) for err in stats.crawl_errors]

                    # Persist silent skips (fetched OK but rejected by a filter)
                    if stats.crawl_skip_reasons:
                        job.crawl_skip_reasons = [
                            CrawlSkip(**skip) for skip in stats.crawl_skip_reasons
                        ]

                    await self._update_step(
                        db,
                        job,
                        "crawling",
                        "completed",
                        f"Found {stats.policy_documents_stored} policy documents",
                    )

                    if stats.policy_documents_stored == 0:
                        # Crawl stored nothing new. Before giving up, check if the
                        # product already has documents from a previous run. If yes,
                        # those docs are valid input for synthesis — deduplicated
                        # re-crawls (same content hash) legitimately store 0 new docs
                        # but must not skip the overview step.
                        doc_svc_check = create_document_service()
                        existing_docs = await doc_svc_check.get_product_documents_by_slug(
                            db, job.product_slug
                        )
                        existing_policy_docs = [
                            doc for doc in existing_docs if doc.doc_type != "other"
                        ]
                        if existing_policy_docs:
                            logger.info(
                                "Crawl stored 0 new docs but %d existing docs found for %s "
                                "— proceeding to synthesis",
                                len(existing_policy_docs),
                                job.product_slug,
                            )
                            job.documents_stored = len(existing_policy_docs)
                        else:
                            job.status = "no_documents"

                        # Build a descriptive error based on crawl error types
                        robots_blocked = [
                            err
                            for err in job.crawl_errors
                            if err.error_type == "robots_txt_blocked"
                        ]
                        if (
                            robots_blocked
                            and len(robots_blocked) == len(job.crawl_errors)
                            and not job.crawl_skip_reasons
                        ):
                            # All attempted URLs were blocked by robots.txt — this is a
                            # distinct, deterministic outcome that the frontend surfaces
                            # with a dedicated "blocked by robots.txt" message instead of
                            # the generic "no documents found" state.
                            job.status = "robots_blocked"
                            job.error = PipelineErrorCode.crawl_robots_blocked
                            job.error_detail = (
                                "This site blocks automated access via robots.txt. "
                                "We were unable to crawl any policy documents."
                            )
                        elif robots_blocked:
                            job.status = "robots_blocked"
                            job.error = PipelineErrorCode.crawl_robots_blocked
                            job.error_detail = (
                                f"Some pages were blocked by robots.txt ({len(robots_blocked)} "
                                f"of {len(job.crawl_errors)} failed URLs). "
                                "No policy documents could be found."
                            )
                        elif job.crawl_errors:
                            job.error = PipelineErrorCode.crawl_failed
                            job.error_detail = (
                                f"Crawling failed for {len(job.crawl_errors)} URL(s). "
                                "No policy documents could be found."
                            )
                        elif job.crawl_skip_reasons:
                            # Categorize: which filter rejected the URLs? This gives the
                            # operator a concrete next action (tune classifier, enable JS
                            # rendering, etc.) instead of the prior opaque message.
                            counts: dict[str, int] = {}
                            for skip in job.crawl_skip_reasons:
                                counts[skip.reason] = counts.get(skip.reason, 0) + 1
                            breakdown = ", ".join(
                                f"{n}× {reason}"
                                for reason, n in sorted(counts.items(), key=lambda kv: -kv[1])
                            )
                            job.error = PipelineErrorCode.no_documents_found
                            job.error_detail = (
                                f"{len(job.crawl_skip_reasons)} URLs fetched but all "
                                f"rejected by content filters ({breakdown}). "
                                "See crawl_skip_reasons for the per-URL detail."
                            )
                        else:
                            job.error = PipelineErrorCode.no_documents_found
                            job.error_detail = "No policy documents found on this site"

                        job.completed_at = datetime.now()
                        await self._update_step(
                            db,
                            job,
                            "synthesising",
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

                        # Remove the product record when the crawl found nothing at all.
                        # A product with no documents is invisible to users (no analysis,
                        # no overview) and reappearing in the product list is confusing.
                        # The pipeline job is kept as a failure record; the product is
                        # re-created automatically if the user retries the URL later.
                        if job.status in ("no_documents", "robots_blocked"):
                            try:
                                doc_count = await db.documents.count_documents(
                                    {"product_id": product.id}
                                )
                                if doc_count == 0:
                                    await db.products.delete_one({"id": product.id})
                                    logger.info(
                                        "Removed empty product %s (no policy documents found)",
                                        job.product_slug,
                                    )
                                else:
                                    logger.info(
                                        "Kept product %s despite no_documents — %d existing document(s) present",
                                        job.product_slug,
                                        doc_count,
                                    )
                            except Exception as del_exc:  # noqa: BLE001
                                logger.warning(
                                    "Failed to remove empty product %s: %s",
                                    job.product_slug,
                                    del_exc,
                                )

                        # Alert the admin so a human can check whether this is a
                        # crawler coverage gap or the site genuinely has no policy
                        # documents. Best-effort — never fail the job on email error.
                        try:
                            from src.services.email_service import get_email_service

                            await get_email_service().send_no_documents_alert(
                                product_name=product.name,
                                product_slug=job.product_slug,
                                url=job.url,
                                reason=job.error_detail or "No policy documents found on this site",
                                crawl_error_count=len(job.crawl_errors),
                                skip_count=len(job.crawl_skip_reasons),
                            )
                        except Exception as alert_exc:  # noqa: BLE001
                            logger.warning(
                                "no-documents admin alert failed",
                                product_slug=job.product_slug,
                                error=str(alert_exc),
                            )
                        return

                    # === Step 2: Summarize ===
                    job.status = "synthesising"
                    await self._update_step(
                        db, job, "synthesising", "running", "Analyzing document contents..."
                    )

                    doc_svc = create_document_service()
                    expected_total = int(job.documents_stored or job.documents_found or 0)
                    if expected_total > 0:
                        await self._update_step_progress(
                            db,
                            job,
                            "synthesising",
                            current=0,
                            total=expected_total,
                            message=f"Queued {expected_total} documents for analysis",
                        )

                    async def _on_synthesise_progress(
                        index: int, total: int, doc: Document
                    ) -> None:
                        remaining = max(total - index, 0)
                        title = f": {doc.title}" if doc.title else ""
                        await self._update_step_progress(
                            db,
                            job,
                            "synthesising",
                            current=index,
                            total=total,
                            message=f"Analyzing document {index}/{total}{title} ({remaining} left)",
                        )

                    async def _on_synthesise_heartbeat() -> None:
                        await self._update_step_progress(
                            db,
                            job,
                            "synthesising",
                            message="Retrying LLM analysis…",
                        )

                    analysis_result = await analyse_product_documents(
                        db,
                        job.product_slug,
                        doc_svc,
                        progress_callback=_on_synthesise_progress,
                        force_reanalyze=job.force_reanalyze,
                        heartbeat_callback=_on_synthesise_heartbeat,
                    )
                    analysed_docs = analysis_result.documents
                    job.analyses_skipped = analysis_result.analyses_skipped

                    # Update to total docs in product (not just newly stored this run).
                    # documents_stored was set from crawl stats which only counts new/changed
                    # docs — misleading when re-crawling a product that already has docs.
                    job.documents_stored = len(analysed_docs)

                    # Truthful step state: a document either got analysis or it didn't.
                    # Per-document failures are isolated inside analyse_product_documents,
                    # so the call returns even when every document failed. If NONE were
                    # analysed, mark the step failed (not "completed") and stop here with
                    # an accurate analysis-stage error — rather than reporting success and
                    # letting overview synthesis blow up with a generic failure.
                    analysed_count = sum(1 for doc in analysed_docs if doc.analysis)
                    # Overview synthesis needs at least one analysed CORE doc. If core docs
                    # were found but none of them got analysis, the overview will fail — so
                    # fail here truthfully instead of reporting "completed" and letting the
                    # next step blow up. (Non-core partial loss is reported, not failed.)
                    core_docs = [
                        doc for doc in analysed_docs if doc.doc_type in OVERVIEW_CORE_DOC_TYPES
                    ]
                    core_analysed = sum(1 for doc in core_docs if doc.analysis)
                    no_analysis = bool(analysed_docs) and analysed_count == 0
                    core_wipeout = bool(core_docs) and core_analysed == 0
                    if no_analysis or core_wipeout:
                        job.status = "failed"
                        if core_wipeout and not no_analysis:
                            job.error = PipelineErrorCode.core_docs_unanalyzed
                            job.error_detail = (
                                f"Analyzed {analysed_count} of {len(analysed_docs)} documents, but "
                                f"none of the {len(core_docs)} core policy document(s) (privacy/terms) "
                                "could be analyzed — cannot build a reliable overview. Usually a "
                                "temporary model rate-limit/timeout issue — try again."
                            )
                            synthesising_message = (
                                f"0 of {len(core_docs)} core documents could be analyzed "
                                f"({analysed_count} of {len(analysed_docs)} total)"
                            )
                        else:
                            job.error = PipelineErrorCode.all_analysis_failed
                            job.error_detail = (
                                f"Found {len(analysed_docs)} documents but could not analyze any "
                                "of them. This is usually a temporary issue (model rate limits or "
                                "timeouts) — try again."
                            )
                            synthesising_message = (
                                f"0 of {len(analysed_docs)} documents could be analyzed"
                            )
                        job.completed_at = datetime.now()
                        await self._update_step(
                            db,
                            job,
                            "synthesising",
                            "failed",
                            synthesising_message,
                        )
                        await self._update_step(
                            db,
                            job,
                            "generating_overview",
                            "failed",
                            "Skipped - no analyzed documents",
                        )
                        await self._pipeline_repo.update(db, job)
                        return

                    await self._update_step(
                        db,
                        job,
                        "synthesising",
                        "completed",
                        f"Analyzed {analysed_count} of {len(analysed_docs)} documents",
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

                    # Overview synthesis runs several long LLM/aggregation sub-steps with no
                    # DB write of its own. On a large core-doc set it can outlast the stall
                    # window, so bump the job heartbeat at each sub-step boundary the same way
                    # the summarize stage does — keeping a healthy synthesis from being killed
                    # at the finish line while a truly wedged one still trips the guard.
                    async def _on_overview_progress() -> None:
                        await self._update_step_progress(
                            db,
                            job,
                            "generating_overview",
                            message="Generating privacy overview...",
                        )

                    await generate_product_overview(
                        db,
                        job.product_slug,
                        force_regenerate=True,
                        product_svc=product_svc_for_overview,
                        document_svc=doc_svc_for_overview,
                        on_progress=_on_overview_progress,
                        job_id=job.id,
                    )

                    # Verify the overview actually persisted — same truthfulness lesson as
                    # the analysis-persistence bug: never report "completed" off an
                    # in-memory success without confirming the row exists in the DB.
                    persisted_overview = await product_svc_for_overview.get_product_overview_data(
                        db, job.product_slug
                    )
                    if not persisted_overview:
                        job.status = "failed"
                        job.error = PipelineErrorCode.overview_not_persisted
                        job.error_detail = (
                            "Overview generation reported success but no overview was persisted "
                            f"for {job.product_slug}."
                        )
                        job.completed_at = datetime.now()
                        await self._update_step(
                            db,
                            job,
                            "generating_overview",
                            "failed",
                            "Overview did not persist",
                        )
                        await self._pipeline_repo.update(db, job)
                        return

                    # Consumer explainer (product-level, the consumer-facing output).
                    # Best-effort: a failure here must NOT fail a job whose overview already
                    # succeeded — the product page degrades gracefully when it is absent.
                    _explainer_step_idx = next(
                        (i for i, s in enumerate(job.steps) if s.name == "generating_overview"),
                        None,
                    )
                    try:
                        await _on_overview_progress()
                        explainer = await generate_product_consumer_explainer(
                            db,
                            job.product_slug,
                            product_svc_for_overview,
                            doc_svc_for_overview,
                            heartbeat_callback=_on_overview_progress,
                        )
                        if explainer is not None:
                            saved = await product_svc_for_overview.save_product_explainer(
                                db, job.product_slug, explainer
                            )
                            logger.info(
                                "Saved consumer explainer for %s (grade=%s, persisted=%s)",
                                job.product_slug,
                                explainer.grade,
                                saved,
                            )
                            if _explainer_step_idx is not None:
                                job.steps[_explainer_step_idx].has_explainer = True
                                await self._pipeline_repo.update_fields(
                                    db,
                                    job.id,
                                    {
                                        f"steps.{_explainer_step_idx}.has_explainer": True,
                                    },
                                )
                        else:
                            logger.warning(
                                "Consumer explainer not generated for %s "
                                "(no core extraction or model failure).",
                                job.product_slug,
                            )
                            if _explainer_step_idx is not None:
                                job.steps[_explainer_step_idx].has_explainer = False
                                await self._pipeline_repo.update_fields(
                                    db,
                                    job.id,
                                    {
                                        f"steps.{_explainer_step_idx}.has_explainer": False,
                                    },
                                )
                    except asyncio.CancelledError:
                        raise
                    except Exception as explainer_error:
                        logger.warning(
                            "Consumer explainer generation failed for %s: %s",
                            job.product_slug,
                            explainer_error,
                            exc_info=True,
                        )
                        if _explainer_step_idx is not None:
                            job.steps[_explainer_step_idx].has_explainer = False
                            await self._pipeline_repo.update_fields(
                                db,
                                job.id,
                                {
                                    f"steps.{_explainer_step_idx}.has_explainer": False,
                                },
                            )

                    # Justified compliance assessment (per-regime score + strengths/gaps).
                    # Also best-effort — secondary to the consumer-facing outputs above.
                    try:
                        await _on_overview_progress()
                        compliance = await generate_product_compliance(
                            db,
                            job.product_slug,
                            product_svc_for_overview,
                            doc_svc_for_overview,
                        )
                        if compliance:
                            saved = await product_svc_for_overview.save_product_compliance(
                                db, job.product_slug, compliance
                            )
                            logger.info(
                                "Saved compliance assessment for %s (%d regime(s), persisted=%s)",
                                job.product_slug,
                                len(compliance),
                                saved,
                            )
                        else:
                            logger.info(
                                "No compliance assessment generated for %s "
                                "(documents gave no basis).",
                                job.product_slug,
                            )
                    except Exception as compliance_error:
                        logger.warning(
                            "Compliance assessment generation failed for %s: %s",
                            job.product_slug,
                            compliance_error,
                            exc_info=True,
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

                    # Auto-enroll in monitoring (best-effort)
                    try:
                        await MonitoringScheduleRepository().enroll(
                            db,
                            product_slug=job.product_slug,
                            product_id=job.product_id,
                        )
                    except Exception as enroll_exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to enroll %s in monitoring: %s",
                            job.product_slug,
                            enroll_exc,
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
                    job.error = PipelineErrorCode.internal_error
                    job.error_detail = str(e)
                    job.completed_at = datetime.now()

                    # Mark any running steps as failed
                    for step in job.steps:
                        if step.status == "running":
                            step.status = "failed"
                            step.message = f"Failed: {e}"
                            step.completed_at = datetime.now()

                    await self._pipeline_repo.update(db, job)

            core_task = asyncio.create_task(_run_pipeline_core())
            started_at = job.started_at or datetime.now()
            try:
                # Liveness is the stall guard (no-progress) + the crawler's max_pages bound. The
                # absolute wall-clock cap is an opt-in backstop: only wrap when explicitly enabled
                # (PIPELINE_MAX_DURATION_SECONDS > 0), so long legitimate crawls run to completion.
                if MAX_PIPELINE_DURATION_SECONDS > 0:
                    await asyncio.wait_for(
                        self._await_with_stall_guard(core_task, job_id, started_at),
                        timeout=MAX_PIPELINE_DURATION_SECONDS,
                    )
                else:
                    await self._await_with_stall_guard(core_task, job_id, started_at)
            except _PipelineStalled:
                stall_minutes = int(STALL_TIMEOUT_SECONDS // 60)
                logger.error("Pipeline job %s stalled (no progress for %dm)", job_id, stall_minutes)
                await self._mark_aborted(
                    db,
                    job,
                    PipelineErrorCode.stalled,
                    f"Stalled — no progress for {stall_minutes} minutes. Usually a site that's "
                    "hard to crawl/render or a temporary model issue; try again.",
                )
            except TimeoutError:
                # Opt-in hard ceiling fired (PIPELINE_MAX_DURATION_SECONDS > 0). The guard's
                # wait_for timed out but core_task is a separate task, so cancel it explicitly.
                core_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await core_task
                cap_seconds = int(MAX_PIPELINE_DURATION_SECONDS)
                logger.error(
                    "Pipeline job %s timed out after %s seconds",
                    job_id,
                    cap_seconds,
                )
                await self._mark_aborted(
                    db,
                    job,
                    PipelineErrorCode.timed_out,
                    f"Pipeline timed out after {cap_seconds} seconds",
                )
