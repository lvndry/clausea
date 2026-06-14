"""Failed browser renders must be retried serially, never silently dropped.

A render that returns no page is usually a starvation/navigation timeout under
concurrency, not a genuinely empty page. Dropping it loses a policy document, so
such URLs are deferred to an end-of-crawl serial retry pass (recall over speed).
"""

from typing import cast
from unittest.mock import AsyncMock

import aiohttp
import pytest

from src.crawler import ClauseaCrawler, CrawlResult

# _drain_render_retries forwards this to fetch_page, which the tests mock, so the
# session is never used — a typed stand-in keeps the signature honest.
_NO_SESSION = cast(aiohttp.ClientSession, None)


def _result(url: str, *, success: bool) -> CrawlResult:
    return CrawlResult(
        url=url,
        title="",
        content="x" if success else "",
        markdown="",
        metadata={},
        status_code=200 if success else 0,
        success=success,
    )


@pytest.mark.asyncio
async def test_drain_recovers_a_render_that_succeeds_on_serial_retry(monkeypatch):
    crawler = ClauseaCrawler()
    crawler._render_retry_queue = ["https://example.com/privacy"]
    crawler.stats.failed_urls = 1
    crawler.failed_urls.add("https://example.com/privacy")

    fetch_page = AsyncMock(return_value=_result("https://example.com/privacy", success=True))
    monkeypatch.setattr(crawler, "fetch_page", fetch_page)

    await crawler._drain_render_retries(session=_NO_SESSION)

    assert len(crawler.results) == 1
    assert crawler.stats.crawled_urls == 1
    assert crawler.stats.failed_urls == 0
    assert crawler._render_retry_queue == []
    assert crawler._in_render_retry is False  # reset after draining


@pytest.mark.asyncio
async def test_drain_leaves_a_genuinely_failing_url_failed(monkeypatch):
    crawler = ClauseaCrawler()
    crawler._render_retry_queue = ["https://example.com/terms"]
    fetch_page = AsyncMock(return_value=_result("https://example.com/terms", success=False))
    monkeypatch.setattr(crawler, "fetch_page", fetch_page)

    await crawler._drain_render_retries(session=_NO_SESSION)

    assert crawler.results == []
    assert crawler.stats.crawled_urls == 0
    assert crawler._render_retry_queue == []


@pytest.mark.asyncio
async def test_drain_retries_each_url_at_most_once(monkeypatch):
    crawler = ClauseaCrawler()
    crawler._render_retry_queue = ["https://example.com/a", "https://example.com/a"]
    fetch_page = AsyncMock(return_value=_result("https://example.com/a", success=False))
    monkeypatch.setattr(crawler, "fetch_page", fetch_page)

    await crawler._drain_render_retries(session=_NO_SESSION)

    # Deduped: only one retry attempt despite the duplicate entry.
    assert fetch_page.await_count == 1


@pytest.mark.asyncio
async def test_drain_is_noop_when_queue_empty(monkeypatch):
    crawler = ClauseaCrawler()
    fetch_page = AsyncMock()
    monkeypatch.setattr(crawler, "fetch_page", fetch_page)
    await crawler._drain_render_retries(session=_NO_SESSION)
    fetch_page.assert_not_awaited()
