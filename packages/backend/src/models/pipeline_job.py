"""Pipeline job model for tracking background crawl/analysis pipeline execution."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

import shortuuid
from pydantic import BaseModel, Field


class PipelineErrorCode(StrEnum):
    """Stable machine codes for pipeline job failures.

    The API stores one of these in `PipelineJob.error`; the human-readable
    phrasing lives in the frontend (mapped from the code) and, for debugging,
    in `PipelineJob.error_detail`.
    """

    product_not_found = "product_not_found"
    crawl_robots_blocked = "crawl_robots_blocked"
    crawl_failed = "crawl_failed"
    no_documents_found = "no_documents_found"
    all_analysis_failed = "all_analysis_failed"
    core_docs_unanalyzed = "core_docs_unanalyzed"
    overview_not_persisted = "overview_not_persisted"
    internal_error = "internal_error"
    timed_out = "timed_out"
    stalled = "stalled"
    interrupted = "interrupted"
    orphaned = "orphaned"
    domain_circuit_breaker = "domain_circuit_breaker"


PipelineJobStatus = Literal[
    "pending",
    "crawling",
    "synthesising",
    "generating_overview",
    "completed",
    "failed",
    "no_documents",
    "interrupted",
]

# Statuses a job can never leave. A job in any of these is "done" and must not be
# treated as active, reused, or retriggered automatically:
#   - completed:    ran to the end, overview generated
#   - no_documents: crawl ran to completion but found 0 policy documents (a valid,
#                   deterministic result — retrying yields the same outcome)
#   - failed:       interrupted or errored. Auto-retry may re-queue some failed
#                   jobs (transient/retryable) within a bounded attempt budget.
TERMINAL_PIPELINE_STATUSES: tuple[PipelineJobStatus, ...] = (
    "completed",
    "failed",
    "no_documents",
    "interrupted",
)

CrawlErrorType = Literal[
    "robots_txt_blocked",
    "http_error",
    "timeout",
    "network_error",
    "content_error",
    "unknown",
]


# HTTP status codes that indicate a hard anti-bot/access block (not transient errors).
# 403 Forbidden, 401 Unauthorized, 407 Proxy Auth Required, 451 Unavailable For Legal Reasons.
_HARD_HTTP_STATUS_CODES: frozenset[int] = frozenset({401, 403, 407, 451})

# Keywords in error messages that signal bot-detection or active access blocks.
_BOT_DETECTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "captcha",
        "cloudflare",
        "access denied",
        "bot detection",
        "bot-detection",
        "challenge",
        "security check",
        "ddos protection",
        "anti-bot",
    }
)


def is_hard_crawl_error(error_type: str, status_code: int, error_message: str | None) -> bool:
    """Return True if this crawl error signals a hard anti-bot or access block.

    Hard failures = bot detection (CAPTCHA, Cloudflare, 403 Forbidden, "Access Denied").
    Transient failures = network timeouts, DNS errors, 5xx server errors — these should
    still be retried.
    """
    if error_type == "http_error" and status_code in _HARD_HTTP_STATUS_CODES:
        return True
    if error_message:
        msg = error_message.lower()
        if any(kw in msg for kw in _BOT_DETECTION_KEYWORDS):
            return True
    return False


def classify_crawl_error(error_message: str | None, status_code: int) -> "CrawlErrorType":
    """Derive a categorical error type from the error message and status code."""
    if not error_message:
        return "unknown"
    msg = error_message.lower()
    if "robots.txt" in msg or "robots" in msg:
        return "robots_txt_blocked"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if any(kw in msg for kw in ("connection", "dns", "refused", "reset", "network")):
        return "network_error"
    if status_code >= 400:
        return "http_error"
    return "unknown"


class CrawlError(BaseModel):
    """A single URL that failed during crawling."""

    url: str
    status_code: int = 0
    error_message: str | None = None
    error_type: CrawlErrorType = "unknown"


CrawlSkipReason = Literal[
    "insufficient_content",
    "garbled_content",
    "low_legal_score",
    "non_policy_classification",
    "non_english",
]


class CrawlSkip(BaseModel):
    """A single URL that was fetched without error but dropped by a pipeline filter.

    Distinct from CrawlError — these are pages we got, looked at, and decided not to
    store. Knowing which filter rejected which URL is essential for diagnosing why
    a pipeline finishes with zero stored documents despite a successful crawl.
    """

    url: str
    reason: CrawlSkipReason
    detail: str | None = None  # e.g. "text=212 chars", "legal_score=0.18", "locale=fr-FR"


class PipelineStep(BaseModel):
    """Status of an individual pipeline step."""

    name: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    message: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_percent: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    has_explainer: bool | None = None


class PipelineJob(BaseModel):
    """Tracks the status of a background pipeline execution.

    Stored in the `pipeline_jobs` MongoDB collection.
    """

    id: str = Field(default_factory=shortuuid.uuid)
    product_slug: str
    product_id: str | None = None
    product_name: str
    url: str
    status: PipelineJobStatus = "pending"
    # Discriminator backing the partial unique index that enforces at-most-one active
    # job per product. Kept in sync with `status` by PipelineRepository on every write
    # (assignment to `status` does not re-derive it, so the repo is the source of truth).
    active: bool = True
    steps: list[PipelineStep] = Field(
        default_factory=lambda: [
            PipelineStep(name="crawling"),
            PipelineStep(name="synthesising"),
            PipelineStep(name="generating_overview"),
        ]
    )
    # Stable machine error code (a `PipelineErrorCode` value). The frontend maps
    # this to user-facing copy; never store a human string here.
    error: str | None = None
    # Human/debug detail for the error (logs + optional tooltip). May embed
    # counts, exception text, or a per-URL breakdown.
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat: datetime | None = None

    attempts: int = 0  # claims so far; bounds auto-retry of failed/orphaned jobs
    # Sticky auto-retry guard: when true, stale sweeps won't re-queue this failed job.
    auto_retry_disabled: bool = False
    auto_retry_disabled_reason: str | None = None

    # Cumulative count of hard crawl errors (bot detection, 403s, anti-scrape blocks)
    # accumulated across retries. NOT reset on requeue so the circuit breaker has a
    # persistent signal. Reaches PIPELINE_DOMAIN_CIRCUIT_BREAKER_THRESHOLD before
    # the next claim attempt skips the job instead of running it again.
    accumulated_hard_failure_count: int = 0

    # Stats from the crawl phase
    documents_found: int = 0
    documents_stored: int = 0

    # Per-URL crawl failures (e.g. robots.txt blocks, HTTP errors)
    crawl_errors: list[CrawlError] = Field(default_factory=list)

    # Per-URL silent skips: pages we fetched OK but rejected by a filter.
    # Populated by pipeline._process_crawl_result. Used to produce a
    # categorized failure message when crawl_errors is empty but the
    # pipeline still found no policy documents.
    crawl_skip_reasons: list[CrawlSkip] = Field(default_factory=list)

    # Policy-page URLs harvested from the live DOM by the browser extension
    # (footer links the server crawler cannot reach due to anti-bot walls).
    # Injected as high-priority seeds at the start of the crawl.
    seed_urls: list[str] = Field(default_factory=list)

    # When True, the analysis phase skips the content-hash cache and re-runs
    # LLM analysis on every document even if findings already exist in the DB.
    force_reanalyze: bool = False

    # Number of documents whose analysis was reused from a prior run (skipped LLM).
    analyses_skipped: int = 0
