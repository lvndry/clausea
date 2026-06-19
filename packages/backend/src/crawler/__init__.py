"""Re-export shim so ``from src.crawler import …`` works as it did from the monolithic ``crawler.py``.

**What it contains**
Every public symbol once defined in ``src/crawler.py`` — the main
``ClauseaCrawler`` class, helper types, constants, and internal utilities
that test monkeypatches rely on.

**What it prevents**
Consumers importing directly from submodules (``src.crawler.client``,
``src.crawler.robots``, etc.).  All access goes through this single
``__init__`` so the internal module structure can be reorganised without
touching callers.
"""

from src.crawler.browser import (
    _block_heavy_assets,
    _get_global_browser_slot,
    _global_browser_semaphores,
    cleanup_browser,
    get_global_browser_slot,
    setup_browser,
)
from src.crawler.client import (
    ClauseaCrawler,
    crawl_for_policy_documents,
    main,
    needs_browser_fallback,
    test_specific_url,
)
from src.crawler.constants import (
    _BLOCKED_ASSETS_RE,
    _MIRROR_SUBDOMAIN_RE,
    _TLD_EXTRACT,
    ACCEPT_HEADER,
    BROWSER_LAUNCH_TIMEOUT_S,
    BROWSER_LOAD_STATE_TIMEOUT_MS,
    BROWSER_NAV_TIMEOUT_MS,
    CONVERGENCE_LEGAL_SCORE,
    CRAWL_BOT_WALL_ABORT,
    CRAWL_EXHAUSTION_GRACE,
    DEFAULT_NO_POLICY_PAGE_BUDGET,
    DEFAULT_USER_AGENT,
    MAX_CHILD_SITEMAPS,
    MAX_ENGLISH_LOCALE_VARIANTS_PER_DOC,
    MAX_HEADER_BYTES,
    MAX_LEGAL_SCORE_SCALE,
    MAX_RESPONSE_BYTES,
    MIN_CONTENT_LENGTH_FOR_SPA_CHECK,
    MIN_PAGES_PER_SEED,
    SPA_HYDRATION_RETRIES,
    english_locale_canonical_key,
    locale_canonical_key,
)
from src.crawler.content_analyzer import ContentAnalyzer
from src.crawler.http_cache import AsyncFileLogHandler, HTTPCache
from src.crawler.models import CrawlResult, CrawlStats, PageContent, StaticFetchResult
from src.crawler.rate_limiter import DomainRateLimiter
from src.crawler.robots import RobotsTxtChecker
from src.crawler.url_scorer import URLScorer

__all__ = [
    "ACCEPT_HEADER",
    "AsyncFileLogHandler",
    "BROWSER_LAUNCH_TIMEOUT_S",
    "BROWSER_LOAD_STATE_TIMEOUT_MS",
    "BROWSER_NAV_TIMEOUT_MS",
    "CONVERGENCE_LEGAL_SCORE",
    "CRAWL_BOT_WALL_ABORT",
    "CRAWL_EXHAUSTION_GRACE",
    "ClauseaCrawler",
    "ContentAnalyzer",
    "CrawlResult",
    "CrawlStats",
    "DEFAULT_NO_POLICY_PAGE_BUDGET",
    "DEFAULT_USER_AGENT",
    "DomainRateLimiter",
    "HTTPCache",
    "MAX_CHILD_SITEMAPS",
    "MAX_ENGLISH_LOCALE_VARIANTS_PER_DOC",
    "MAX_HEADER_BYTES",
    "MAX_LEGAL_SCORE_SCALE",
    "MAX_RESPONSE_BYTES",
    "MIN_CONTENT_LENGTH_FOR_SPA_CHECK",
    "MIN_PAGES_PER_SEED",
    "PageContent",
    "RobotsTxtChecker",
    "SPA_HYDRATION_RETRIES",
    "StaticFetchResult",
    "URLScorer",
    "_BLOCKED_ASSETS_RE",
    "_MIRROR_SUBDOMAIN_RE",
    "_TLD_EXTRACT",
    "_block_heavy_assets",
    "_get_global_browser_slot",
    "_global_browser_semaphores",
    "cleanup_browser",
    "crawl_for_policy_documents",
    "english_locale_canonical_key",
    "get_global_browser_slot",
    "locale_canonical_key",
    "main",
    "needs_browser_fallback",
    "setup_browser",
    "test_specific_url",
]
