"""Per-domain politeness and browser render tuning guards."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.crawler import ClauseaCrawler
from src.crawler.rate_limiter import DomainRateLimiter
from src.crawler.robots import RobotsTxtChecker


def test_get_crawl_delay_reads_cached_robots_rules() -> None:
    checker = RobotsTxtChecker()
    checker.robots_cache["https://example.com"] = {
        "user_agents": {
            "*": {"disallow": [], "allow": [], "crawl_delay": 4.0},
        }
    }

    assert checker.get_crawl_delay("https://example.com/privacy") == 4.0
    assert checker.get_crawl_delay("https://other.com/privacy") is None


@pytest.mark.asyncio
async def test_rate_limiter_honors_min_delay_override() -> None:
    limiter = DomainRateLimiter(delay_between_requests=1.0, jitter=0.0)
    url = "https://example.com/privacy"

    await limiter.rate_limit(url)
    start = time.time()
    await limiter.rate_limit(url, min_delay=2.5)
    elapsed = time.time() - start

    assert elapsed >= 2.4


@pytest.mark.asyncio
async def test_crawler_rate_limit_uses_robots_delay() -> None:
    crawler = ClauseaCrawler(delay_between_requests=1.0)
    assert crawler.robots_checker is not None
    crawler.robots_checker.robots_cache["https://example.com"] = {
        "user_agents": {"*": {"disallow": [], "allow": [], "crawl_delay": 3.0}}
    }

    with patch.object(crawler.rate_limiter, "rate_limit", new=AsyncMock()) as mock_limit:
        await crawler.rate_limit("https://example.com/terms")
        mock_limit.assert_awaited_once_with("https://example.com/terms", min_delay=3.0)


def test_browser_failure_backoff_caps_per_domain() -> None:
    crawler = ClauseaCrawler(
        browser_extra_delay=2.0,
        browser_failure_backoff_s=5.0,
        browser_failure_backoff_max_s=12.0,
    )
    url = "https://spa.example/privacy"

    crawler._note_browser_domain_delay(url, failed=False)
    assert crawler._domain_extra_delay["spa.example"] == 2.0

    crawler._note_browser_domain_delay(url, failed=True)
    assert crawler._domain_extra_delay["spa.example"] == 7.0

    crawler._note_browser_domain_delay(url, failed=True)
    assert crawler._domain_extra_delay["spa.example"] == 12.0


@pytest.mark.asyncio
async def test_try_dismiss_consent_banner_clicks_visible_accept() -> None:
    from src.crawler.browser import try_dismiss_consent_banner

    page = MagicMock()
    locator = MagicMock()
    locator.is_visible = AsyncMock(return_value=True)
    locator.click = AsyncMock()
    page.locator.return_value.first = locator

    clicked = await try_dismiss_consent_banner(page)

    assert clicked is True
    locator.click.assert_awaited_once()
