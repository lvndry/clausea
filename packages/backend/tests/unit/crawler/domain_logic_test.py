"""Unit tests for ClauseaCrawler domain and subdomain logic."""

from src.crawler import ClauseaCrawler


class TestCrawlerDomainLogic:
    """Test cases for crawler domain and subdomain filtering."""

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

        # This confirms the fix for the sibling subdomain issue
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
