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
    completed_at: datetime | None = None

    # Stats from the crawl phase
    documents_found: int = 0
    documents_stored: int = 0
