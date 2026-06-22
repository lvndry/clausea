"""crawl_multiple shares one page budget across all seed URLs.

A product with many seed URLs (e.g. 10 distinct policy pages) would otherwise run N full
max_pages crawls back to back — enough work to blow the pipeline stall timeout and loop
reset→recrawl forever. The budget is divided across seeds, with a floor so each seed keeps
enough breadth for the convergence/exhaustion stoppers to fire naturally.
"""

from unittest.mock import AsyncMock

import pytest

from src.crawler import MIN_PAGES_PER_SEED, ClauseaCrawler


async def _record_budgets(crawler: ClauseaCrawler, seeds: list[str]) -> list[int]:
    seen: list[int] = []

    async def fake_crawl(_url: str, *, cleanup: bool = True):
        seen.append(crawler.max_pages)
        return []

    crawler.crawl = AsyncMock(side_effect=fake_crawl)  # type: ignore[method-assign]
    await crawler.crawl_multiple(seeds)
    return seen


@pytest.mark.asyncio
async def test_single_seed_keeps_full_budget():
    crawler = ClauseaCrawler(max_pages=400)
    budgets = await _record_budgets(crawler, ["https://example.com"])
    assert budgets == [400]


@pytest.mark.asyncio
async def test_many_seeds_divide_the_budget():
    crawler = ClauseaCrawler(max_pages=400)
    seeds = [f"https://example.com/p{i}" for i in range(8)]
    budgets = await _record_budgets(crawler, seeds)
    # 400 // 8 = 50, floored to MIN_PAGES_PER_SEED so convergence (budget 50) can still fire.
    assert budgets == [MIN_PAGES_PER_SEED] * 8
    assert all(b < 400 for b in budgets)


@pytest.mark.asyncio
async def test_few_seeds_split_without_hitting_the_floor():
    crawler = ClauseaCrawler(max_pages=400)
    seeds = [f"https://example.com/p{i}" for i in range(4)]
    budgets = await _record_budgets(crawler, seeds)
    assert budgets == [100, 100, 100, 100]


@pytest.mark.asyncio
async def test_budget_restored_after_crawl_multiple():
    crawler = ClauseaCrawler(max_pages=400)
    await _record_budgets(crawler, [f"https://example.com/p{i}" for i in range(10)])
    # Later products reuse the crawler config; the divided budget must not leak.
    assert crawler.max_pages == 400
