"""Static assets must never enter the crawl queue.

Regression: Next.js stylesheet/script chunks (e.g. ``/_next/static/chunks/x.css?dpl=...``)
were being queued and then escalated to a full Playwright render because a CSS
file fetched statically looks "content-insufficient". Each wasted up to a full
navigation timeout (30s). The URL filter must reject asset extensions, including
when a query string or fragment follows the extension.
"""

import pytest

from src.crawler import ClauseaCrawler

BASE = "https://example.com"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/_next/static/chunks/05vxco8axmog1.css?dpl=dpl_abc",
        "https://example.com/_next/static/chunks/app.js",
        "https://example.com/assets/main.mjs?v=2",
        "https://example.com/bundle.js.map",
        "https://example.com/fonts/inter.woff2",
        "https://example.com/fonts/icons.ttf",
        "https://example.com/img/logo.png",
        "https://example.com/img/hero.jpg?w=800",
        "https://example.com/icons/sprite.svg",
    ],
)
def test_static_assets_are_not_crawled(url: str):
    crawler = ClauseaCrawler()
    assert crawler.should_crawl_url(url, BASE, 0) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/privacy",
        "https://example.com/legal/terms",
        "https://example.com/company/privacy-policy",
        "https://example.com/policies/cookies?lang=en",
    ],
)
def test_real_pages_are_still_crawled(url: str):
    crawler = ClauseaCrawler()
    assert crawler.should_crawl_url(url, BASE, 0) is True
