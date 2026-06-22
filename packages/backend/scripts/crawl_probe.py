"""Measure real crawl behavior for one seed URL + strategy. Read-only; no DB, no LLM.

Answers the only question that matters before touching the crawler: left to its own
devices, does a crawl terminate quickly (converged / frontier exhausted) or does it keep
climbing until it hits the page cap (wander)? Runs the actual ClauseaCrawler with the same
knobs the pipeline uses, under a hard wall-clock timeout, and prints a JSON summary.

Usage:
    uv run python scripts/crawl_probe.py <seed_url> <strategy> <min_legal_score> <max_depth> <max_pages> <timeout_s> [browser_concurrency] [--write <result_json>] [--compare <baseline_json>]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.core.logging import setup_logging
from src.crawler import ClauseaCrawler, CrawlResult


def _parse_optional_args(argv: list[str]) -> tuple[int, str | None, str | None]:
    browser_concurrency = 4
    write_path: str | None = None
    compare_path: str | None = None
    idx = 0
    while idx < len(argv):
        token = argv[idx]
        if token == "--write" and idx + 1 < len(argv):
            write_path = argv[idx + 1]
            idx += 2
            continue
        if token == "--compare" and idx + 1 < len(argv):
            compare_path = argv[idx + 1]
            idx += 2
            continue
        # Backward compatible optional positional browser_concurrency.
        if idx == 0:
            browser_concurrency = int(token)
            idx += 1
            continue
        raise ValueError(f"Unknown argument: {token}")
    return browser_concurrency, write_path, compare_path


def _policy_page_details(results: list[CrawlResult]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for result in results:
        if not result.success:
            continue
        legal_score = float(result.legal_score or 0.0)
        if legal_score < 0.2:
            continue
        details.append(
            {
                "url": result.url,
                "legal_score": round(legal_score, 3),
                "content_length": len(result.content or ""),
                "title": result.title or "",
            }
        )
    details.sort(key=lambda item: (-float(item["legal_score"]), -int(item["content_length"])))
    return details


def _len_map(details: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in details or []:
        if isinstance(item, dict) and item.get("url"):
            out[str(item["url"])] = int(item.get("content_length", 0))
    return out


def _compare_probe_runs(current: dict[str, Any], baseline_path: str) -> dict[str, object]:
    baseline = json.loads(Path(baseline_path).read_text())
    current_map = _len_map(current.get("policy_page_details"))
    baseline_map = _len_map(baseline.get("policy_page_details"))

    current_urls = set(current_map)
    baseline_urls = set(baseline_map)
    missing_policy_urls = sorted(baseline_urls - current_urls)
    new_policy_urls = sorted(current_urls - baseline_urls)

    # Flag major content truncation for URLs present in both runs.
    # 0.7 keeps mild extraction variance out of the alert channel.
    regressions: list[dict[str, object]] = []
    for url in sorted(current_urls & baseline_urls):
        base_len = baseline_map[url]
        curr_len = current_map[url]
        if base_len >= 200 and curr_len < int(base_len * 0.7):
            regressions.append(
                {
                    "url": url,
                    "baseline_length": base_len,
                    "current_length": curr_len,
                    "ratio": round(curr_len / base_len, 3) if base_len else 1.0,
                }
            )

    gate_passed = not missing_policy_urls and not regressions
    return {
        "baseline_path": baseline_path,
        "baseline_policy_pages": len(baseline_urls),
        "current_policy_pages": len(current_urls),
        "missing_policy_urls": missing_policy_urls,
        "new_policy_urls": new_policy_urls,
        "content_length_regressions": regressions,
        "verification_gate_passed": gate_passed,
    }


async def main() -> None:
    if len(sys.argv) < 7:
        raise SystemExit(
            "Usage: uv run python scripts/crawl_probe.py "
            "<seed_url> <strategy> <min_legal_score> <max_depth> <max_pages> <timeout_s> "
            "[browser_concurrency] [--write <result_json>] [--compare <baseline_json>]"
        )
    seed, strategy = sys.argv[1], sys.argv[2]
    min_legal_score = float(sys.argv[3])
    max_depth, max_pages = int(sys.argv[4]), int(sys.argv[5])
    timeout_s = float(sys.argv[6])
    browser_concurrency, write_path, compare_path = _parse_optional_args(sys.argv[7:])

    setup_logging()
    domain = urlparse(seed).netloc
    crawler = ClauseaCrawler(
        max_depth=max_depth,
        max_pages=max_pages,
        max_concurrent=20,
        delay_between_requests=1.0,
        timeout=30,
        allowed_domains=[domain],
        respect_robots_txt=True,
        follow_external_links=False,
        min_legal_score=min_legal_score,
        strategy=strategy,
        use_browser=True,
        browser_concurrency=browser_concurrency,
    )

    start = time.perf_counter()
    timed_out = False
    try:
        results = await asyncio.wait_for(crawler.crawl(seed), timeout=timeout_s)
    except TimeoutError:
        timed_out = True
        results = []
    elapsed = time.perf_counter() - start

    crawled = crawler.stats.crawled_urls
    visited = len(crawler.visited_urls)
    # Path-prefix histogram of what actually got fetched — reveals wander into
    # non-policy areas (/blog, /help, /careers) vs staying on policy paths.
    prefixes = Counter(
        ("/" + (urlparse(u).path.lstrip("/").split("/", 1)[0] or "<root>"))
        for u in crawler.visited_urls
    )
    policy_pages = (
        sum(1 for r in results if (r.legal_score or 0) >= 0.2 and r.success) if results else None
    )
    # Did we actually reach policy pages? Surfaces opaque-URL discovery (Amazon-style)
    # and lets us eyeball whether non-standard labels (Conditions of Use) were followed.
    policy_tokens = ("privacy", "conditions", "legal", "cookie", "terms", "notice", "gdpr")
    policy_like = sorted(
        u for u in crawler.visited_urls if any(t in u.lower() for t in policy_tokens)
    )[:25]
    policy_page_details = _policy_page_details(results)

    hit_cap = visited >= max_pages
    summary = {
        "seed": seed,
        "strategy": strategy,
        "min_legal_score": min_legal_score,
        "max_depth": max_depth,
        "max_pages": max_pages,
        "browser_concurrency": browser_concurrency,
        "elapsed_s": round(elapsed, 1),
        "timed_out_at_s": timeout_s if timed_out else None,
        "visited": visited,
        "crawled_ok": crawled,
        "policy_pages_ge_0.2": policy_pages,
        "hit_page_cap": hit_cap,
        # The verdict: terminated early (good) vs hit cap / timed out (wander signal).
        "verdict": (
            "WANDER (hit cap)"
            if hit_cap
            else "WANDER (timed out, still going)"
            if timed_out
            else "CONVERGED/EXHAUSTED early"
        ),
        "top_path_prefixes": prefixes.most_common(12),
        "policy_like_urls": policy_like,
        "policy_page_details": policy_page_details,
    }
    if compare_path:
        summary["comparison"] = _compare_probe_runs(summary, compare_path)
    if write_path:
        Path(write_path).write_text(json.dumps(summary, indent=2) + "\n")
    print("PROBE_RESULT " + json.dumps(summary))
    comparison = summary.get("comparison")
    if compare_path and isinstance(comparison, dict):
        if not comparison.get("verification_gate_passed", False):
            raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
