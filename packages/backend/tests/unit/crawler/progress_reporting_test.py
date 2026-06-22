"""Tests for crawl progress reporting cadence.

Regression: URLs are processed in concurrent batches, so ``stats.total_urls``
jumps by the batch size each iteration. The old gate (``total_urls % 10 == 0``)
required an exact landing on a multiple of 10, which batching routinely skips —
so the frontend progress bar would freeze mid-crawl. The reporter must instead
emit whenever enough new URLs have been processed since the last report.
"""

from src.crawler import ClauseaCrawler


def test_progress_emits_across_batch_jumps_that_skip_multiples_of_ten():
    """Cadence is driven by processed URLs (total_urls) so the report fires even
    when batched increments skip an exact multiple of the interval."""
    calls: list[tuple[int, int]] = []
    crawler = ClauseaCrawler(
        progress_callback=lambda current, total: calls.append((current, total))
    )

    # Batch lands total_urls at 2 — below the interval of 3, no report yet.
    crawler.stats.total_urls = 2
    crawler.stats.crawled_urls = 1
    crawler._report_crawl_progress()
    assert calls == []

    # Jumps to 6 (skipping the exact "3"): must still emit.
    crawler.stats.total_urls = 6
    crawler.stats.crawled_urls = 3
    crawler._report_crawl_progress()
    assert len(calls) == 1

    # Only 1 new processed since last report — still below the interval.
    crawler.stats.total_urls = 7
    crawler.stats.crawled_urls = 4
    crawler._report_crawl_progress()
    assert len(calls) == 1

    # Jumps to 13 (skipping 9 and 12): must emit, not freeze.
    crawler.stats.total_urls = 13
    crawler.stats.crawled_urls = 6
    crawler._report_crawl_progress()
    assert len(calls) == 2


def test_progress_reports_successful_pages_not_probed_count():
    """The reported count is successfully-fetched pages, NOT total URLs processed.

    total_urls is inflated by speculative policy-URL probes that mostly 404
    (e.g. 121 processed but only 20 fetched), so reporting it would massively
    overstate real progress.
    """
    calls: list[tuple[int, int]] = []
    crawler = ClauseaCrawler(
        progress_callback=lambda current, total: calls.append((current, total))
    )

    # 121 processed, only 20 fetched — the capcut scenario.
    crawler.stats.total_urls = 121
    crawler.stats.crawled_urls = 20
    crawler._report_crawl_progress(force=True)

    assert len(calls) == 1
    assert calls[-1][0] == 20  # successful pages, not 121


def test_progress_force_always_emits_even_below_interval():
    calls: list[tuple[int, int]] = []
    crawler = ClauseaCrawler(
        progress_callback=lambda current, total: calls.append((current, total))
    )

    crawler.stats.total_urls = 3
    crawler.stats.crawled_urls = 1
    crawler._report_crawl_progress(force=True)
    assert len(calls) == 1
    assert calls[-1][0] == 1


def test_progress_reporter_is_noop_without_callback():
    crawler = ClauseaCrawler()  # no progress_callback
    crawler.stats.total_urls = 100
    # Must not raise.
    crawler._report_crawl_progress()
    crawler._report_crawl_progress(force=True)
