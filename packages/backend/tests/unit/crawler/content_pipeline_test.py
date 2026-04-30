"""Tests for the refactored fetch pipeline: _content_is_sufficient, _extract_page_content, and
the static-to-browser fallback orchestrator."""

from typing import cast

import aiohttp
import pytest

from src.crawler import ClauseaCrawler, PageContent, StaticFetchResult


class _FakeContent:
    """Minimal mock of aiohttp's StreamReader for tests."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, n: int = -1) -> bytes:
        return self._data if n < 0 else self._data[:n]


# ---------------------------------------------------------------------------
# _content_is_sufficient
# ---------------------------------------------------------------------------


class TestContentIsSufficient:
    def _crawler(self) -> ClauseaCrawler:
        return ClauseaCrawler(respect_robots_txt=False)

    def test_empty_text_is_insufficient(self):
        crawler = self._crawler()
        page = PageContent(text="", markdown="", title="")
        assert crawler._content_is_sufficient(page, "https://example.com/privacy") is False

    def test_short_text_is_insufficient(self):
        crawler = self._crawler()
        page = PageContent(text="a" * 100, markdown="short", title="Page")
        assert crawler._content_is_sufficient(page, "https://example.com/privacy") is False

    def test_garbled_content_is_insufficient(self):
        crawler = self._crawler()
        garbled = "a" * 50 + "\x00\x01\x02" * 40 + "b" * 500
        page = PageContent(text=garbled, markdown=garbled, title="Page")
        assert crawler._content_is_sufficient(page, "https://example.com") is False

    def test_js_required_markers_is_insufficient(self):
        crawler = self._crawler()
        text = "Please enable javascript to continue viewing this page. " * 20
        page = PageContent(text=text, markdown=text, title="Page")
        assert crawler._content_is_sufficient(page, "https://example.com") is False

    def test_high_value_url_with_thin_content_is_insufficient(self):
        crawler = self._crawler()
        text = "Privacy Policy " * 60
        page = PageContent(text=text, markdown=text, title="Privacy Policy")
        assert len(text) < 1000
        assert crawler._content_is_sufficient(page, "https://example.com/privacy-policy") is False

    def test_good_content_is_sufficient(self):
        crawler = self._crawler()
        text = "This is a comprehensive privacy policy document. " * 40
        page = PageContent(text=text, markdown=text, title="Privacy Policy")
        assert len(text) > 1000
        assert crawler._content_is_sufficient(page, "https://example.com/privacy-policy") is True

    def test_normal_url_medium_content_is_sufficient(self):
        crawler = self._crawler()
        text = "Hello world. " * 80
        page = PageContent(text=text, markdown=text, title="Page")
        assert len(text) >= 500
        assert crawler._content_is_sufficient(page, "https://example.com/about") is True


# ---------------------------------------------------------------------------
# _extract_page_content
# ---------------------------------------------------------------------------


class TestExtractPageContent:
    def _crawler(self) -> ClauseaCrawler:
        return ClauseaCrawler(respect_robots_txt=False)

    @pytest.mark.asyncio
    async def test_html_extraction(self):
        html = """
        <html>
          <head><title>Privacy Policy</title></head>
          <body>
            <main>
              <h1>Privacy Policy</h1>
              <p>We collect personal data to provide services.</p>
            </main>
            <a href="/terms">Terms</a>
          </body>
        </html>
        """
        raw = StaticFetchResult(
            url="https://example.com/privacy",
            status_code=200,
            content_type="text/html; charset=utf-8",
            body=html,
        )
        crawler = self._crawler()
        page = await crawler._extract_page_content(raw, "https://example.com/privacy")
        assert page is not None
        assert "Privacy Policy" in page.title
        assert "personal data" in page.text
        assert page.status_code == 200

    @pytest.mark.asyncio
    async def test_plain_text_extraction(self):
        raw = StaticFetchResult(
            url="https://example.com/privacy.txt",
            status_code=200,
            content_type="text/plain",
            body="Privacy Policy\nWe respect your data.\nContact us at privacy@example.com",
        )
        crawler = self._crawler()
        page = await crawler._extract_page_content(raw, "https://example.com/privacy.txt")
        assert page is not None
        assert "Privacy Policy" in page.title
        assert page.discovered_links == []

    @pytest.mark.asyncio
    async def test_xml_sitemap_extraction(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/privacy</loc></url>
          <url><loc>https://example.com/terms</loc></url>
        </urlset>
        """
        raw = StaticFetchResult(
            url="https://example.com/sitemap.xml",
            status_code=200,
            content_type="application/xml",
            body=xml,
        )
        crawler = self._crawler()
        page = await crawler._extract_page_content(raw, "https://example.com/sitemap.xml")
        assert page is not None
        urls = {link["url"] for link in page.discovered_links}
        assert "https://example.com/privacy" in urls
        assert "https://example.com/terms" in urls

    @pytest.mark.asyncio
    async def test_unsupported_content_type_returns_none(self):
        raw = StaticFetchResult(
            url="https://example.com/image.png",
            status_code=200,
            content_type="image/png",
            body="",
            raw_bytes=b"\x89PNG",
        )
        crawler = self._crawler()
        page = await crawler._extract_page_content(raw, "https://example.com/image.png")
        assert page is None

    @pytest.mark.asyncio
    async def test_cached_304_returns_page_content(self):
        raw = StaticFetchResult(
            url="https://example.com/privacy",
            status_code=304,
            content_type="",
            body="",
            cached=True,
        )
        crawler = self._crawler()
        page = await crawler._extract_page_content(raw, "https://example.com/privacy")
        assert page is not None
        assert page.metadata.get("cached") is True


# ---------------------------------------------------------------------------
# Orchestrator: static-to-browser fallback
# ---------------------------------------------------------------------------


class TestFetchPageInternalOrchestration:
    @pytest.mark.asyncio
    async def test_good_static_content_skips_browser(self):
        """When static fetch returns sufficient content, browser is never called."""
        html = """
        <html><head><title>Privacy Policy</title></head>
        <body><main><p>{}</p></main></body>
        </html>
        """.format("We collect data for analytics. " * 80)

        class FakeResponse:
            def __init__(self, url: str):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = url
                self.charset = "utf-8"
                self.content = _FakeContent(html.encode())

            async def text(self):
                return html

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse(url)

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=True)

        browser_called = False
        original_browser_fetch = crawler._browser_fetch

        async def tracking_browser_fetch(url: str) -> PageContent | None:
            nonlocal browser_called
            browser_called = True
            return await original_browser_fetch(url)

        crawler._browser_fetch = tracking_browser_fetch  # type: ignore[method-assign]

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), "https://example.com/privacy"
        )
        assert result.success is True
        assert "Privacy Policy" in result.title
        assert browser_called is False

    @pytest.mark.asyncio
    async def test_thin_static_content_triggers_browser_fallback(self):
        """When static fetch returns thin content, browser is tried."""
        thin_html = "<html><head><title>App</title></head><body>Loading...</body></html>"

        class FakeResponse:
            def __init__(self, url: str):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = url
                self.charset = "utf-8"
                self.content = _FakeContent(thin_html.encode())

            async def text(self):
                return thin_html

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse(url)

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=True)

        browser_called = False

        async def fake_browser_fetch(url: str) -> PageContent | None:
            nonlocal browser_called
            browser_called = True
            return PageContent(
                text="Full rendered privacy policy content " * 50,
                markdown="Full rendered privacy policy content " * 50,
                title="Privacy Policy",
                metadata={},
                discovered_links=[],
                status_code=200,
            )

        crawler._browser_fetch = fake_browser_fetch  # type: ignore[method-assign]

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), "https://example.com/privacy"
        )
        assert result.success is True
        assert browser_called is True
        assert "Full rendered" in result.content

    @pytest.mark.asyncio
    async def test_browser_failure_falls_back_to_static(self):
        """When browser returns None, the static content is used."""
        thin_html = "<html><head><title>Page</title></head><body>Loading...</body></html>"

        class FakeResponse:
            def __init__(self, url: str):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = url
                self.charset = "utf-8"
                self.content = _FakeContent(thin_html.encode())

            async def text(self):
                return thin_html

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse(url)

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=True)

        async def failing_browser_fetch(url: str) -> PageContent | None:
            return None

        crawler._browser_fetch = failing_browser_fetch  # type: ignore[method-assign]

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), "https://example.com/page"
        )
        assert result.success is False
        assert "browser rendering failed" in (result.error_message or "").lower()

    @pytest.mark.asyncio
    async def test_no_browser_when_disabled(self):
        """When use_browser=False, even thin content doesn't trigger browser."""
        thin_html = "<html><head><title>Page</title></head><body>Hi</body></html>"

        class FakeResponse:
            def __init__(self, url: str):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = url
                self.charset = "utf-8"
                self.content = _FakeContent(thin_html.encode())

            async def text(self):
                return thin_html

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse(url)

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=False)

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), "https://example.com/page"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_http_404_skips_browser_and_extraction(self):
        """HTTP 404 should fail fast without browser or HTML parsing."""
        from yarl import URL as YarlURL

        class FakeResponse:
            def __init__(self):
                self.status = 404
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = YarlURL("https://example.com/missing")
                self.charset = "utf-8"
                self.content = _FakeContent(b"<html><body>Not found</body></html>")

            async def text(self):
                return "<html><body>Not found</body></html>"

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse()

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=True)

        browser_called = False

        async def fake_browser_fetch(url: str) -> PageContent | None:
            nonlocal browser_called
            browser_called = True
            return None

        crawler._browser_fetch = fake_browser_fetch  # type: ignore[method-assign]

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), "https://example.com/missing"
        )
        assert result.success is False
        assert result.status_code == 404
        assert (result.error_message or "") == "Not found (404)"
        assert browser_called is False

    @pytest.mark.asyncio
    async def test_soft_404_path_skips_browser(self):
        """Redirect target /404 (200 shell) should skip browser retry."""
        from yarl import URL as YarlURL

        thin_html = "<html><head><title>Oops</title></head><body>404</body></html>"
        final_url = "https://www.example.com/404?fromUrl=/docs"

        class FakeResponse:
            def __init__(self):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = YarlURL(final_url)
                self.charset = "utf-8"
                self.content = _FakeContent(thin_html.encode())

            async def text(self):
                return thin_html

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse()

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=True)

        browser_called = False

        async def fake_browser_fetch(url: str) -> PageContent | None:
            nonlocal browser_called
            browser_called = True
            return None

        crawler._browser_fetch = fake_browser_fetch  # type: ignore[method-assign]

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), "https://www.example.com/docs"
        )
        assert result.success is False
        assert result.url == final_url
        assert (result.error_message or "") == "Not found (404)"
        assert browser_called is False


class TestUrlLooksLikeNotFoundLanding:
    def test_tiktok_style_404_query(self):
        assert ClauseaCrawler._url_looks_like_not_found_landing(
            "https://www.tiktok.com/404?fromUrl=/policy/terms"
        )

    def test_plain_404_path(self):
        assert ClauseaCrawler._url_looks_like_not_found_landing("https://example.com/404")

    def test_locale_prefix_404(self):
        assert ClauseaCrawler._url_looks_like_not_found_landing("https://example.com/en/404")

    def test_normal_legal_path_not_not_found(self):
        assert not ClauseaCrawler._url_looks_like_not_found_landing(
            "https://www.tiktok.com/legal/page/eea/terms-of-service/en"
        )


# ---------------------------------------------------------------------------
# Redirect URL tracking
# ---------------------------------------------------------------------------


class TestRedirectURLTracking:
    """The crawler should capture the final URL after HTTP redirects so that
    link extraction, deduplication, and stored document URLs are correct.

    A common real-world case: disneyplus.com/legal/privacy-policy redirects
    to disneyplus.com/en-gb/legal/privacy-policy.
    """

    @pytest.mark.asyncio
    async def test_static_fetch_captures_resolved_url(self):
        """StaticFetchResult.resolved_url should reflect the final redirect target."""
        from yarl import URL as YarlURL

        original_url = "https://www.example.com/legal/privacy-policy"
        redirected_url = "https://www.example.com/en-gb/legal/privacy-policy"

        html = "<html><head><title>Privacy Policy</title></head><body><p>We collect data.</p></body></html>"

        class FakeResponse:
            def __init__(self):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                # aiohttp exposes the final URL via response.url (a yarl.URL)
                self.url = YarlURL(redirected_url)
                self.charset = "utf-8"
                self.content = _FakeContent(html.encode())

            async def text(self):
                return html

            async def read(self):
                return html.encode()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse()

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=False)

        raw = await crawler._static_fetch(cast(aiohttp.ClientSession, FakeSession()), original_url)

        assert raw.resolved_url == redirected_url, (
            f"resolved_url should be the redirect target, got {raw.resolved_url}"
        )

    @pytest.mark.asyncio
    async def test_fetch_page_internal_uses_resolved_url_in_result(self):
        """CrawlResult.url should be the final URL after redirects."""
        from yarl import URL as YarlURL

        original_url = "https://www.example.com/legal/privacy-policy"
        redirected_url = "https://www.example.com/en-gb/legal/privacy-policy"

        html = """
        <html><head><title>Privacy Policy</title></head>
        <body><main><p>{}</p></main></body>
        </html>
        """.format("We collect personal data for analytics. " * 80)

        class FakeResponse:
            def __init__(self):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = YarlURL(redirected_url)
                self.charset = "utf-8"
                self.content = _FakeContent(html.encode())

            async def text(self):
                return html

            async def read(self):
                return html.encode()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse()

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=False)

        result = await crawler._fetch_page_internal(
            cast(aiohttp.ClientSession, FakeSession()), original_url
        )

        assert result.success is True
        assert result.url == redirected_url, (
            f"CrawlResult.url should be the redirected URL, got {result.url}"
        )

    @pytest.mark.asyncio
    async def test_redirect_target_added_to_visited_urls(self):
        """The redirect target should be marked as visited to prevent re-crawling."""
        from yarl import URL as YarlURL

        original_url = "https://www.example.com/legal/privacy-policy"
        redirected_url = "https://www.example.com/en-gb/legal/privacy-policy"

        html = """
        <html><head><title>Privacy Policy</title></head>
        <body><main><p>{}</p></main></body>
        </html>
        """.format("We collect personal data for analytics. " * 80)

        class FakeResponse:
            def __init__(self):
                self.status = 200
                self.headers = {"content-type": "text/html; charset=utf-8"}
                self.url = YarlURL(redirected_url)
                self.charset = "utf-8"
                self.content = _FakeContent(html.encode())

            async def text(self):
                return html

            async def read(self):
                return html.encode()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse()

        crawler = ClauseaCrawler(respect_robots_txt=False, use_browser=False)

        await crawler._fetch_page_internal(cast(aiohttp.ClientSession, FakeSession()), original_url)

        normalized_redirect = crawler.normalize_url(redirected_url)
        assert normalized_redirect in crawler.visited_urls, (
            "Redirect target should be added to visited_urls to prevent duplicate crawling"
        )
