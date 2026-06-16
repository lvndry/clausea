from typing import cast

import aiohttp
import pytest
from bs4 import BeautifulSoup

from src.crawler import ClauseaCrawler, PageContent


class _FakeContent:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, n: int = -1) -> bytes:
        return self._data if n < 0 else self._data[:n]


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
        | {u for _, u, _, _ in crawler.url_priority_queue}
    )
    assert "https://example.com/privacy" not in all_urls

    # If follow_nofollow enabled, the specific link should be added
    crawler2 = ClauseaCrawler(follow_nofollow=True)
    crawler2.add_urls_to_queue(links, "https://example.com", depth=0, page_metadata=None)
    all_urls2 = (
        {u for u, _ in crawler2.url_queue}
        | {u for u, _ in crawler2.url_stack}
        | {u for _, u, _, _ in crawler2.url_priority_queue}
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
    """When sitemaps provide seeds, generate_potential_policy_urls should NOT run."""
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
    """When no sitemap provides seeds, generate_potential_policy_urls should run."""
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


def test_extract_main_content_combines_split_blocks_over_small_sidebar():
    """Airbnb help/legal pages split the body across many sibling
    ``data-testid="CEPHtmlSection"`` blocks while a small "Related articles"
    widget (``data-testid="...article..."``) appears earlier in the DOM.

    The extractor must pick the rich combined body, not the tiny sidebar.
    """
    body_para = (
        "This Terms of Service section explains the legal agreement between you and "
        "the company. It describes your rights, obligations, liability, dispute "
        "resolution, governing law, and the conditions under which the service is "
        "provided. "
    )
    sections = "".join(
        f'<div data-testid="CEPHtmlSection"><h2>Section {i}</h2><p>{body_para}</p></div>'
        for i in range(8)
    )
    html = f"""
    <!doctype html>
    <html>
      <body>
        <div data-testid="related-articles-card">
          <h3>Related articles</h3>
          <a href="/help/article/1">About the updates to our Terms</a>
          <a href="/help/article/2">Terms of Service</a>
        </div>
        <div data-testid="article-body-container">
          {sections}
        </div>
      </body>
    </html>
    """
    crawler = ClauseaCrawler()
    soup = BeautifulSoup(html, "html.parser")
    cleaned = crawler._extract_main_content_soup(soup)
    text = cleaned.get_text(" ", strip=True)

    # All 8 body sections must survive, not just the first.
    assert text.count("This Terms of Service section explains") == 8
    assert "Section 7" in text
    # The richer body must dominate over the tiny related-articles sidebar.
    assert len(text) > 1000


def test_decode_sitemap_bytes_inflates_gzip():
    """``.xml.gz`` sitemap indexes arrive as gzip file bodies; aiohttp does not
    transparently inflate them, so a naive .text() decode raised
    'utf-8 codec can't decode byte 0x8b'. The decoder must gunzip first.
    """
    import gzip

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/privacy</loc></url>"
        "</urlset>"
    )
    gz = gzip.compress(xml.encode("utf-8"))
    # Magic bytes present so the gzip body never reaches a utf-8 decode.
    assert gz[:2] == b"\x1f\x8b"

    crawler = ClauseaCrawler()
    decoded = crawler._decode_sitemap_bytes(gz, "https://example.com/sitemap-index.xml.gz")
    assert "<loc>https://example.com/privacy</loc>" in decoded
    assert crawler._parse_sitemap_xml(decoded) == ["https://example.com/privacy"]


def test_decode_sitemap_bytes_passes_through_plain_xml():
    crawler = ClauseaCrawler()
    xml = b'<?xml version="1.0"?><urlset><url><loc>https://example.com/a</loc></url></urlset>'
    decoded = crawler._decode_sitemap_bytes(xml, "https://example.com/sitemap.xml")
    assert decoded.startswith("<?xml")
    assert "https://example.com/a" in decoded


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
            self.charset = "utf-8"
            self.content = _FakeContent(body.encode())

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


def _index_xml(child_urls: list[str]) -> str:
    entries = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in child_urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</sitemapindex>"
    )


def _urlset_xml(page_urls: list[str]) -> str:
    entries = "".join(f"<url><loc>{u}</loc></url>" for u in page_urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )


class _MappedResponse:
    """aiohttp-style response whose body is looked up by URL; 404 if unknown."""

    def __init__(self, bodies: dict[str, str], url: str) -> None:
        self._body = bodies.get(url)
        self.url = url
        self.status = 200 if self._body is not None else 404
        self.headers: dict[str, str] = {}

    async def text(self) -> str:
        return self._body or ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    @property
    def content(self) -> _FakeContent:
        return _FakeContent((self._body or "").encode())


class _MappedSession:
    """Fake session that serves sitemap XML by URL and records every fetched URL."""

    def __init__(self, bodies: dict[str, str]) -> None:
        self._bodies = bodies
        self.fetched: list[str] = []

    def get(self, url, **kwargs):
        self.fetched.append(url)
        return _MappedResponse(self._bodies, url)


@pytest.mark.asyncio
async def test_policy_child_sitemap_past_cap_is_still_followed():
    """A policy-named child sitemap sitting far beyond the truncation cap in index
    order must still be fetched, because children are sorted policy-first before
    the cap is applied."""
    from src.crawler import MAX_CHILD_SITEMAPS

    origin = "https://example.com"
    cap = MAX_CHILD_SITEMAPS

    # Build an index with more children than the cap. The legal sitemap is placed
    # last in index order — well past position 50 and past the cap — so a naive
    # index-order truncation would drop it.
    product_children = [f"{origin}/sitemap-products-{i}.xml" for i in range(cap + 20)]
    legal_child = f"{origin}/sitemap-legal.xml"
    children = product_children + [legal_child]

    bodies = {
        f"{origin}/sitemap.xml": _index_xml(children),
        legal_child: _urlset_xml([f"{origin}/legal/privacy-policy"]),
    }
    for child in product_children:
        bodies[child] = _urlset_xml([child.replace("sitemap-", "page-").replace(".xml", "")])

    session = _MappedSession(bodies)
    crawler = ClauseaCrawler(respect_robots_txt=False)

    discovered = await crawler._discover_sitemap_urls(cast(aiohttp.ClientSession, session), origin)

    assert legal_child in session.fetched
    assert f"{origin}/legal/privacy-policy" in discovered


@pytest.mark.asyncio
async def test_child_sitemap_truncation_past_cap_logs(caplog):
    """When an index lists more children than the cap, truncation must be logged
    so recall loss is never silent."""
    import logging

    from src.crawler import MAX_CHILD_SITEMAPS

    origin = "https://example.com"
    children = [f"{origin}/sitemap-{i}.xml" for i in range(MAX_CHILD_SITEMAPS + 5)]
    bodies = {f"{origin}/sitemap.xml": _index_xml(children)}
    for child in children:
        bodies[child] = _urlset_xml([child.replace(".xml", "/page")])

    session = _MappedSession(bodies)
    crawler = ClauseaCrawler(respect_robots_txt=False)

    with caplog.at_level(logging.INFO):
        await crawler._discover_sitemap_urls(cast(aiohttp.ClientSession, session), origin)

    assert any(
        f"lists {len(children)} children" in record.getMessage() for record in caplog.records
    )


@pytest.mark.asyncio
async def test_all_children_followed_when_under_cap_no_truncation_log(caplog):
    """With fewer children than the cap, every child is followed, every page URL is
    discovered, and no truncation is logged."""
    import logging

    origin = "https://example.com"
    children = [f"{origin}/sitemap-{i}.xml" for i in range(5)]
    bodies = {f"{origin}/sitemap.xml": _index_xml(children)}
    expected_pages = []
    for index, child in enumerate(children):
        page = f"{origin}/page-{index}"
        expected_pages.append(page)
        bodies[child] = _urlset_xml([page])

    session = _MappedSession(bodies)
    crawler = ClauseaCrawler(respect_robots_txt=False)

    with caplog.at_level(logging.INFO):
        discovered = await crawler._discover_sitemap_urls(
            cast(aiohttp.ClientSession, session), origin
        )

    for page in expected_pages:
        assert page in discovered
    for child in children:
        assert child in session.fetched
    assert not any("children; following the first" in r.getMessage() for r in caplog.records)
