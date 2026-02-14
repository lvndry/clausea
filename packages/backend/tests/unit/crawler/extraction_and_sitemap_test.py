from bs4 import BeautifulSoup

from src.crawler import ClauseaCrawler


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

    # Respect meta robots nofollow
    links2 = [{"url": "https://example.com/terms", "text": "Terms"}]
    crawler3 = ClauseaCrawler()
    page_meta = {"robots": "noindex, nofollow"}
    crawler3.add_urls_to_queue(links2, "https://example.com", depth=0, page_metadata=page_meta)
    assert len(crawler3.url_queue) == 0


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
