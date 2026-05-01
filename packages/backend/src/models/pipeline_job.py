"""Pipeline job model for tracking background crawl/analysis pipeline execution."""

from datetime import datetime
from typing import Literal

import shortuuid
from pydantic import BaseModel, Field

PipelineJobStatus = Literal[
    "pending",
    "crawling",
    "summarizing",
    "generating_overview",
    "completed",
    "failed",
]

CrawlErrorType = Literal[
    "robots_txt_blocked",
    "http_error",
    "timeout",
    "network_error",
    "content_error",
    "unknown",
]


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
    steps: list[PipelineStep] = Field(
        default_factory=lambda: [
            PipelineStep(name="crawling"),
            PipelineStep(name="summarizing"),
            PipelineStep(name="generating_overview"),
        ]
    )
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat: datetime | None = None

    # Stats from the crawl phase
    documents_found: int = 0
    documents_stored: int = 0

    # Per-URL crawl failures (e.g. robots.txt blocks, HTTP errors)
    crawl_errors: list[CrawlError] = Field(default_factory=list)
