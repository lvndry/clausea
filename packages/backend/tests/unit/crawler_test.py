"""Unit tests for the ClauseaCrawler."""

from src.crawler import ClauseaCrawler


class TestClauseaCrawler:
    """Test cases for ClauseaCrawler."""

    def test_should_crawl_url_same_domain(self) -> None:
        """Test that same domain URLs are allowed."""
        crawler = ClauseaCrawler(allowed_domains=None, follow_external_links=False)
        base_url = "https://anthropic.com"
        target_url = "https://anthropic.com/about"

        assert crawler.should_crawl_url(target_url, base_url, 1) is True

    def test_should_crawl_url_subdomain_from_root(self) -> None:
        """Test that subdomains are allowed from root domain."""
        crawler = ClauseaCrawler(allowed_domains=None, follow_external_links=False)
        base_url = "https://anthropic.com"
        target_url = "https://support.anthropic.com"

        assert crawler.should_crawl_url(target_url, base_url, 1) is True

    def test_should_crawl_url_sibling_subdomain_with_allowed_domains(self) -> None:
        """
        Test that sibling subdomains are allowed when in allowed_domains list,
        even if technically external to the current base URL.
        """
        crawler = ClauseaCrawler(allowed_domains=["anthropic.com"], follow_external_links=False)
        base_url = "https://privacy.anthropic.com"
        target_url = "https://support.anthropic.com"

        # This was previously False and is now fixed to be True
        assert crawler.should_crawl_url(target_url, base_url, 1) is True

    def test_should_reject_external_domain_without_allowed_domains(self) -> None:
        """Test that external domains are rejected by default."""
        crawler = ClauseaCrawler(allowed_domains=None, follow_external_links=False)
        base_url = "https://anthropic.com"
        target_url = "https://google.com"

        assert crawler.should_crawl_url(target_url, base_url, 1) is False

    def test_should_reject_external_domain_even_with_other_allowed_domains(self) -> None:
        """Test that external domains outside of allowed_domains are rejected."""
        crawler = ClauseaCrawler(allowed_domains=["anthropic.com"], follow_external_links=False)
        base_url = "https://anthropic.com"
        target_url = "https://google.com"

        assert crawler.should_crawl_url(target_url, base_url, 1) is False

    def test_should_allow_external_if_follow_external_links_true(self) -> None:
        """Test that any URL is allowed if follow_external_links is True."""
        crawler = ClauseaCrawler(allowed_domains=None, follow_external_links=True)
        base_url = "https://anthropic.com"
        target_url = "https://google.com"

        assert crawler.should_crawl_url(target_url, base_url, 1) is True

    def test_should_reject_when_max_depth_exceeded(self) -> None:
        """Test that URLs are rejected when depth exceeds max_depth."""
        crawler = ClauseaCrawler(max_depth=2)
        base_url = "https://anthropic.com"
        target_url = "https://anthropic.com/about"

        assert crawler.should_crawl_url(target_url, base_url, 3) is False

    def test_should_reject_compressed_files(self) -> None:
        """Test that compressed files (.gz, .zip, etc.) are rejected."""
        crawler = ClauseaCrawler()
        base_url = "https://booking.com"

        # Test various compressed file formats
        compressed_urls = [
            "https://booking.com/sitemap.xml.gz",
            "https://booking.com/data.zip",
            "https://booking.com/archive.tar",
            "https://booking.com/file.bz2",
            "https://booking.com/package.7z",
        ]

        for url in compressed_urls:
            assert crawler.should_crawl_url(url, base_url, 1) is False

    def test_should_allow_xml_sitemap_files(self) -> None:
        """Test that plain XML sitemap files are allowed (not compressed ones)."""
        crawler = ClauseaCrawler()
        base_url = "https://booking.com"

        # Plain XML sitemaps should be allowed (we can parse them for URLs)
        allowed_sitemap_urls = [
            "https://booking.com/sitemap.xml",
            "https://booking.com/sitemap-index.xml",
        ]

        for url in allowed_sitemap_urls:
            assert crawler.should_crawl_url(url, base_url, 1) is True

        # Compressed sitemaps should be rejected (we can't easily parse .gz files)
        rejected_sitemap_urls = [
            "https://booking.com/sitemap.xml.gz",
            "https://booking.com/sitembk-airport-el.0000.xml.gz",
        ]

        for url in rejected_sitemap_urls:
            assert crawler.should_crawl_url(url, base_url, 1) is False

    def test_should_reject_binary_media_files(self) -> None:
        """Test that binary media files are rejected."""
        crawler = ClauseaCrawler()
        base_url = "https://example.com"

        # Test various media formats
        media_urls = [
            "https://example.com/video.mp4",
            "https://example.com/audio.mp3",
            "https://example.com/video.avi",
            "https://example.com/document.docx",
        ]

        for url in media_urls:
            assert crawler.should_crawl_url(url, base_url, 1) is False

    def test_should_allow_feed_urls(self) -> None:
        """Test that RSS/Atom feed URLs are allowed (they may link to legal docs)."""
        crawler = ClauseaCrawler()
        base_url = "https://example.com"

        # Feed URLs should be allowed - they can contain links to policy documents
        feed_urls = [
            "https://example.com/rss",
            "https://example.com/feed",
            "https://example.com/atom",
            "https://example.com/feed.xml",
        ]

        for url in feed_urls:
            assert crawler.should_crawl_url(url, base_url, 1) is True

    def test_should_allow_policy_document_urls(self) -> None:
        """Test that policy document URLs are NOT filtered out."""
        crawler = ClauseaCrawler()
        base_url = "https://example.com"

        # Test policy document URLs that should be allowed
        legal_urls = [
            "https://example.com/privacy-policy",
            "https://example.com/terms-of-service",
            "https://example.com/legal/privacy.html",
            "https://example.com/cookie-policy",
        ]

        for url in legal_urls:
            assert crawler.should_crawl_url(url, base_url, 1) is True
