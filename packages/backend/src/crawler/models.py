"""Data containers that flow through the crawler and into the pipeline.

**What it contains**
- ``CrawlResult``: outcome of one crawled URL — raw HTML, extracted text, HTTP metadata,
  policy-score, doc-type classification, and error info.  This is the primary output
  of the crawler and input to the pipeline.
- ``CrawlStats``: aggregate counters (pages visited, errors, cache hits, robots-blocked)
  accumulated during a crawl iteration for logging and monitoring.
- ``PageContent``: intermediate container holding cleaned text, title, and content hash
  after HTML-to-text extraction but before classification.
- ``StaticFetchResult``: low-level HTTP fetch result with status, headers, body bytes,
  and redirect chain — used internally by the HTTP stack.

**What it prevents**
Ad-hoc dicts or unstructured tuples being passed between crawler internals.
Pydantic/dataclass validation ensures every field has the expected type.
"""

import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class StaticFetchResult:
    url: str
    status_code: int
    content_type: str
    body: str
    raw_bytes: bytes | None = None
    headers: dict[str, str] = dataclass_field(default_factory=dict)
    blocked_by_robots_txt: bool = False
    error_message: str | None = None
    cached: bool = False
    resolved_url: str | None = None

    def to_failed_crawl_result(self) -> "CrawlResult":
        return CrawlResult(
            url=self.url,
            title="",
            content="",
            markdown="",
            metadata={"content-type": self.content_type} if self.content_type else {},
            status_code=self.status_code,
            success=False,
            error_message=self.error_message or f"HTTP {self.status_code}",
            blocked_by_robots_txt=self.blocked_by_robots_txt,
        )


@dataclass
class PageContent:
    text: str
    markdown: str
    title: str
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)
    discovered_links: list[dict[str, str]] = dataclass_field(default_factory=list)
    status_code: int = 200


class CrawlResult(BaseModel):
    url: str = Field(description="The final URL after redirects")
    title: str = Field(description="The page title")
    content: str = Field(description="The raw text content of the page")
    markdown: str = Field(description="The content converted to Markdown format")
    metadata: dict[str, Any] = Field(
        description="Metadata extracted from the page (e.g., tags, headers)"
    )
    status_code: int = Field(description="The HTTP status code of the response")
    success: bool = Field(description="Whether the crawl was successful")
    error_message: str | None = Field(
        default=None, description="Detailed error message if crawl failed"
    )
    legal_score: float | None = Field(
        default=None,
        description="Content-based legal relevance score (0.0–1.0); None if not analyzed",
    )
    discovered_links: list[dict[str, str]] = Field(
        default_factory=list, description="List of links with both URL and original anchor text"
    )
    blocked_by_robots_txt: bool = Field(
        default=False, description="True if the fetch was refused by the site's robots.txt"
    )


class CrawlStats(BaseModel):
    total_urls: int = 0
    crawled_urls: int = 0
    failed_urls: int = 0
    start_time: float = Field(default_factory=time.time)
    # Set to True when crawled_urls == 0 and every attempted URL was refused by the
    # site's robots.txt. Lets the pipeline emit a targeted "robots_blocked" job
    # status rather than the generic "no_documents" outcome.
    all_seeds_robots_blocked: bool = False

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    @property
    def crawl_rate(self) -> float:
        return self.crawled_urls / self.elapsed_time if self.elapsed_time > 0 else 0
