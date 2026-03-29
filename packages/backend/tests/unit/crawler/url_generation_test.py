"""Tests for generate_potential_policy_urls path-prefix awareness and hub patterns."""

from src.crawler import ClauseaCrawler


class TestGeneratePotentialLegalUrls:
    """Test cases for the URL generation logic."""

    def test_root_url_generates_standard_legal_paths(self) -> None:
        """A plain domain seed should produce root-level legal paths."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://example.com")

        assert "https://example.com/privacy" in urls
        assert "https://example.com/legal" in urls
        assert "https://example.com/terms" in urls
        assert "https://example.com/cookie-policy" in urls

    def test_root_url_generates_hub_paths(self) -> None:
        """A plain domain seed should produce hub / listing page URLs."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://example.com")

        assert "https://example.com/articles" in urls
        assert "https://example.com/collections" in urls
        assert "https://example.com/categories" in urls
        assert "https://example.com/help" in urls

    def test_locale_prefix_generates_prefixed_paths(self) -> None:
        """A locale-prefixed seed like /en should produce both root and prefixed URLs."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://privacy.claude.com/en")

        # Root-level URLs should still be present
        assert "https://privacy.claude.com/privacy" in urls
        assert "https://privacy.claude.com/legal" in urls

        # Prefixed legal paths
        assert "https://privacy.claude.com/en/privacy" in urls
        assert "https://privacy.claude.com/en/legal" in urls
        assert "https://privacy.claude.com/en/terms" in urls
        assert "https://privacy.claude.com/en/cookie-policy" in urls

        # Prefixed hub paths — the key missing discovery
        assert "https://privacy.claude.com/en/articles" in urls
        assert "https://privacy.claude.com/en/collections" in urls
        assert "https://privacy.claude.com/en/categories" in urls

    def test_multi_segment_prefix_generates_sub_prefixes(self) -> None:
        """A multi-segment path like /hc/en-us should produce URLs under each sub-prefix."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://help.example.com/hc/en-us")

        # Root-level
        assert "https://help.example.com/privacy" in urls
        assert "https://help.example.com/articles" in urls

        # Sub-prefix /hc
        assert "https://help.example.com/hc/privacy" in urls
        assert "https://help.example.com/hc/articles" in urls
        assert "https://help.example.com/hc/categories" in urls

        # Full prefix /hc/en-us
        assert "https://help.example.com/hc/en-us/privacy" in urls
        assert "https://help.example.com/hc/en-us/articles" in urls
        assert "https://help.example.com/hc/en-us/categories" in urls

    def test_trailing_slash_is_normalized(self) -> None:
        """Trailing slashes on the base URL should not produce double-slash paths."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://example.com/en/")

        assert "https://example.com/en/privacy" in urls
        # No double-slash
        assert not any("//privacy" in u for u in urls)

    def test_no_duplicate_urls(self) -> None:
        """The returned list should contain no duplicates."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://privacy.claude.com/en")

        assert len(urls) == len(set(urls))

    def test_plain_domain_no_spurious_prefix(self) -> None:
        """A bare domain (no path) should only generate root-level URLs."""
        crawler = ClauseaCrawler()
        urls = crawler.generate_potential_policy_urls("https://example.com")
        url_set = set(urls)

        # Every URL should start with the domain and a single slash (no double prefix)
        for u in url_set:
            path = u.replace("https://example.com", "")
            assert path.startswith("/"), f"Unexpected path format: {path}"
            assert not path.startswith("//"), f"Double slash in path: {path}"
