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

    # Batch lands total_urls at 8 — below the interval, no report yet.
    crawler.stats.total_urls = 8
    crawler.stats.crawled_urls = 2
    crawler._report_crawl_progress()
    assert calls == []

    # Jumps to 16 (skipping the exact "10"): old logic emitted nothing here.
    crawler.stats.total_urls = 16
    crawler.stats.crawled_urls = 5
    crawler._report_crawl_progress()
    assert len(calls) == 1

    # Only 6 new processed since last report — still below the interval.
    crawler.stats.total_urls = 22
    crawler.stats.crawled_urls = 6
    crawler._report_crawl_progress()
    assert len(calls) == 1

    # Jumps to 37 (skipping 20 and 30): must emit, not freeze.
    crawler.stats.total_urls = 37
    crawler.stats.crawled_urls = 9
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
