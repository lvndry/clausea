"""The per-result callback streams every processed page out of the crawler.

Long crawls must persist progress incrementally rather than batching all storage at the
end, so the pipeline registers a ``result_callback`` that fires once for every processed
result — success AND failure — as it is produced. A None callback must be a zero-behavior
change no-op.
"""

import pytest

from src.crawler import ClauseaCrawler, CrawlResult

DOMAIN = "cb.test"
SEED = f"https://{DOMAIN}/"

# Seed links to one good policy page and one page that fails to fetch. Both must reach the
# callback: the success so it can be stored, the failure so the heartbeat still advances.
_GRAPH: dict[str, tuple[bool, list[dict[str, str]]]] = {
    SEED: (
        True,
        [
            {"url": f"https://{DOMAIN}/privacy", "text": ""},
            {"url": f"https://{DOMAIN}/dead", "text": ""},
        ],
    ),
    f"https://{DOMAIN}/privacy": (True, []),
    f"https://{DOMAIN}/dead": (False, []),
}


def _fake_fetch():
    async def fake_fetch(_session, url: str) -> CrawlResult:
        success, links = _GRAPH.get(url, (False, []))
        return CrawlResult(
            url=url,
            title="",
            content="x" * 600 if success else "",
            markdown="x",
            metadata={},
            status_code=200 if success else 0,
            success=success,
            discovered_links=links,
        )

    return fake_fetch


async def _no_sitemaps(_session, _base):
    return []


def _crawler(result_callback) -> ClauseaCrawler:
    return ClauseaCrawler(
        max_depth=3,
        max_pages=50,
        max_concurrent=1,
        respect_robots_txt=False,
        use_browser=False,
        allowed_domains=[DOMAIN],
        result_callback=result_callback,
    )


@pytest.mark.asyncio
async def test_callback_fires_once_per_processed_result_success_and_failure(monkeypatch):
    seen: list[tuple[str, bool]] = []

    async def callback(result: CrawlResult) -> None:
        seen.append((result.url, result.success))

    crawler = _crawler(callback)
    monkeypatch.setattr(crawler, "fetch_page", _fake_fetch())
    monkeypatch.setattr(crawler, "_discover_sitemap_urls", _no_sitemaps)

    await crawler.crawl(SEED, cleanup=False)

    seen_urls = [url for url, _ in seen]
    # Every processed URL reached the callback exactly once — including the failure.
    assert seen_urls.count(SEED) == 1
    assert seen_urls.count(f"https://{DOMAIN}/privacy") == 1
    assert seen_urls.count(f"https://{DOMAIN}/dead") == 1
    assert (f"https://{DOMAIN}/dead", False) in seen


@pytest.mark.asyncio
async def test_callback_fires_across_multiple_seeds(monkeypatch):
    seen: list[str] = []

    async def callback(result: CrawlResult) -> None:
        seen.append(result.url)

    crawler = _crawler(callback)
    monkeypatch.setattr(crawler, "fetch_page", _fake_fetch())
    monkeypatch.setattr(crawler, "_discover_sitemap_urls", _no_sitemaps)

    await crawler.crawl_multiple([SEED, SEED])

    # The instance-level callback survives the per-seed state reset, so both passes report.
    assert seen.count(f"https://{DOMAIN}/privacy") == 2


@pytest.mark.asyncio
async def test_none_callback_is_a_noop(monkeypatch):
    crawler = _crawler(None)
    monkeypatch.setattr(crawler, "fetch_page", _fake_fetch())
    monkeypatch.setattr(crawler, "_discover_sitemap_urls", _no_sitemaps)

    # No error, and the crawl still produces results exactly as before.
    results = await crawler.crawl(SEED, cleanup=False)
    assert any(r.url == f"https://{DOMAIN}/privacy" and r.success for r in results)


@pytest.mark.asyncio
async def test_recovered_render_retry_reaches_callback(monkeypatch):
    """A page recovered on the serial render-retry pass is streamed like any other result."""
    seen: list[str] = []

    async def callback(result: CrawlResult) -> None:
        seen.append(result.url)

    crawler = _crawler(callback)
    crawler._render_retry_queue = [f"https://{DOMAIN}/late"]

    async def fetch_page(_session, url: str) -> CrawlResult:
        return CrawlResult(
            url=url,
            title="",
            content="x" * 600,
            markdown="x",
            metadata={},
            status_code=200,
            success=True,
        )

    monkeypatch.setattr(crawler, "fetch_page", fetch_page)

    from typing import cast

    import aiohttp

    await crawler._drain_render_retries(session=cast(aiohttp.ClientSession, None))

    assert seen == [f"https://{DOMAIN}/late"]
