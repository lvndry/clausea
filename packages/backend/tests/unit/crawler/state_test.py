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

    def test_should_reject_already_queued_urls(self) -> None:
        """Test that URLs already in the queue are rejected to prevent duplicates."""
        crawler = ClauseaCrawler()
        url = "https://anthropic.com/queued"
        crawler.queued_urls.add(url)

        assert crawler.should_crawl_url(url, "https://anthropic.com", 1) is False

    def test_add_urls_to_queue_does_not_enqueue_duplicates(self) -> None:
        """Test that the same URL is not added to the BFS queue twice."""
        # min_legal_score=0 keeps this focused on dedup, not the relevance gate.
        crawler = ClauseaCrawler(strategy="bfs", min_legal_score=0)
        base_url = "https://example.com"

        links = [
            {"url": "https://example.com/page", "text": "Page"},
        ]

        # Add the URL once
        crawler.add_urls_to_queue(links, base_url, depth=1)
        assert len(crawler.url_queue) == 1
        assert "https://example.com/page" in crawler.queued_urls

        # Try to add the same URL again — should be deduplicated
        crawler.add_urls_to_queue(links, base_url, depth=1)
        assert len(crawler.url_queue) == 1

    def test_bfs_queue_rejects_urls_below_min_legal_score(self) -> None:
        """BFS must drop off-topic links, not just best_first.

        Regression: the relevance gate previously only applied to best_first, so the
        BFS fallback pass followed every same-domain link and wandered large sites.
        """
        crawler = ClauseaCrawler(strategy="bfs", min_legal_score=2.0)
        base_url = "https://example.com"

        links = [
            {"url": "https://example.com/privacy", "text": "Privacy Policy"},
            {"url": "https://example.com/blog/how-to-cook-pasta", "text": "Pasta"},
        ]
        crawler.add_urls_to_queue(links, base_url, depth=0)

        queued = {u for u, _ in crawler.url_queue}
        assert "https://example.com/privacy" in queued
        assert "https://example.com/blog/how-to-cook-pasta" not in queued

    def test_state_cleared_between_crawl_multiple_runs(self) -> None:
        """Test that queued_urls and _sitemap_seeded are cleared between runs."""
        crawler = ClauseaCrawler()
        crawler.queued_urls.add("https://example.com/old")
        crawler.visited_urls.add("https://example.com/visited")
        crawler._sitemap_seeded = True

        # Simulate the reset that happens in crawl_multiple
        crawler.visited_urls.clear()
        crawler.failed_urls.clear()
        crawler.queued_urls.clear()
        crawler._sitemap_seeded = False
        crawler.url_queue.clear()

        assert len(crawler.queued_urls) == 0
        assert crawler._sitemap_seeded is False
        assert crawler.should_crawl_url("https://example.com/old", "https://example.com", 1) is True

    def test_get_pending_url_count_bfs(self) -> None:
        """Test _get_pending_url_count returns BFS queue length."""
        crawler = ClauseaCrawler(strategy="bfs")
        assert crawler._get_pending_url_count() == 0

        crawler.url_queue.append(("https://example.com/a", 1))
        crawler.url_queue.append(("https://example.com/b", 1))
        assert crawler._get_pending_url_count() == 2

    def test_get_pending_url_count_best_first(self) -> None:
        """Test _get_pending_url_count returns priority queue length."""
        import heapq

        crawler = ClauseaCrawler(strategy="best_first")
        heapq.heappush(crawler.url_priority_queue, (-5.0, "https://example.com/a", 1))
        assert crawler._get_pending_url_count() == 1
