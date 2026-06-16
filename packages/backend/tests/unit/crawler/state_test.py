"""Unit tests for ClauseaCrawler depth and state management."""

from src.crawler import CRAWL_EXHAUSTION_GRACE, ClauseaCrawler


class TestRelevanceExhaustion:
    """The best_first relevance-exhaustion stop: stop once every own-score policy lead is
    crawled and a grace window of boost-only crawls surfaced nothing new."""

    def test_boost_only_link_is_not_a_real_lead(self) -> None:
        crawler = ClauseaCrawler(strategy="best_first", min_legal_score=2.5)
        # Boosted score clears the gate, but the URL's own score does not.
        crawler._enqueue_best_first("https://x.com/random", 1, 3.0, 0.0)
        assert crawler._frontier_real_leads == 0

    def test_own_score_link_is_a_real_lead_and_pop_decrements(self) -> None:
        crawler = ClauseaCrawler(strategy="best_first", min_legal_score=2.5)
        crawler._enqueue_best_first("https://x.com/privacy", 1, 8.0, 8.0)
        assert crawler._frontier_real_leads == 1
        crawler.get_next_url()  # popping the lead decrements the counter
        assert crawler._frontier_real_leads == 0

    def test_new_real_lead_resets_grace_window(self) -> None:
        crawler = ClauseaCrawler(strategy="best_first", min_legal_score=2.5)
        crawler._crawls_since_new_lead = 5
        crawler._enqueue_best_first("https://x.com/legal", 1, 4.0, 4.0)
        assert crawler._crawls_since_new_lead == 0

    def test_does_not_stop_while_a_real_lead_is_queued(self) -> None:
        # The /privacy -> /random -> /legal case: /legal is a real lead, so we never give up
        # while it is queued, regardless of intervening boost-only pages.
        crawler = ClauseaCrawler(strategy="best_first", min_legal_score=2.5)
        crawler._policy_pages_found = 1
        crawler._enqueue_best_first("https://x.com/legal", 1, 4.0, 4.0)
        crawler._crawls_since_new_lead = CRAWL_EXHAUSTION_GRACE + 5
        assert crawler._relevance_exhausted() is False

    def test_stops_only_after_grace_once_leads_exhausted(self) -> None:
        crawler = ClauseaCrawler(strategy="best_first", min_legal_score=2.5)
        crawler._policy_pages_found = 1
        crawler._frontier_real_leads = 0
        crawler._crawls_since_new_lead = CRAWL_EXHAUSTION_GRACE - 1
        assert crawler._relevance_exhausted() is False  # grace not yet elapsed
        crawler._crawls_since_new_lead = CRAWL_EXHAUSTION_GRACE
        assert crawler._relevance_exhausted() is True

    def test_never_stops_before_any_policy_found(self) -> None:
        crawler = ClauseaCrawler(strategy="best_first", min_legal_score=2.5)
        crawler._frontier_real_leads = 0
        crawler._crawls_since_new_lead = CRAWL_EXHAUSTION_GRACE * 2
        assert crawler._relevance_exhausted() is False  # no policy page found yet

    def test_does_not_apply_to_bfs(self) -> None:
        crawler = ClauseaCrawler(strategy="bfs", min_legal_score=2.5)
        crawler._policy_pages_found = 5
        crawler._frontier_real_leads = 0
        crawler._crawls_since_new_lead = CRAWL_EXHAUSTION_GRACE * 2
        assert crawler._relevance_exhausted() is False


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
        crawler = ClauseaCrawler(strategy="bfs")
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

    def test_get_pending_url_count_dfs(self) -> None:
        """Test _get_pending_url_count returns DFS stack length."""
        crawler = ClauseaCrawler(strategy="dfs")
        crawler.url_stack.append(("https://example.com/a", 1))
        assert crawler._get_pending_url_count() == 1

    def test_get_pending_url_count_best_first(self) -> None:
        """Test _get_pending_url_count returns priority queue length."""
        import heapq

        crawler = ClauseaCrawler(strategy="best_first")
        heapq.heappush(crawler.url_priority_queue, (-5.0, "https://example.com/a", 1, 5.0))
        assert crawler._get_pending_url_count() == 1


class TestResumeSkipSet:
    """A retried crawl skips re-fetching docs stored within the resume freshness
    window (recently_stored_urls), while leaving every other crawl decision intact."""

    def test_recently_stored_url_is_rejected(self) -> None:
        crawler = ClauseaCrawler(recently_stored_urls=["https://anthropic.com/privacy"])
        assert (
            crawler.should_crawl_url("https://anthropic.com/privacy", "https://anthropic.com", 1)
            is False
        )

    def test_skip_matches_after_normalization(self) -> None:
        # Stored without trailing slash; crawled with one — normalize_url collapses both,
        # so the membership test still matches. A mismatch here would silently disable
        # the skip, so this guards normalization parity between stored and crawled URLs.
        crawler = ClauseaCrawler(recently_stored_urls=["https://anthropic.com/legal"])
        assert (
            crawler.should_crawl_url("https://anthropic.com/legal/", "https://anthropic.com", 1)
            is False
        )

    def test_skip_matches_when_crawled_url_carries_tracking_params(self) -> None:
        # normalize_url strips trackers on both sides, so a tracked crawl URL still
        # resolves to the stored canonical URL and is skipped.
        crawler = ClauseaCrawler(recently_stored_urls=["https://anthropic.com/privacy"])
        assert (
            crawler.should_crawl_url(
                "https://anthropic.com/privacy?utm_source=email",
                "https://anthropic.com",
                1,
            )
            is False
        )

    def test_non_stored_url_is_not_skipped(self) -> None:
        crawler = ClauseaCrawler(recently_stored_urls=["https://anthropic.com/privacy"])
        assert (
            crawler.should_crawl_url("https://anthropic.com/terms", "https://anthropic.com", 1)
            is True
        )

    def test_empty_set_causes_no_skips(self) -> None:
        crawler = ClauseaCrawler(recently_stored_urls=[])
        assert (
            crawler.should_crawl_url("https://anthropic.com/privacy", "https://anthropic.com", 1)
            is True
        )

    def test_none_causes_no_skips(self) -> None:
        crawler = ClauseaCrawler(recently_stored_urls=None)
        assert (
            crawler.should_crawl_url("https://anthropic.com/privacy", "https://anthropic.com", 1)
            is True
        )

    def test_skip_set_survives_per_seed_reset(self) -> None:
        # crawl_multiple clears per-seed state (visited/queued/etc.) between base URLs,
        # but the resume skip-set must span every seed in the batch — otherwise the 2nd
        # seed would re-fetch docs already stored. Assert it still skips after a reset.
        crawler = ClauseaCrawler(recently_stored_urls=["https://anthropic.com/privacy"])

        # Simulate the per-seed reset block in crawl_multiple.
        crawler.visited_urls.clear()
        crawler.failed_urls.clear()
        crawler.queued_urls.clear()
        crawler._locale_seen_keys.clear()
        crawler._sitemap_seeded = False
        crawler.url_queue.clear()

        assert crawler._recently_stored_urls == {"https://anthropic.com/privacy"}
        assert (
            crawler.should_crawl_url("https://anthropic.com/privacy", "https://anthropic.com", 1)
            is False
        )
