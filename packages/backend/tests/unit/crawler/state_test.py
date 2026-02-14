"""Unit tests for ClauseaCrawler depth and state management."""

from src.crawler import ClauseaCrawler


class TestCrawlerState:
    """Test cases for crawler depth and internal state."""

    def test_should_reject_when_max_depth_exceeded(self) -> None:
        """Test that URLs are rejected when depth exceeds max_depth."""
        crawler = ClauseaCrawler(max_depth=2)
        base_url = "https://anthropic.com"
        target_url = "https://anthropic.com/about"

        assert crawler.should_crawl_url(target_url, base_url, 3) is False

    def test_should_reject_visited_urls(self) -> None:
        """Test that already visited URLs are rejected."""
        crawler = ClauseaCrawler()
        url = "https://anthropic.com/visited"
        crawler.visited_urls.add(url)

        assert crawler.should_crawl_url(url, "https://anthropic.com", 1) is False
