"""End-to-end test of the best_first relevance-exhaustion stop over a controlled link graph.

Mocks only the fetch layer (network + content scoring); the real crawl loop, URL scoring,
parent-boost, real-lead counting, grace window, and stop condition all run for real. Proves
the two properties that matter under a quality-first crawl:

1. Every policy page is found — including one reachable ONLY through a non-policy (boost-only)
   page (the "/privacy then /random then /legal" case).
2. The crawl still terminates early instead of grinding through a long tail of boost-only junk.
"""

import pytest

from src.crawler import CRAWL_EXHAUSTION_GRACE, ClauseaCrawler, CrawlResult

DOMAIN = "t.test"
SEED = f"https://{DOMAIN}/"

# Graph: the seed is a policy hub (title has policy keywords) so its links get a parent boost.
# /privacy, /terms, /cookies have high OWN scores (real leads). /cookies is reachable ONLY via
# the boost-only /deephub. A long tail of /junkNN pages are boost-only noise.
_JUNK = [f"https://{DOMAIN}/junk{n:02d}" for n in range(30)]


def _links(*urls: str) -> list[dict[str, str]]:
    return [{"url": u, "text": ""} for u in urls]


# url -> (legal_score, title, discovered_links)
_GRAPH: dict[str, tuple[float, str, list[dict[str, str]]]] = {
    SEED: (
        0.0,
        "Privacy and Terms",
        _links(
            f"https://{DOMAIN}/privacy",
            f"https://{DOMAIN}/terms",
            f"https://{DOMAIN}/deephub",
            *_JUNK,
        ),
    ),
    f"https://{DOMAIN}/privacy": (0.9, "Privacy Policy", []),
    f"https://{DOMAIN}/terms": (0.9, "Terms of Service", []),
    # Non-hub junk page whose ONLY link is a high-own-score policy reachable nowhere else.
    f"https://{DOMAIN}/deephub": (0.0, "Help", _links(f"https://{DOMAIN}/cookies")),
    f"https://{DOMAIN}/cookies": (0.9, "Cookie Policy", []),
}
for _j in _JUNK:
    _GRAPH[_j] = (0.0, "Stuff", [])


@pytest.mark.asyncio
async def test_relevance_exhaustion_finds_all_policies_and_stops_early(monkeypatch):
    crawler = ClauseaCrawler(
        strategy="best_first",
        min_legal_score=2.5,
        max_depth=5,
        max_pages=200,  # high, so the relevance-exhaustion stop is what terminates, not the cap
        max_concurrent=1,  # one page per batch so the grace window is checked exactly per page
        respect_robots_txt=False,
        use_browser=False,
        allowed_domains=[DOMAIN],
    )

    async def fake_fetch(_session, url: str) -> CrawlResult:
        score, title, links = _GRAPH.get(url, (0.0, "", []))
        return CrawlResult(
            url=url,
            title=title,
            content="x" * 600,
            markdown="x",
            metadata={"title": title},
            status_code=200,
            success=True,
            legal_score=score,
            discovered_links=links,
        )

    async def no_sitemaps(_session, _base):
        return []

    monkeypatch.setattr(crawler, "fetch_page", fake_fetch)
    monkeypatch.setattr(crawler, "_discover_sitemap_urls", no_sitemaps)

    await crawler.crawl(SEED, cleanup=False)
    visited = crawler.visited_urls

    # 1. Quality: every policy page was crawled — including /cookies, reachable only via the
    #    boost-only /deephub. Nothing dropped.
    assert f"https://{DOMAIN}/privacy" in visited
    assert f"https://{DOMAIN}/terms" in visited
    assert f"https://{DOMAIN}/cookies" in visited

    # 2. Termination: the crawl stopped without grinding the whole junk tail. It crawls at most
    #    the grace window's worth of junk after the last real lead, far fewer than all 30.
    junk_visited = sum(1 for j in _JUNK if j in visited)
    assert junk_visited <= CRAWL_EXHAUSTION_GRACE, f"crawled too much junk: {junk_visited}"
    assert len(visited) < len(_JUNK), "should not have crawled the entire junk tail"
