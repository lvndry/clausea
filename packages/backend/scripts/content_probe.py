"""Fetch each URL as a single page (no link-following) and report extracted content size.

Used to verify recall-neutrality of browser-fetch changes: run on baseline, run again on a
branch, diff the content lengths per URL. A change is recall-safe only if policy pages keep
(roughly) the same extracted text. Read-only; no DB, no LLM.

Usage:
    uv run python scripts/content_probe.py <url> [<url> ...]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from urllib.parse import urlparse

from src.core.logging import setup_logging
from src.crawler import ClauseaCrawler


async def fetch_one(url: str) -> dict:
    domain = urlparse(url).netloc
    crawler = ClauseaCrawler(
        max_depth=0,  # seed only, no link-following
        max_pages=1,
        allowed_domains=[domain],
        respect_robots_txt=True,
        follow_external_links=False,
        min_legal_score=0,
        strategy="best_first",
        use_browser=True,
        browser_concurrency=1,
    )
    start = time.perf_counter()
    try:
        results = await crawler.crawl(url)
    except Exception as exc:  # noqa: BLE001 - probe must report, not crash
        return {"url": url, "ok": False, "error": repr(exc)}
    elapsed = time.perf_counter() - start
    if not results:
        return {"url": url, "ok": False, "elapsed_s": round(elapsed, 1), "text_len": 0}
    r = results[0]
    return {
        "url": url,
        "ok": r.success,
        "elapsed_s": round(elapsed, 1),
        "status": r.status_code,
        "title": (r.title or "")[:80],
        "text_len": len(r.content or ""),
        "markdown_len": len(r.markdown or ""),
    }


async def main() -> None:
    setup_logging()
    for url in sys.argv[1:]:
        result = await fetch_one(url)
        print("CONTENT_PROBE " + json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
