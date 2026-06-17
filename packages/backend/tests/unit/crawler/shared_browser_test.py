"""The browser is shared process-wide and a failed launch degrades gracefully.

Each pipeline builds its own crawler; before this, each launched its own Camoufox, so
two memory-heavy Firefox instances coexisted in the worker and deadlocked. All crawlers
now render through one shared browser, and a stuck/failed launch returns None (deferred
render-retry) instead of hanging until the 2h pipeline cap.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.crawler as crawler_module
from src.crawler import ClauseaCrawler, _get_global_browser_slot


def test_render_slot_is_shared_across_crawler_instances():
    crawler_module._global_browser_semaphores.clear()
    slot_a = ClauseaCrawler(browser_concurrency=2)._browser_render_slot()
    slot_b = ClauseaCrawler(browser_concurrency=2)._browser_render_slot()
    # Same object → concurrent pipelines share one cap, not one-per-crawler.
    assert slot_a is slot_b
    assert slot_a is _get_global_browser_slot(2)


@pytest.mark.asyncio
async def test_browser_fetch_returns_none_when_launch_fails(monkeypatch):
    crawler = ClauseaCrawler(use_browser=True)
    monkeypatch.setattr(
        crawler, "_setup_browser", AsyncMock(side_effect=TimeoutError("launch hung"))
    )
    # A failed/timed-out launch is a render failure, not a fatal crawl error.
    assert await crawler._browser_fetch("https://example.com/privacy") is None


@pytest.mark.asyncio
async def test_browser_fetch_waits_briefly_for_load_state(monkeypatch):
    """Render path navigates on domcontentloaded then settles briefly on 'load' so partial-SSR
    bodies are captured whole; a load timeout is swallowed, not fatal."""

    crawler = ClauseaCrawler(use_browser=True)
    url = "https://example.com/privacy"
    page = AsyncMock()
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    page.title = AsyncMock(return_value="Privacy")
    page.content = AsyncMock(
        return_value=f"<html><head><title>Privacy</title></head><body>{'privacy ' * 200}</body></html>"
    )
    page.set_extra_http_headers = AsyncMock()
    page.close = AsyncMock()
    # Load never fires (SPA): the wait must time out and be swallowed, not abort the fetch.
    page.wait_for_load_state = AsyncMock(side_effect=TimeoutError("load never fired"))
    page.url = url

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)

    monkeypatch.setattr(crawler, "_setup_browser", AsyncMock(return_value=(AsyncMock(), context)))
    monkeypatch.setattr(crawler_module, "_block_heavy_assets", AsyncMock())

    result = await crawler._browser_fetch(url)

    assert result is not None
    assert result.status_code == 200
    page.goto.assert_awaited_once()
    assert page.goto.await_args.kwargs["wait_until"] == "domcontentloaded"
    page.wait_for_load_state.assert_awaited_once()
    assert page.wait_for_load_state.await_args.args[0] == "load"
