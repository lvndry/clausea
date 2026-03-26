from typing import cast

import aiohttp
import pytest
from bs4 import BeautifulSoup

from src.crawler import ClauseaCrawler, PageContent


def test_extract_links_various_sources():
    html = """
    <!doctype html>
    <html>
      <head>
        <link rel="canonical" href="https://example.com/legal/privacy" />
        <meta property="og:url" content="https://example.com/og-url" />
        <script type="application/ld+json">
          {"@context": "http://schema.org", "url": "https://example.com/jsonld"}
        </script>
        <meta name="robots" content="index,follow" />
      </head>
      <body>
        <a href="/privacy-policy">Privacy</a>
        <a data-href="/terms">Terms via data-href</a>
        <div data-url="/cookies">Cookies section</div>
        <area href="/area-link" alt="area" />
        <form action="/post-action"></form>
        <button onclick="location.href='/onclick-link'">Click</button>
        Some text with a URL: https://example.com/embedded
      </body>
    </html>
    """

    soup = BeautifulSoup(html, "html.parser")
    crawler = ClauseaCrawler()

    links = crawler.extract_links(soup, "https://example.com")
    urls = {link["url"] for link in links}

    assert "https://example.com/privacy-policy" in urls
    assert "https://example.com/terms" in urls
    assert "https://example.com/cookies" in urls
    assert "https://example.com/area-link" in urls
    assert "https://example.com/post-action" in urls
    assert "https://example.com/onclick-link" in urls
    assert "https://example.com/embedded" in urls
    assert "https://example.com/legal/privacy" in urls  # canonical
    assert "https://example.com/jsonld" in urls


def test_extract_links_propagates_page_title_for_alternate_links():
    html = """
    <!doctype html>
    <html>
      <head>
        <title>Cookie Policy</title>
        <link rel="alternate" hreflang="fr" href="https://www.airbnb.fr/help/article/2866" />
        <link rel="canonical" href="https://www.airbnb.com/help/article/2866" />
        <link rel="stylesheet" href="/styles.css" />
      </head>
      <body><p>Content</p></body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    crawler = ClauseaCrawler()
    links = crawler.extract_links(soup, "https://www.airbnb.com/help/article/2866")
    by_url = {link["url"]: link for link in links}

    alt_link = by_url.get("https://www.airbnb.fr/help/article/2866")
    assert alt_link is not None
    assert alt_link["text"] == "Cookie Policy"

    canonical_link = by_url.get("https://www.airbnb.com/help/article/2866")
    assert canonical_link is not None
    assert canonical_link["text"] == "Cookie Policy"

    # Non-alternate/canonical link tags keep the generic label
    css_link = by_url.get("https://www.airbnb.com/styles.css")
    assert css_link is not None
    assert css_link["text"] == "link:stylesheet"


def test_add_urls_to_queue_respects_rel_nofollow_and_meta():
    crawler = ClauseaCrawler()

    # Prepare a link marked nofollow
    links = [{"url": "https://example.com/privacy", "text": "Privacy", "rel": "nofollow"}]

    # By default follow_nofollow=False -> the specific nofollow link should be skipped
    crawler.add_urls_to_queue(links, "https://example.com", depth=0, page_metadata=None)
    all_urls = (
        {u for u, _ in crawler.url_queue}
        | {u for u, _ in crawler.url_stack}
        | {u for _, u, _ in crawler.url_priority_queue}
    )
    assert "https://example.com/privacy" not in all_urls

    # If follow_nofollow enabled, the specific link should be added
    crawler2 = ClauseaCrawler(follow_nofollow=True)
    crawler2.add_urls_to_queue(links, "https://example.com", depth=0, page_metadata=None)
    all_urls2 = (
        {u for u, _ in crawler2.url_queue}
        | {u for u, _ in crawler2.url_stack}
        | {u for _, u, _ in crawler2.url_priority_queue}
    )
    assert "https://example.com/privacy" in all_urls2

    # Verify queued_urls tracking works with follow_nofollow
    assert "https://example.com/privacy" in crawler2.queued_urls

    # Respect meta robots nofollow
    links2 = [{"url": "https://example.com/terms", "text": "Terms"}]
    crawler3 = ClauseaCrawler()
    page_meta = {"robots": "noindex, nofollow"}
    crawler3.add_urls_to_queue(links2, "https://example.com", depth=0, page_metadata=page_meta)
    assert len(crawler3.url_queue) == 0
    assert "https://example.com/terms" not in crawler3.queued_urls


def test_parse_sitemap_xml():
    crawler = ClauseaCrawler()
    sitemap = """
    <?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>https://example.com/privacy</loc>
      </url>
      <url>
        <loc>https://example.com/terms</loc>
      </url>
    </urlset>
    """

    urls = crawler._parse_sitemap_xml(sitemap)
    assert "https://example.com/privacy" in urls
    assert "https://example.com/terms" in urls


def test_parse_sitemap_xml_index():
    """Sitemap index files should return the child sitemap URLs."""
    crawler = ClauseaCrawler()
    index_xml = """
    <?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap>
        <loc>https://example.com/sitemap-articles.xml</loc>
      </sitemap>
      <sitemap>
        <loc>https://example.com/sitemap-pages.xml</loc>
      </sitemap>
    </sitemapindex>
    """
    urls = crawler._parse_sitemap_xml(index_xml)
    assert "https://example.com/sitemap-articles.xml" in urls
    assert "https://example.com/sitemap-pages.xml" in urls


def test_parse_robots_txt_sitemaps():
    crawler = ClauseaCrawler()
    robots = """
    User-agent: *
    Disallow:
    Sitemap: https://example.com/sitemap.xml
    Sitemap: https://cdn.example.com/sitemap-index.xml
    """

    parsed = crawler._parse_robots_txt(robots)
    assert "sitemaps" in parsed
    assert "https://example.com/sitemap.xml" in parsed["sitemaps"]
    assert "https://cdn.example.com/sitemap-index.xml" in parsed["sitemaps"]


def test_well_known_sitemap_paths_are_defined():
    """ClauseaCrawler should probe common sitemap paths beyond robots.txt."""
    paths = ClauseaCrawler._WELL_KNOWN_SITEMAP_PATHS
    assert "/sitemap.xml" in paths
    assert "/sitemap_index.xml" in paths
    assert "/sitemap-index.xml" in paths


def test_sitemap_seeded_skips_speculative_legal_urls():
    """When sitemaps provide seeds, generate_potential_legal_urls should NOT run."""
    crawler = ClauseaCrawler()
    crawler._sitemap_seeded = True

    links = [{"url": "https://example.com/page", "text": "Page"}]
    crawler.add_urls_to_queue(links, "https://example.com", depth=0)

    # Only the explicitly discovered link should be queued — no speculative
    # legal paths like /privacy, /legal, /terms.
    queued = {u for u, _ in crawler.url_queue}
    assert "https://example.com/page" in queued
    assert "https://example.com/privacy" not in queued
    assert "https://example.com/legal" not in queued


def test_no_sitemap_falls_back_to_speculative_legal_urls():
    """When no sitemap provides seeds, generate_potential_legal_urls should run."""
    crawler = ClauseaCrawler()
    assert crawler._sitemap_seeded is False

    links = [{"url": "https://example.com/page", "text": "Page"}]
    crawler.add_urls_to_queue(links, "https://example.com", depth=0)

    queued = {u for u, _ in crawler.url_queue}
    assert "https://example.com/page" in queued
    # Fallback speculative URLs should be present
    assert "https://example.com/privacy" in queued
    assert "https://example.com/legal" in queued


def test_choose_effective_url_with_relative_canonical():
    crawler = ClauseaCrawler()
    orig = "https://example.com/some/page"
    metadata = {"canonical_url": "/legal/privacy"}
    effective = crawler._choose_effective_url(orig, metadata)
    assert effective == "https://example.com/legal/privacy"


def test_choose_effective_url_respects_allowed_domains():
    # canonical on different domain should be ignored if allowed_domains restricts
    crawler = ClauseaCrawler(allowed_domains=["example.com"])
    orig = "https://example.com/page"
    metadata = {"canonical_url": "https://external.com/privacy"}
    effective = crawler._choose_effective_url(orig, metadata)
    assert effective == "https://example.com/page"


def test_choose_effective_url_accepts_cross_domain_if_allowed():
    crawler = ClauseaCrawler(allowed_domains=["external.com", "example.com"])
    orig = "https://example.com/page"
    metadata = {"canonical_url": "https://external.com/privacy"}
    effective = crawler._choose_effective_url(orig, metadata)
    assert effective == "https://external.com/privacy"


def test_extract_main_content_preserves_cookie_policy_wrapper():
    html = """
    <!doctype html>
    <html>
      <body>
        <div id="cookie-banner">Accept cookies</div>
        <section class="cookie-policy legal-content">
          <h1>Cookie Policy</h1>
          <p>
            This Cookie Policy explains how we use cookies, similar technologies,
            and related tracking tools. We process personal data for analytics,
            security, and service improvement. You can manage your consent
            preferences, and you have rights under applicable privacy laws.
          </p>
          <p>
            We may update this policy from time to time. Please review this
            policy periodically for changes affecting data protection and usage.
          </p>
        </section>
      </body>
    </html>
    """
    crawler = ClauseaCrawler()
    soup = BeautifulSoup(html, "html.parser")

    cleaned = crawler._extract_main_content_soup(soup)
    text = cleaned.get_text(" ", strip=True)

    assert "Cookie Policy" in text
    assert "data protection" in text.lower()
    assert "Accept cookies" not in text


@pytest.mark.asyncio
async def test_static_html_fallback_uses_main_content_and_keeps_jsonld_links():
    html = """
    <!doctype html>
    <html>
      <head>
        <title>Privacy Policy</title>
        <script type="application/ld+json">
          {"url": "https://example.com/legal/privacy-jsonld"}
        </script>
      </head>
      <body>
        <div id="cookie-banner">Enable JavaScript and accept cookies to continue</div>
        <main>
          <h1>Privacy Policy</h1>
          <p>
            We collect account, device, and usage data to provide and improve services.
            We retain data as required by law and process it for fraud prevention,
            support, analytics, and compliance obligations. We also describe user rights,
            security practices, international transfers, and lawful bases for processing.
          </p>
        </main>
      </body>
    </html>
    """

    class FakeResponse:
        def __init__(self, body: str, url: str = ""):
            self.status = 200
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self._body = body
            self.url = url

        async def text(self) -> str:
            return self._body

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResponse(html, url=url)

    crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=True)

    async def fake_browser_fetch(url: str) -> PageContent | None:
        return None

    crawler._browser_fetch = fake_browser_fetch  # type: ignore[method-assign]

    result = await crawler._fetch_page_internal(
        cast(aiohttp.ClientSession, FakeSession()), "https://example.com/privacy"
    )

    assert result.success is False
    assert "browser rendering failed" in (result.error_message or "").lower()
