"""Policy-document crawler — the main ``ClauseaCrawler`` class and its entry points.

**What it does**
Orchestrates the full crawl lifecycle for a given seed URL or product:
1. Sitemap discovery — fetches and parses ``/sitemap.xml`` (and child sitemaps),
   aggregates candidate URLs from sitemap entries and on-page ``<a>`` links.
2. URL frontier — a priority queue ordered by ``URLScorer`` score; exhausted
   when budget is met or no high-value URLs remain.
3. Per-URL pipeline — robots.txt check, rate-limit acquire, static HTTP fetch,
   SPA re-fetch via headless browser if needed, content classification, locale
   deduplication, convergence check.
4. Returns a list of ``CrawlResult`` objects to the pipeline caller.

**What it contains**
- ``ClauseaCrawler``: the main class (~700 lines) with ``crawl``, ``_fetch_url``,
  ``_process_crawl_result``, and the sitemap-parsing / link-extraction machinery.
- ``crawl_for_policy_documents(product, max_pages, …)``: top-level convenience wrapper.
- ``test_specific_url(url)``: debug entry point that crawls one URL with full logging.
- ``main()``: CLI entry point invoked by ``python -m src.crawler``.

**What it allows/prevents**
Allows the pipeline to submit a company/product name and receive a set of
classified policy documents in return.  Prevents duplicate processing of the
same URL (via a ``seen`` set), prevents crawling beyond configurable page
and time budgets, and stops when crawl convergence criteria are met.
"""

from __future__ import annotations

import asyncio
import gzip
import heapq
import json
import logging
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, parse_qsl, urlencode, urljoin, urlparse, urlunparse

import aiohttp
import markdownify
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.logging import get_logger
from src.crawler.browser import (
    _block_heavy_assets,
    cleanup_browser,
    get_global_browser_slot,
    setup_browser,
)
from src.crawler.constants import (
    _CONSENT_CONTAINER_RE,
    _CONSENT_TEXT_MARKERS,
    _MAX_GENERIC_CHILD_SITEMAPS,
    _MIRROR_SUBDOMAIN_RE,
    _POLICY_SITEMAP_RE,
    _TLD_EXTRACT,
    _TRACKING_QUERY_PARAMS,
    ACCEPT_HEADER,
    BROWSER_DOMAIN_FAILURE_CAP,
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
    STEALTH_ACCEPT_HEADER,
    STEALTH_USER_AGENT,
    english_locale_canonical_key,
    locale_canonical_key,
)
from src.crawler.content_analyzer import ContentAnalyzer
from src.crawler.http_cache import AsyncFileLogHandler, HTTPCache
from src.crawler.models import CrawlResult, CrawlStats, PageContent, StaticFetchResult
from src.crawler.rate_limiter import DomainRateLimiter
from src.crawler.robots import RobotsTxtChecker
from src.crawler.url_scorer import URLScorer
from src.utils.perf import _log_browser_processes, _log_top_processes

logger = get_logger(__name__, component="crawler")

# ---- Browser-fallback heuristic ----------------------------------------------------

_SPA_CONTAINER_IDS: frozenset[str] = frozenset(
    {"root", "app", "__next", "__nuxt", "react-root", "ember-application"}
)

_RENDERABLE_CONTENT_TYPES: tuple[str, ...] = (
    "text/html",
    "text/markdown",
    "text/x-markdown",
    "text/plain",
)


def needs_browser_fallback(raw: StaticFetchResult) -> bool:
    """Return True when a plain-HTTP response is a JS shell warranting headless browser fallback.

    Triggers True when any of these hold:
    - HTTP 4xx (except 429, which is a rate-limit hard block the browser cannot bypass)
    - Missing or non-HTML/text/markdown Content-Type
    - HTML body containing a known SPA root element (div#root, div#app, div#__next, …)
      with fewer than MIN_CONTENT_LENGTH_FOR_SPA_CHECK characters of inner text
    - Fewer than MIN_CONTENT_LENGTH_FOR_SPA_CHECK visible characters overall

    Returns False unconditionally for HTTP 429.
    """
    if raw.status_code == 429:
        return False

    if 400 <= raw.status_code < 500:
        return True

    content_type = (raw.content_type or "").lower().split(";")[0].strip()
    if not any(content_type.startswith(ct) for ct in _RENDERABLE_CONTENT_TYPES):
        return True

    body = raw.body or ""

    # Non-HTML renderable types (plain text, markdown) can't be SPA shells; just check length.
    if not content_type.startswith("text/html"):
        return len(body.strip()) < MIN_CONTENT_LENGTH_FOR_SPA_CHECK

    # Parse HTML once for both SPA-skeleton detection and overall visible-text check.
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for spa_id in _SPA_CONTAINER_IDS:
        el = soup.find(id=spa_id)
        if el is not None and len(el.get_text(" ", strip=True)) < MIN_CONTENT_LENGTH_FOR_SPA_CHECK:
            return True

    return len(soup.get_text(" ", strip=True)) < MIN_CONTENT_LENGTH_FOR_SPA_CHECK


# ---- ClauseaCrawler ----------------------------------------------------------------


class ClauseaCrawler:
    """Powerful policy document crawler."""

    PROGRESS_REPORT_INTERVAL = 3

    def __init__(
        self,
        max_depth: int = 5,
        max_pages: int = 1000,
        no_policy_page_budget: int = DEFAULT_NO_POLICY_PAGE_BUDGET,
        max_concurrent: int = 10,
        delay_between_requests: float = 1.0,
        timeout: int = 60,
        allowed_domains: list[str] | None = None,
        respect_robots_txt: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        follow_external_links: bool = False,
        follow_nofollow: bool = False,
        respect_meta_robots: bool = True,
        min_legal_score: float = 2.0,
        strategy: str = "bfs",
        ignore_robots_for_domains: list[str] | None = None,
        max_retries: int = 3,
        log_file_path: str | None = None,
        use_browser: bool = False,
        browser_concurrency: int = 4,
        proxy: str | None = None,
        allowed_paths: list[str] | None = None,
        denied_paths: list[str] | None = None,
        delay_jitter: float = 0.0,
        enable_binary_crawling: bool = False,
        use_tika_for_binaries: bool = False,
        use_pdfminer_for_pdf: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
        result_callback: Callable[[CrawlResult], Awaitable[None]] | None = None,
        stop_callback: Callable[[], bool] | Callable[[], Awaitable[bool]] | None = None,
        recently_stored_urls: list[str] | set[str] | None = None,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.no_policy_page_budget = no_policy_page_budget
        self.max_concurrent = max_concurrent
        self.delay_between_requests = delay_between_requests
        self.delay_jitter = delay_jitter
        self.timeout = timeout
        self.allowed_domains: set[str] | None = set(allowed_domains) if allowed_domains else None
        self.respect_robots_txt = respect_robots_txt
        self.user_agent = user_agent
        self.follow_external_links = follow_external_links
        self.follow_nofollow = follow_nofollow
        self.respect_meta_robots = respect_meta_robots
        self.min_legal_score = min_legal_score
        self.strategy = strategy
        self.ignore_robots_for_domains = set(ignore_robots_for_domains or [])
        self.max_retries = max_retries
        self.log_file_path = log_file_path
        self.use_browser = use_browser
        self.browser_concurrency = max(1, browser_concurrency)
        self.proxy = proxy
        self.allowed_paths = allowed_paths
        self.denied_paths = denied_paths

        self.enable_binary_crawling = enable_binary_crawling
        self.use_tika_for_binaries = use_tika_for_binaries
        self.use_pdfminer_for_pdf = use_pdfminer_for_pdf

        self.progress_callback = progress_callback
        self.result_callback = result_callback
        self.stop_callback = stop_callback
        self._last_progress_report = 0

        self.compiled_allowed_paths = (
            [re.compile(path_pattern) for path_pattern in allowed_paths] if allowed_paths else []
        )
        self.compiled_denied_paths = (
            [re.compile(path_pattern) for path_pattern in denied_paths] if denied_paths else []
        )

        self.url_scorer = URLScorer()
        self.content_analyzer = ContentAnalyzer()
        self.robots_checker = RobotsTxtChecker(max_cache_size=1000) if respect_robots_txt else None
        self.http_cache = HTTPCache(max_cache_size=10000)

        self.file_handler: logging.FileHandler | None = None
        self._async_handler: AsyncFileLogHandler | None = None
        self._log_executor: ThreadPoolExecutor | None = None
        if self.log_file_path:
            self._setup_file_logging()

        self.visited_urls: set[str] = set()
        self.failed_urls: set[str] = set()
        self.queued_urls: set[str] = set()
        self._recently_stored_urls: set[str] = {
            self.normalize_url(url) for url in (recently_stored_urls or [])
        }
        self._locale_seen_keys: set[str] = set()
        self.max_english_locale_variants = max(1, MAX_ENGLISH_LOCALE_VARIANTS_PER_DOC)
        self._english_locale_seen: dict[str, set[str]] = {}
        self.url_queue: deque[tuple[str, int]] = deque()
        self.url_stack: list[tuple[str, int]] = []
        self.url_priority_queue: list[tuple[int, float, str, int, float]] = []
        self._frontier_real_leads: int = 0
        self._policy_pages_found: int = 0
        self._crawls_since_new_lead: int = 0
        self._consecutive_blocked: int = 0
        self._sitemap_seeded: bool = False
        self._url_scores: dict[str, float] = {}
        self._speculative_urls: set[str] = set()
        self.results: list[CrawlResult] = []
        self.stats = CrawlStats()

        self._render_retry_queue: list[str] = []
        self._in_render_retry: bool = False

        self._render_attempts: int = 0
        self._render_failures: int = 0
        self._render_slot_wait_total: float = 0.0
        self._render_recovered: int = 0
        self._consecutive_browser_failures: int = 0

        self.rate_limiter = DomainRateLimiter(
            delay_between_requests=delay_between_requests, jitter=self.delay_jitter
        )

        binary_exclusions = "jpg|jpeg|png|gif|css|js|ico"
        first_pattern = (
            rf"\.(?:{binary_exclusions})$"
            if self.enable_binary_crawling
            else r"\.(?:pdf|jpg|jpeg|png|gif|css|js|ico)$"
        )
        self.compiled_skip_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                first_pattern,
                r"#",
                r"mailto:",
                r"tel:",
                r"javascript:",
                r"/search\?",
                r"/api/",
                r"/ajax/",
                r"\.(gz|zip|tar|bz2|7z|rar|xz)(?:[?#]|$)",
                r"\.(mp4|mp3|avi|mov|wmv|flv|wav|ogg|webm)(?:[?#]|$)",
                r"\.(doc|docx|xls|xlsx|ppt|pptx)(?:[?#]|$)",
                r"\.(css|js|mjs|map)(?:[?#]|$)",
                r"\.(woff2?|ttf|otf|eot)(?:[?#]|$)",
                r"\.(png|jpe?g|gif|svg|webp|avif|ico|bmp)(?:[?#]|$)",
            ]
        ]

    def _setup_file_logging(self) -> None:
        if not self.log_file_path:
            return
        try:
            log_path = Path(self.log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            self.file_handler = logging.FileHandler(self.log_file_path, mode="a", encoding="utf-8")
            self.file_handler.setLevel(logging.DEBUG)

            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            self.file_handler.setFormatter(formatter)

            self._log_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="log-writer")
            self._async_handler = AsyncFileLogHandler(self.file_handler, self._log_executor)
            self._async_handler.setLevel(logging.DEBUG)
            self._async_handler.setFormatter(formatter)

            root_logger = logging.getLogger()
            root_logger.addHandler(self._async_handler)

            logger.info(f"File logging enabled (async): {self.log_file_path}")
        except Exception as e:
            logger.warning(f"Failed to set up file logging: {e}")

    async def _shutdown_log_executor(self) -> None:
        if self._async_handler:
            try:
                self._async_handler.set_shutdown(True)
            except Exception:
                pass
        if self._log_executor:
            await asyncio.to_thread(self._log_executor.shutdown, wait=True)

    async def _setup_browser(self):
        return await setup_browser(proxy=self.proxy)

    async def _cleanup_browser(self):
        await cleanup_browser()

    @staticmethod
    def _is_garbled_content(text: str, *, sample_size: int = 1024) -> bool:
        if not text or len(text) < 100:
            return False
        sample = text[:sample_size]
        non_text_chars = sum(
            1 for ch in sample if not ch.isprintable() and ch not in ("\n", "\r", "\t")
        )
        ratio = non_text_chars / len(sample)
        if ratio > 0.08:
            return True
        non_ascii = sum(1 for ch in sample if ord(ch) > 127)
        if non_ascii / len(sample) > 0.25:
            return True
        return False

    _JS_REQUIRED_MARKERS = [
        "javascript is required",
        "enable javascript",
        "you need to enable javascript",
        "please enable js",
    ]

    @staticmethod
    def _has_js_required_markers(text: str) -> bool:
        text_lower = text.lower()
        return any(m in text_lower for m in ClauseaCrawler._JS_REQUIRED_MARKERS)

    @staticmethod
    def _url_looks_like_not_found_landing(url: str) -> bool:
        path = (urlparse(url).path or "/").rstrip("/") or "/"
        if path == "/404":
            return True
        segments = [seg for seg in path.split("/") if seg]
        return bool(segments) and segments[-1].casefold() == "404"

    def _content_is_sufficient(self, page: PageContent, url: str) -> bool:
        text = page.text or ""
        if self._is_garbled_content(text):
            return False
        if self._has_js_required_markers(text):
            return False
        url_score = self.url_scorer.score_url(url)
        min_len = 1000 if url_score >= 5.0 else MIN_CONTENT_LENGTH_FOR_SPA_CHECK
        if len(text) < min_len:
            return False
        markdown = page.markdown or ""
        if len(markdown.strip()) < 400:
            return False
        return True

    async def _static_fetch(self, session: aiohttp.ClientSession, url: str) -> StaticFetchResult:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        should_check_robots = (
            self.respect_robots_txt and domain not in self.ignore_robots_for_domains
        )

        if should_check_robots and self.robots_checker:
            is_allowed, reason = await self.robots_checker.can_fetch(session, url)
            if not is_allowed:
                logger.warning(f"URL blocked by robots.txt: {url} - Reason: {reason}")
                return StaticFetchResult(
                    url=url,
                    status_code=403,
                    content_type="",
                    body="",
                    blocked_by_robots_txt=True,
                    error_message=f"Blocked by robots.txt: {reason}",
                )

        await self.rate_limit(url)

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        headers = {"User-Agent": self.user_agent, "Accept": ACCEPT_HEADER}
        cache_headers = self.http_cache.get_cache_headers(url)
        headers.update(cache_headers)

        request_args: dict[str, Any] = {"timeout": timeout, "headers": headers}
        if self.proxy:
            request_args["proxy"] = self.proxy

        async with session.get(url, **request_args) as response:
            final_url = str(response.url)
            if final_url != url:
                logger.debug(f"Redirect detected: {url} -> {final_url}")

            if response.status == 304:
                return StaticFetchResult(
                    url=url,
                    status_code=304,
                    content_type="",
                    body="",
                    cached=True,
                    resolved_url=final_url,
                )

            if response.status == 200:
                self.http_cache.update_cache(url, response)

            content_type = response.headers.get("content-type", "").lower()
            resp_headers = dict(response.headers.items())

            is_text = any(
                ct in content_type
                for ct in (
                    "text/html",
                    "text/markdown",
                    "text/x-markdown",
                    "text/plain",
                    "text/xml",
                    "application/xml",
                    "application/rss+xml",
                    "application/atom+xml",
                )
            )

            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > MAX_RESPONSE_BYTES:
                return StaticFetchResult(
                    url=url,
                    status_code=response.status,
                    content_type=content_type,
                    body="",
                    headers=resp_headers,
                    resolved_url=final_url,
                    error_message=f"Response too large ({declared_length} bytes)",
                )

            if is_text:
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raw = raw[:MAX_RESPONSE_BYTES]
                body = raw.decode(response.charset or "utf-8", errors="replace")
                return StaticFetchResult(
                    url=url,
                    status_code=response.status,
                    content_type=content_type,
                    body=body,
                    headers=resp_headers,
                    resolved_url=final_url,
                )
            else:
                raw_bytes = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw_bytes) > MAX_RESPONSE_BYTES:
                    raw_bytes = raw_bytes[:MAX_RESPONSE_BYTES]
                return StaticFetchResult(
                    url=url,
                    status_code=response.status,
                    content_type=content_type,
                    body="",
                    raw_bytes=raw_bytes,
                    headers=resp_headers,
                    resolved_url=final_url,
                )

    async def _static_fetch_stealth(
        self, session: aiohttp.ClientSession, url: str
    ) -> StaticFetchResult | None:
        """Retry a static fetch with a real browser UA when the bot UA got a JS-shell bot-wall.

        Only called when the primary fetch returned HTTP 200 with < 500 chars of visible text,
        indicating the server detected ClauseaBot and served a JS challenge instead of content.
        Returns None on any network error so the caller can fall through to the browser.
        """
        try:
            await self.rate_limit(url)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "User-Agent": STEALTH_USER_AGENT,
                "Accept": STEALTH_ACCEPT_HEADER,
                "Accept-Language": "en-US,en;q=0.9",
            }
            request_args: dict[str, Any] = {"timeout": timeout, "headers": headers}
            if self.proxy:
                request_args["proxy"] = self.proxy

            async with session.get(url, **request_args) as response:
                if response.status != 200:
                    return None
                content_type = response.headers.get("content-type", "").lower()
                if not any(
                    content_type.startswith(ct)
                    for ct in ("text/html", "text/markdown", "text/plain")
                ):
                    return None

                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raw = raw[:MAX_RESPONSE_BYTES]
                body = raw.decode(response.charset or "utf-8", errors="replace")
                return StaticFetchResult(
                    url=url,
                    status_code=response.status,
                    content_type=content_type,
                    body=body,
                    headers=dict(response.headers.items()),
                    resolved_url=str(response.url),
                )
        except Exception as e:
            logger.debug("Stealth static retry failed for %s: %s", url, e)
            return None

    async def _extract_page_content(self, raw: StaticFetchResult, url: str) -> PageContent | None:
        ct = raw.content_type
        if raw.cached:
            return PageContent(
                text="",
                markdown="",
                title="",
                metadata={"cached": True, "status": "not_modified"},
                status_code=raw.status_code,
            )

        is_text_type = any(
            t in ct
            for t in (
                "text/html",
                "text/markdown",
                "text/x-markdown",
                "text/plain",
                "text/xml",
                "application/xml",
                "application/rss+xml",
                "application/atom+xml",
            )
        )
        if not is_text_type:
            return await self._extract_binary_content(raw, url)

        if "markdown" in ct:
            return await asyncio.to_thread(self._extract_markdown_content, raw, url)
        if "text/html" in ct:
            return await asyncio.to_thread(self._extract_html_content, raw, url)
        elif "text/plain" in ct:
            return self._extract_plain_text_content(raw, url)
        else:
            return self._extract_xml_content(raw, url)

    def _parse_html_string(
        self, html: str, url: str
    ) -> tuple[str, str, str, dict[str, Any], list[dict[str, str]]]:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""
        content_soup = self._extract_main_content_soup(soup)
        text = self._extract_text_from_soup(content_soup)
        markdown = markdownify.markdownify(str(content_soup), heading_style="ATX")
        metadata = self.extract_metadata(soup)
        links = self.extract_links(soup, url)
        return title, text, markdown, metadata, links

    def _extract_html_content(self, raw: StaticFetchResult, url: str) -> PageContent:
        title, text_content, markdown_content, metadata, discovered_links = self._parse_html_string(
            raw.body, url
        )
        return PageContent(
            text=text_content,
            markdown=markdown_content,
            title=title,
            metadata=metadata,
            discovered_links=discovered_links,
            status_code=raw.status_code,
        )

    _MD_INLINE_LINK_RE = re.compile(
        r"""\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:"[^"]*"|'[^']*'))?\s*\)"""
    )
    _MD_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")

    def _resolve_md_link(self, base_url: str, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            return None
        resolved = urljoin(base_url, href)
        if not resolved.startswith(("http://", "https://")):
            return None
        return self.normalize_url(resolved)

    @staticmethod
    def _markdown_to_text(md: str) -> str:
        text = re.sub(r"<!--.*?-->", " ", md, flags=re.DOTALL)
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"`{1,3}[^`]*`{1,3}", " ", text)
        text = re.sub(r"^\s{0,3}[>#\-\*\+]+\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"[*_~]{1,3}", "", text)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _extract_markdown_content(self, raw: StaticFetchResult, url: str) -> PageContent:
        body = raw.body or ""
        discovered_links: list[dict[str, str]] = []
        seen: set[str] = set()
        for href in self._MD_INLINE_LINK_RE.findall(body) + self._MD_AUTOLINK_RE.findall(body):
            resolved = self._resolve_md_link(url, href)
            if resolved and resolved not in seen:
                seen.add(resolved)
                discovered_links.append({"url": resolved, "text": ""})

        title = ""
        in_fence = False
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if not in_fence and stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break
        if not title:
            title = url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title()

        return PageContent(
            text=self._markdown_to_text(body),
            markdown=body,
            title=title,
            metadata={"content-type": raw.content_type, "estimated_title": title},
            discovered_links=discovered_links,
            status_code=raw.status_code,
        )

    def _extract_plain_text_content(self, raw: StaticFetchResult, url: str) -> PageContent:
        text_content = raw.body.strip()
        lines = text_content.split("\n")
        title_text = ""
        for line in lines[:5]:
            line = line.strip()
            if line and (
                any(
                    kw in line.lower()
                    for kw in [
                        "privacy",
                        "terms",
                        "policy",
                        "agreement",
                        "license",
                        "legal",
                        "notice",
                    ]
                )
                or len(line) < 100
            ):
                title_text = line
                break
        if not title_text:
            url_parts = url.rstrip("/").split("/")
            if url_parts:
                title_text = url_parts[-1].replace("-", " ").replace("_", " ").title()
        return PageContent(
            text=text_content,
            markdown=text_content,
            title=title_text,
            metadata={
                "content-type": raw.content_type,
                "estimated_title": title_text,
                "line_count": len(lines),
                "character_count": len(text_content),
            },
            discovered_links=[],
            status_code=raw.status_code,
        )

    def _extract_xml_content(self, raw: StaticFetchResult, url: str) -> PageContent:
        discovered_links: list[dict[str, str]] = []
        text_content = ""
        title_text = ""
        try:
            sitemap_urls = self._parse_sitemap_xml(raw.body)
            if sitemap_urls:
                discovered_links = [
                    {"url": self.normalize_url(u), "text": ""} for u in sitemap_urls
                ]
                title_text = "XML Sitemap or Feed"
                text_content = f"Contains {len(sitemap_urls)} URLs"
        except Exception as e:
            logger.debug(f"Failed to parse XML content from {url}: {e}")
            text_content = raw.body.strip()
            title_text = "XML Document"
        return PageContent(
            text=text_content,
            markdown=text_content,
            title=title_text,
            metadata={
                "content-type": raw.content_type,
                "estimated_title": title_text,
                "link_count": len(discovered_links),
            },
            discovered_links=discovered_links,
            status_code=raw.status_code,
        )

    async def _extract_binary_content(self, raw: StaticFetchResult, url: str) -> PageContent | None:
        if not self.enable_binary_crawling:
            return None
        if "application/pdf" not in raw.content_type and not raw.content_type.startswith(
            "application/"
        ):
            return None
        if not raw.raw_bytes:
            return None

        from src.document_processor import DocumentProcessor

        processor = DocumentProcessor(
            max_content_length=5000,
            enable_binary_parsing=True,
            prefer_tika=self.use_tika_for_binaries,
            prefer_pdfminer=self.use_pdfminer_for_pdf,
        )
        filename = urlparse(url).path.split("/")[-1] or "document"
        text_content = await processor._extract_text(raw.raw_bytes, filename, raw.content_type)

        if not text_content:
            return None

        return PageContent(
            text=text_content,
            markdown=text_content,
            title=filename,
            metadata={
                "content-type": raw.content_type,
                "estimated_title": filename,
                "line_count": len(text_content.splitlines()),
                "character_count": len(text_content),
            },
            discovered_links=[],
            status_code=raw.status_code,
        )

    _BROWSER_CRASH_MARKERS = (
        "browser has been closed",
        "target closed",
        "connection closed",
        "context or browser has been closed",
        "browser closed",
        "window is null",  # Camoufox crash: context.new_page() fails when browser process dies
        # Playwright Node.js driver crash: FFBrowserContext._onUncaughtError reads
        # error.location.url without null-checking; if the page throws an uncaught JS
        # error with no location the Node.js process dies with this TypeError.
        "cannot read properties of undefined",
    )

    def _browser_render_slot(self) -> asyncio.Semaphore:
        return get_global_browser_slot(self.browser_concurrency)

    async def _browser_fetch(self, url: str) -> PageContent | None:
        try:
            _browser_manager, context = await self._setup_browser()
        except Exception as e:
            logger.warning("Browser setup failed for %s: %s", url, e)
            return None

        page = None
        _browser_cleaned_up = False
        try:
            page = await context.new_page()
            await page.set_extra_http_headers({"Accept-Encoding": "gzip, deflate"})
            await _block_heavy_assets(page)

            nav_timeout_ms = min(self.timeout * 1000, BROWSER_NAV_TIMEOUT_MS)

            response = await page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)

            if not response:
                return None

            try:
                await page.wait_for_load_state("load", timeout=BROWSER_LOAD_STATE_TIMEOUT_MS)
            except Exception:
                pass

            title = await page.title()
            content = await page.content()

            final_url = page.url or url
            if final_url != url:
                logger.debug(f"Browser redirect detected: {url} -> {final_url}")

            _, text_content, markdown_content, metadata, discovered_links = await asyncio.to_thread(
                self._parse_html_string, content, final_url
            )

            body_text_len = len(text_content) if text_content else 0
            if body_text_len < MIN_CONTENT_LENGTH_FOR_SPA_CHECK:
                for _ in range(SPA_HYDRATION_RETRIES):
                    await asyncio.sleep(1)
                    new_content = await page.content()
                    _, new_text, new_md, new_meta, new_links = await asyncio.to_thread(
                        self._parse_html_string, new_content, final_url
                    )
                    new_len = len(new_text) if new_text else 0
                    if new_len >= MIN_CONTENT_LENGTH_FOR_SPA_CHECK or new_len == body_text_len:
                        if new_len > body_text_len:
                            text_content = new_text
                            markdown_content = new_md
                            metadata = new_meta
                            discovered_links = new_links
                        break
                    body_text_len = new_len
                    text_content = new_text
                    markdown_content = new_md
                    metadata = new_meta
                    discovered_links = new_links

            metadata["_browser_resolved_url"] = final_url

            return PageContent(
                text=text_content,
                markdown=markdown_content,
                title=title,
                metadata=metadata,
                discovered_links=discovered_links,
                status_code=response.status,
            )

        except Exception as e:
            error_str = str(e).lower()
            if any(marker in error_str for marker in self._BROWSER_CRASH_MARKERS):
                logger.warning("Browser driver crash detected for %s: %s", url, e)
                await _log_top_processes(logger)
                await _log_browser_processes(logger)
                _browser_cleaned_up = True
                await self._cleanup_browser()
            else:
                logger.warning(f"Browser fetch failed for {url}: {e}", exc_info=True)
            return None
        finally:
            if page is not None and not _browser_cleaned_up:
                try:
                    await asyncio.wait_for(page.close(), timeout=10.0)
                except Exception:
                    logger.warning("page.close() failed or timed out; triggering browser cleanup")
                    try:
                        await self._cleanup_browser()
                    except Exception:
                        pass

    def _build_crawl_result(self, url: str, page: PageContent) -> CrawlResult:
        resolved_url = self._choose_effective_url(url, page.metadata)
        if resolved_url != url:
            page.metadata["canonical_resolved"] = True
            url = resolved_url

        result = CrawlResult(
            url=url,
            title=page.title,
            content=page.text,
            markdown=page.markdown,
            metadata=page.metadata,
            status_code=page.status_code,
            success=True,
            discovered_links=page.discovered_links,
        )
        if self.content_analyzer:
            text = result.content or result.markdown
            _, raw_score, _ = self.content_analyzer.analyze_content(
                text, title=result.title, metadata=result.metadata
            )
            result = result.model_copy(
                update={"legal_score": min(1.0, raw_score / MAX_LEGAL_SCORE_SCALE)}
            )
        return result

    @staticmethod
    def _top_level_elements(elements: list[Any]) -> list[Any]:
        match_set = set(elements)
        return [el for el in elements if not any(parent in match_set for parent in el.parents)]

    def _extract_main_content_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        selectors = (
            "main",
            "article",
            '[role="main"]',
            '[id*="content" i]',
            '[class*="content" i]',
            '[data-testid*="content" i]',
            '[data-testid*="article" i]',
            '[data-testid="CEPHtmlSection"]',
            '[data-qa*="content" i]',
            '[id*="legal" i]',
            '[class*="legal" i]',
            '[id*="privacy" i]',
            '[class*="privacy" i]',
            '[id*="terms" i]',
            '[class*="terms" i]',
            '[id*="policy" i]',
            '[class*="policy" i]',
        )

        best_html: str | None = None
        best_text_len = 0
        for selector in selectors:
            matches = self._top_level_elements(soup.select(selector))
            matches = [el for el in matches if not self._is_consent_container(el)]
            if not matches:
                continue
            combined_text_len = sum(len(el.get_text(" ", strip=True)) for el in matches)
            min_len = 50 if "data-testid" in selector else 300
            if combined_text_len < min_len or combined_text_len <= best_text_len:
                continue
            best_text_len = combined_text_len
            best_html = (
                str(matches[0])
                if len(matches) == 1
                else "<div>" + "".join(str(el) for el in matches) + "</div>"
            )

        if best_html is not None:
            content_root: Any = BeautifulSoup(best_html, "html.parser")
        else:
            content_root = soup.body or soup
        cleaned = BeautifulSoup(str(content_root), "html.parser")

        for tag in cleaned(["script", "style", "noscript", "template", "svg", "canvas", "iframe"]):
            tag.decompose()

        for tag in cleaned.find_all(
            ["nav", "header", "footer", "aside", "form", "button", "input", "select", "textarea"]
        ):
            tag.decompose()

        for tag in list(cleaned.find_all(True)):
            if tag.parent is None:
                continue
            if tag.attrs is not None and self._is_consent_container(tag):
                tag.decompose()

        boilerplate_pattern = re.compile(
            r"(cookie|consent|banner|popup|modal|newsletter|subscribe|breadcrumb|"
            r"social|share|tracking|advert|promo|sidebar|drawer|menu|navigation|"
            r"footer|header|masthead|toolbar)",
            re.IGNORECASE,
        )

        for tag in cleaned.find_all(True):
            if tag.attrs is None:
                continue
            classes_value = tag.get("class")
            if isinstance(classes_value, list):
                classes = " ".join(str(cls) for cls in classes_value)
            elif classes_value:
                classes = str(classes_value)
            else:
                classes = ""
            attrs = " ".join(
                str(value) for value in [tag.get("id", ""), classes, tag.get("aria-label", "")]
            )
            if attrs and boilerplate_pattern.search(attrs):
                tag_text = tag.get_text(" ", strip=True)
                if self._is_substantive_legal_policy_container(attrs, tag_text):
                    continue
                tag.decompose()

        return cleaned

    @classmethod
    def _is_consent_container(cls, element: Any) -> bool:
        if getattr(element, "attrs", None) is None:
            return False
        class_value = element.get("class")
        if isinstance(class_value, list):
            class_str = " ".join(str(cls) for cls in class_value)
        else:
            class_str = str(class_value or "")
        attrs = f"{element.get('id') or ''} {class_str}"
        if not _CONSENT_CONTAINER_RE.search(attrs):
            return False
        text_lower = element.get_text(" ", strip=True).lower()
        return sum(marker in text_lower for marker in _CONSENT_TEXT_MARKERS) >= 2

    @staticmethod
    def _is_substantive_legal_policy_container(attrs: str, text: str) -> bool:
        attrs_lower = attrs.lower()
        text_lower = text.lower()

        legal_attr_keywords = (
            "legal",
            "privacy",
            "policy",
            "terms",
            "gdpr",
            "ccpa",
            "data-protection",
            "data_protection",
            "dpa",
            "cookie-policy",
            "cookie_policy",
        )
        if not any(keyword in attrs_lower for keyword in legal_attr_keywords):
            return False

        if len(text_lower) < 300:
            return False

        legal_text_pattern = re.compile(
            r"\b(?:privacy|terms|policy|agreement|legal|gdpr|ccpa|cookie|data protection|"
            r"liability|disclaimer|jurisdiction|compliance|consent|rights)\b",
            re.IGNORECASE,
        )
        return bool(legal_text_pattern.search(text_lower))

    def _extract_text_from_soup(self, soup: BeautifulSoup) -> str:
        text_content = soup.get_text(separator="\n")
        text_content = text_content.replace("\xa0", " ")
        text_content = re.sub(r"[ \t]+", " ", text_content)
        text_content = re.sub(r"\n{3,}", "\n\n", text_content)
        return text_content.strip()

    @staticmethod
    @lru_cache(maxsize=50000)  # noqa: B019 - Static method cache is safe
    def _parse_url(url: str) -> ParseResult:
        return urlparse(url)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        domain_lower = domain.lower().strip()

        if "://" in domain_lower:
            domain_lower = domain_lower.split("://", 1)[1]
        if "/" in domain_lower:
            domain_lower = domain_lower.split("/", 1)[0]
        if ":" in domain_lower:
            domain_lower = domain_lower.split(":", 1)[0]
        if domain_lower.startswith("www."):
            domain_lower = domain_lower[4:]

        return domain_lower

    @staticmethod
    def _strip_tracking_params(query: str) -> str:
        if not query:
            return query
        kept = [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if not (key.lower().startswith("utm_") or key.lower() in _TRACKING_QUERY_PARAMS)
        ]
        return urlencode(kept)

    def normalize_url(self, url: str) -> str:
        parsed = self._parse_url(url)

        normalized = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                self._strip_tracking_params(parsed.query),
                "",
            )
        )

        if normalized.endswith("/") and len(parsed.path) > 1:
            normalized = normalized[:-1]

        return normalized

    def _choose_effective_url(self, url: str, metadata: dict[str, Any]) -> str:
        candidate = None
        if metadata:
            candidate = metadata.get("canonical_url") or metadata.get("og:url")
        if not candidate:
            return self.normalize_url(url)

        try:
            candidate_abs = urljoin(url, str(candidate).strip())
            canonical_normalized = self.normalize_url(candidate_abs)

            if self.is_same_domain(url, canonical_normalized):
                return canonical_normalized

            if self.allowed_domains:
                parsed = urlparse(canonical_normalized)
                canon_domain = self._normalize_domain(parsed.netloc)
                normalized_allowed = {self._normalize_domain(d) for d in self.allowed_domains}
                if canon_domain in normalized_allowed or any(
                    canon_domain.endswith("." + d) for d in normalized_allowed
                ):
                    return canonical_normalized

        except Exception as e:
            logger.debug(f"Failed to process canonical URL {candidate}: {e}")

        return self.normalize_url(url)

    @staticmethod
    def _decode_sitemap_bytes(raw: bytes, url: str) -> str:
        if raw[:2] == b"\x1f\x8b" or url.lower().endswith(".gz"):
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError) as exc:
                logger.debug(f"Failed to gunzip sitemap {url}: {exc}")
                return ""
        return raw.decode("utf-8", errors="replace")

    def _parse_sitemap_xml(self, content: str) -> list[str]:
        urls: list[str] = []
        try:
            soup = BeautifulSoup(content, "xml")

            sitemap_tags = soup.find_all("sitemap")
            if sitemap_tags:
                for sitemap in sitemap_tags:
                    loc = sitemap.find("loc")
                    if loc and loc.string:
                        urls.append(loc.string.strip())
            else:
                url_tags = soup.find_all("url")
                for url_tag in url_tags:
                    loc = url_tag.find("loc")
                    if loc and loc.string:
                        urls.append(loc.string.strip())
        except Exception as e:
            logger.warning(f"Failed to parse sitemap XML: {e}")

        return urls

    _WELL_KNOWN_SITEMAP_PATHS = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-index.xml",
        "/sitemaps.xml",
    ]

    async def _discover_sitemap_urls(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> list[str]:
        parsed_url = urlparse(base_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        headers = {"User-Agent": self.user_agent}

        sitemap_candidates: list[str] = []

        if self.robots_checker:
            try:
                async with session.get(f"{origin}/robots.txt", headers=headers) as response:
                    if response.status == 200:
                        robots_content = await response.text()
                        rules = self.robots_checker._parse_robots_txt(robots_content)
                        sitemap_candidates.extend(rules.get("sitemaps", []))
            except Exception as e:
                logger.debug(f"Failed to fetch robots.txt: {e}")

        known = {s.rstrip("/") for s in sitemap_candidates}
        for path in self._WELL_KNOWN_SITEMAP_PATHS:
            candidate = f"{origin}{path}"
            if candidate.rstrip("/") not in known:
                sitemap_candidates.append(candidate)

        seen_urls: set[str] = set()
        discovered_urls: list[str] = []

        max_sitemap_bytes = 5_000_000
        max_child_sitemaps = MAX_CHILD_SITEMAPS
        fetch_timeout = aiohttp.ClientTimeout(total=15)

        async def _fetch_and_parse_sitemap(sitemap_url: str) -> list[str]:
            try:
                async with session.get(sitemap_url, headers=headers, timeout=fetch_timeout) as resp:
                    if resp.status != 200:
                        return []
                    declared = resp.headers.get("Content-Length")
                    if declared and declared.isdigit() and int(declared) > max_sitemap_bytes:
                        return []
                    raw = await resp.content.read(max_sitemap_bytes + 1)
                    if len(raw) > max_sitemap_bytes:
                        return []
                    body = self._decode_sitemap_bytes(raw, sitemap_url)
                    return self._parse_sitemap_xml(body) if body else []
            except Exception as e:
                logger.debug(f"Failed to fetch sitemap {sitemap_url}: {e}")
                return []

        for sitemap_url in sitemap_candidates:
            urls = await _fetch_and_parse_sitemap(sitemap_url)
            if not urls:
                continue

            child_sitemaps: list[str] = []
            for url in urls:
                if "sitemap" in url.lower() and url.lower().endswith((".xml", ".xml.gz")):
                    child_sitemaps.append(url)
                elif url not in seen_urls:
                    seen_urls.add(url)
                    discovered_urls.append(url)

            policy_sitemaps: list[str] = []
            generic_sitemaps: list[str] = []
            for child_sitemap in child_sitemaps:
                if _POLICY_SITEMAP_RE.search(child_sitemap):
                    policy_sitemaps.append(child_sitemap)
                else:
                    generic_sitemaps.append(child_sitemap)

            policy_sitemaps.sort(key=self.url_scorer.score_url, reverse=True)
            generic_sitemaps.sort(key=self.url_scorer.score_url, reverse=True)

            capped_policy = policy_sitemaps[:max_child_sitemaps]
            max_generic_to_fetch = min(
                _MAX_GENERIC_CHILD_SITEMAPS,
                max(0, max_child_sitemaps - len(capped_policy)),
            )
            skipped_generic = len(generic_sitemaps) - max_generic_to_fetch
            if skipped_generic > 0:
                logger.info(
                    "skipping %d generic child sitemaps (cap=%d)",
                    skipped_generic,
                    max_generic_to_fetch,
                )
            children_to_fetch = capped_policy + generic_sitemaps[:max_generic_to_fetch]

            for child_url in children_to_fetch:
                nested_urls = await _fetch_and_parse_sitemap(child_url)
                for url in nested_urls:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        discovered_urls.append(url)

        return discovered_urls

    def _parse_robots_txt(self, content: str) -> dict[str, Any]:
        if self.robots_checker:
            return self.robots_checker._parse_robots_txt(content)
        return {"user_agents": {}}

    def is_allowed_domain(self, url: str) -> bool:
        if not self.allowed_domains:
            return True

        url_ext = _TLD_EXTRACT(url)
        url_domain = url_ext.domain

        for allowed in self.allowed_domains:
            allowed_ext = _TLD_EXTRACT(allowed)
            if url_domain == allowed_ext.domain:
                return True

        return False

    def is_same_domain(self, url1: str, url2: str) -> bool:
        parsed1 = self._parse_url(url1)
        parsed2 = self._parse_url(url2)
        domain1 = self._normalize_domain(parsed1.netloc)
        domain2 = self._normalize_domain(parsed2.netloc)

        return domain1 == domain2

    def should_crawl_url(self, url: str, base_url: str, depth: int) -> bool:
        if depth > self.max_depth:
            return False

        if url in self.visited_urls or url in self.failed_urls or url in self.queued_urls:
            return False

        if self.normalize_url(url) in self._recently_stored_urls:
            return False

        parsed_url = self._parse_url(url)

        if parsed_url.scheme != "https":
            return False

        subdomain = _TLD_EXTRACT(url).subdomain.lower()
        if subdomain and _MIRROR_SUBDOMAIN_RE.search(subdomain):
            return False

        url_domain = self._normalize_domain(parsed_url.netloc)

        if self.allowed_domains:
            if not self.is_allowed_domain(url):
                return False

        if not self.follow_external_links:
            parsed_base = self._parse_url(base_url)
            base_domain = self._normalize_domain(parsed_base.netloc)
            is_same_domain = url_domain == base_domain or url_domain.endswith("." + base_domain)

            if not is_same_domain and not self.allowed_domains:
                return False

        path = parsed_url.path or "/"

        for pattern in self.compiled_denied_paths:
            if pattern.search(path):
                return False

        if self.compiled_allowed_paths:
            is_path_allowed = False
            for pattern in self.compiled_allowed_paths:
                if pattern.search(path):
                    is_path_allowed = True
                    break
            if not is_path_allowed:
                return False

        for pattern in self.compiled_skip_patterns:
            if pattern.search(url):
                return False

        normalized_parsed = self._parse_url(self.normalize_url(url))

        english_key, english_variant = english_locale_canonical_key(normalized_parsed)
        if english_variant is not None:
            seen_variants = self._english_locale_seen.setdefault(english_key, set())
            if english_variant in seen_variants:
                return False
            if len(seen_variants) >= self.max_english_locale_variants:
                return False
            seen_variants.add(english_variant)

        canonical_key, had_language_signal, is_english = locale_canonical_key(normalized_parsed)
        if had_language_signal and not is_english and canonical_key in self._locale_seen_keys:
            return False
        self._locale_seen_keys.add(canonical_key)

        return True

    def extract_links(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []

        def add_url(raw_url: str | None, text: str = "", rel: str | None = None) -> None:
            if not raw_url:
                return
            raw_url = str(raw_url).strip()
            if (
                raw_url.startswith("javascript:")
                or raw_url.startswith("mailto:")
                or raw_url.startswith("tel:")
                or raw_url.startswith("#")
            ):
                return
            absolute = urljoin(base_url, raw_url)
            if absolute.startswith("http://"):
                return
            normalized = self.normalize_url(absolute)
            entry = {"url": normalized, "text": (text or "").strip()}
            if rel:
                entry["rel"] = rel
            links.append(entry)

        for a in soup.find_all("a"):
            href = a.get("href")
            text = (a.get_text() or "").strip()

            if len(text) < 3:
                title_attr = a.get("title")
                aria_label = a.get("aria-label")
                if title_attr:
                    text = str(title_attr).strip()
                elif aria_label:
                    text = str(aria_label).strip()

            rel_attr = a.get("rel")
            rel = (
                " ".join(rel_attr).lower()
                if isinstance(rel_attr, list | tuple)
                else (str(rel_attr).lower() if rel_attr else "")
            )
            add_url(str(href) if href else None, text, rel or None)
            for attr in ("data-href", "data-url", "data-link", "data-target"):
                attr_value = a.get(attr)
                if attr_value:
                    add_url(str(attr_value), text, rel or None)

        page_title = ""
        meta_title = (
            soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "twitter:title"})
            or soup.find("title")
        )
        if meta_title:
            if meta_title.name == "title":
                page_title = meta_title.get_text().strip()
            else:
                content = meta_title.get("content")
                page_title = (str(content) if content else "").strip()

        for link_tag in soup.find_all("link", href=True):
            rel = " ".join(link_tag.get("rel") or [])
            href_value = link_tag.get("href")
            link_text = page_title if rel in ("alternate", "canonical") else f"link:{rel}"
            add_url(str(href_value) if href_value else None, link_text, rel)

        for area in soup.find_all("area", href=True):
            href_value = area.get("href")
            alt_value = area.get("alt")
            add_url(str(href_value) if href_value else None, str(alt_value) if alt_value else "")

        for form in soup.find_all("form", action=True):
            action_value = form.get("action")
            add_url(str(action_value) if action_value else None, "form action")

        for el in soup.find_all():
            for attr in ("data-href", "data-url", "data-action", "data-link"):
                attr_value = el.get(attr)
                if attr_value:
                    add_url(str(attr_value), (el.get_text() or "").strip())

        onclick_elements = soup.find_all(attrs={"onclick": True})  # ty: ignore[invalid-argument-type]
        for el in onclick_elements:
            onclick = str(el.get("onclick") or "")
            matches = re.findall(
                r"(?:location(?:\.href)?|window\.location(?:\.href)?)\s*=\s*['\"](.*?)['\"]|"
                r"location\.assign\(['\"](.*?)['\"]\)|"
                r"location\.replace\(['\"](.*?)['\"]\)",
                onclick,
            )
            for m in matches:
                url_candidate = next((x for x in m if x), None)
                if url_candidate:
                    add_url(url_candidate, (el.get_text() or "").strip())

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = script.string or script.get_text() or ""
                obj = json.loads(payload)

                def _extract_urls(o):
                    if isinstance(o, str):
                        if o.startswith("http"):
                            add_url(o, "json-ld")
                    elif isinstance(o, dict):
                        for v in o.values():
                            _extract_urls(v)
                    elif isinstance(o, list):
                        for item in o:
                            _extract_urls(item)

                _extract_urls(obj)
            except Exception:
                continue

        for meta in soup.find_all("meta"):
            property_value = meta.get("property")
            content_value = meta.get("content")
            if property_value and content_value:
                prop = str(property_value).lower()
                if prop in ("og:url", "og:see_also", "twitter:url"):
                    add_url(str(content_value), prop)

        visible_text = soup.get_text(" ")
        for m in re.findall(r"https?://[^\s'\"<>]+", visible_text):
            add_url(m, "text")

        seen_urls_set = set()
        unique_links: list[dict[str, str]] = []
        for link in links:
            if link["url"] not in seen_urls_set:
                seen_urls_set.add(link["url"])
                unique_links.append(link)

        return unique_links

    def extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        metadata: dict[str, Any] = {}

        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            metadata["lang"] = html_tag.get("lang")

        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text().strip()

        for meta in soup.find_all("meta"):
            if hasattr(meta, "get"):
                name = meta.get("name") or meta.get("property") or meta.get("http-equiv")
                content = meta.get("content")
                if name and content and isinstance(name, str):
                    metadata[name.lower()] = content

        for link in soup.find_all("link", rel=True):
            rel = link.get("rel")
            href = link.get("href")
            if rel and href:
                rel_list = rel if isinstance(rel, list) else [rel]
                for rel_value in rel_list:
                    rel_lower = rel_value.lower()
                    if rel_lower == "canonical":
                        metadata["canonical_url"] = href
                    elif rel_lower == "alternate":
                        hreflang = link.get("hreflang")
                        if hreflang:
                            if "alternate_languages" not in metadata:
                                metadata["alternate_languages"] = {}
                            metadata["alternate_languages"][hreflang] = href

        charset_tag = soup.find("meta", charset=True)
        if charset_tag:
            metadata["charset"] = charset_tag.get("charset")
        else:
            charset_equiv = soup.find(
                "meta", attrs={"http-equiv": re.compile(r"content-type", re.I)}
            )
            if charset_equiv and charset_equiv.get("content"):
                content = charset_equiv.get("content", "")
                charset_match = re.search(r"charset=([^;]+)", str(content), re.I)
                if charset_match:
                    metadata["charset"] = charset_match.group(1).strip()

        for i in range(1, 7):
            headers = soup.find_all(f"h{i}")
            if headers:
                metadata[f"h{i}"] = [h.get_text().strip() for h in headers[:5]]

        return metadata

    async def rate_limit(self, url: str) -> None:
        await self.rate_limiter.rate_limit(url)

    async def _fetch_page_internal(self, session: aiohttp.ClientSession, url: str) -> CrawlResult:
        try:
            raw = await self._static_fetch(session, url)

            if raw.blocked_by_robots_txt:
                return raw.to_failed_crawl_result()

            effective_url = raw.resolved_url or url
            if effective_url != url:
                self.visited_urls.add(self.normalize_url(effective_url))

            if raw.status_code == 404 or self._url_looks_like_not_found_landing(effective_url):
                return CrawlResult(
                    url=effective_url,
                    title="",
                    content="",
                    markdown="",
                    metadata={},
                    status_code=raw.status_code,
                    success=False,
                    error_message="Not found (404)",
                )

            page = await self._extract_page_content(raw, effective_url)

            static_unusable = (
                needs_browser_fallback(raw)
                or page is None
                or not self._content_is_sufficient(page, effective_url)
            )

            # When the bot UA triggered a JS-shell bot-wall (HTTP 200 but unusable content),
            # retry once with a real Chrome UA before burning an expensive browser slot.
            if static_unusable and raw.status_code == 200 and needs_browser_fallback(raw):
                stealth_raw = await self._static_fetch_stealth(session, url)
                if stealth_raw is not None and not needs_browser_fallback(stealth_raw):
                    stealth_effective = stealth_raw.resolved_url or effective_url
                    stealth_page = await self._extract_page_content(stealth_raw, stealth_effective)
                    if stealth_page is not None and self._content_is_sufficient(
                        stealth_page, stealth_effective
                    ):
                        logger.debug("Stealth static retry resolved %s", url)
                        if stealth_effective != effective_url:
                            self.visited_urls.add(self.normalize_url(stealth_effective))
                            effective_url = stealth_effective
                        page = stealth_page
                        static_unusable = False

            is_speculative = self.normalize_url(url) in self._speculative_urls

            if static_unusable and self.use_browser and not is_speculative:
                relevance = max(
                    self._url_scores.get(self.normalize_url(url), 0.0),
                    self.url_scorer.score_url(effective_url),
                )
                if relevance >= self.min_legal_score:
                    if self._consecutive_browser_failures >= BROWSER_DOMAIN_FAILURE_CAP:
                        logger.debug(
                            "Browser cap reached (%d consecutive failures) — disabling browser for remainder of crawl",
                            self._consecutive_browser_failures,
                        )
                        return CrawlResult(
                            url=effective_url,
                            title=(page.title if page else ""),
                            content="",
                            markdown="",
                            metadata=(page.metadata if page else {}),
                            status_code=raw.status_code,
                            success=False,
                            error_message="Static content unusable and browser rendering skipped due to domain failure cap",
                            discovered_links=(page.discovered_links if page else []),
                        )
                    else:
                        slot_wait_start = time.monotonic()
                        async with self._browser_render_slot():
                            self._render_slot_wait_total += time.monotonic() - slot_wait_start
                            self._render_attempts += 1
                            browser_page = await self._browser_fetch(effective_url)
                        if browser_page is not None and self._content_is_sufficient(
                            browser_page, effective_url
                        ):
                            self._consecutive_browser_failures = 0
                            browser_resolved = browser_page.metadata.pop(
                                "_browser_resolved_url", None
                            )
                            if browser_resolved and browser_resolved != effective_url:
                                effective_url = browser_resolved
                                self.visited_urls.add(self.normalize_url(effective_url))
                            if self._in_render_retry:
                                self._render_recovered += 1
                            return self._build_crawl_result(effective_url, browser_page)

                        self._consecutive_browser_failures += 1
                        if browser_page is None:
                            self._render_failures += 1
                            if not self._in_render_retry:
                                self._render_retry_queue.append(effective_url)

                        return CrawlResult(
                            url=effective_url,
                            title=(browser_page.title if browser_page else ""),
                            content="",
                            markdown="",
                            metadata=(browser_page.metadata if browser_page else {}),
                            status_code=(
                                browser_page.status_code if browser_page else raw.status_code
                            ),
                            success=False,
                            error_message="Static content unusable and browser rendering failed",
                            discovered_links=(
                                browser_page.discovered_links if browser_page else []
                            ),
                        )

                if page is not None:
                    return self._build_crawl_result(effective_url, page)

            if page is None:
                return CrawlResult(
                    url=effective_url,
                    title="",
                    content="",
                    markdown="",
                    metadata={"content-type": raw.content_type},
                    status_code=raw.status_code,
                    success=False,
                    error_message=f"Unsupported content type: {raw.content_type}",
                )

            return self._build_crawl_result(effective_url, page)

        except aiohttp.ClientResponseError as e:
            if e.status >= 500 or e.status == 429:
                raise
            return CrawlResult(
                url=url,
                title="",
                content="",
                markdown="",
                metadata={},
                status_code=e.status,
                success=False,
                error_message=f"HTTP {e.status}: {e.message}",
            )
        except (aiohttp.ClientError, TimeoutError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}", exc_info=True)
            return CrawlResult(
                url=url,
                title="",
                content="",
                markdown="",
                metadata={},
                status_code=0,
                success=False,
                error_message=str(e),
            )

    async def fetch_page(self, session: aiohttp.ClientSession, url: str) -> CrawlResult:
        max_attempts = self.max_retries + 1

        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
            reraise=True,
        )
        async def _fetch_with_configurable_retry() -> CrawlResult:
            return await self._fetch_page_internal(session, url)

        try:
            return await _fetch_with_configurable_retry()
        except aiohttp.ClientResponseError as e:
            if e.status >= 500 or e.status == 429:
                return CrawlResult(
                    url=url,
                    title="",
                    content="",
                    markdown="",
                    metadata={},
                    status_code=e.status,
                    success=False,
                    error_message=f"HTTP {e.status}: {e.message} (retries exhausted)",
                )
            else:
                return CrawlResult(
                    url=url,
                    title="",
                    content="",
                    markdown="",
                    metadata={},
                    status_code=e.status,
                    success=False,
                    error_message=f"HTTP {e.status}: {e.message}",
                )
        except (aiohttp.ClientError, TimeoutError) as e:
            return CrawlResult(
                url=url,
                title="",
                content="",
                markdown="",
                metadata={},
                status_code=0,
                success=False,
                error_message=f"{type(e).__name__}: {str(e)} (retries exhausted)",
            )

    _LOCALE_RE = re.compile(r"^[a-z]{2}(?:[-_][a-zA-Z]{2,4})?$")

    def generate_potential_policy_urls(self, base_url: str) -> list[str]:
        parsed = urlparse(base_url)
        domain = parsed.netloc

        legal_paths = [
            "/legal",
            "/legal/privacy",
            "/legal/terms",
            "/legal/cookies",
            "/legal/tos",
            "/privacy",
            "/privacy-policy",
            "/terms",
            "/terms-of-service",
            "/terms-of-use",
            "/tos",
            "/cookies",
            "/gdpr",
            "/cookie-policy",
            "/legal/privacy-policy",
            "/legal/terms-of-service",
            "/legal/terms-of-use",
            "/legal/cookie-policy",
            "/company/legal",
            "/company/privacy",
            "/company/terms",
            "/company/tos",
            "/company/cookies",
            "/about/legal",
            "/about/privacy",
            "/about/terms",
            "/about/tos",
            "/support/legal",
            "/support/privacy",
            "/support/terms",
            "/help/legal",
            "/help/privacy",
            "/help/terms",
            "/policies",
            "/policies/privacy",
            "/policies/terms",
            "/policies/cookies",
            "/legal/policies",
            "/legal/policies/privacy",
            "/legal/policies/terms",
            "/legal/policies/cookies",
            "/policy",
            "/policy/privacy",
            "/policy/terms",
            "/policy/terms-of-service",
            "/policy/terms-of-use",
            "/policy/cookies",
            "/policy/cookie",
            "/policy/data",
            "/policy/gdpr",
            "/policy/ccpa",
            "/policy/community",
            "/policy/safety",
            "/policy/copyright",
            "/trust",
            "/trust/legal",
            "/trust/privacy",
        ]

        hub_paths = [
            "/articles",
            "/collections",
            "/categories",
            "/sections",
            "/docs",
            "/help",
            "/help/articles",
            "/help/collections",
            "/support",
            "/support/articles",
            "/support/solutions",
            "/knowledge",
            "/knowledge-base",
            "/kb",
            "/faq",
            "/hc",
        ]

        base_path = parsed.path.rstrip("/")
        prefixes: list[str] = [""]

        if base_path and base_path != "/":
            prefixes.append(base_path)
            segments = [s for s in base_path.split("/") if s]
            if len(segments) > 1:
                for i in range(1, len(segments)):
                    sub = "/" + "/".join(segments[:i])
                    if sub not in prefixes:
                        prefixes.append(sub)

        seen: set[str] = set()
        potential_urls: list[str] = []

        def _add(path: str) -> None:
            url = f"https://{domain}{path}"
            if url not in seen:
                seen.add(url)
                potential_urls.append(url)

        for prefix in prefixes:
            for path in legal_paths:
                _add(f"{prefix}{path}")
            for path in hub_paths:
                _add(f"{prefix}{path}")

        return potential_urls

    _LEGAL_HUB_RE = re.compile(
        r"\b(?:"
        r"gdpr|ccpa|lgpd|pipeda|hipaa|"
        r"terms?|privacy|cookie|legal|"
        r"trust|transparency|compliance|"
        r"agreement|policy|disclaimer|"
        r"eula|dpa|aup|tos|"
        r"data\s+(?:protection|processing|sharing|policy)|"
        r"acceptable\s+use|"
        r"community\s+guidelines|"
        r"safety\s+policy|"
        r"security\s+policy|"
        r"responsible\s+disclosure"
        r")\b",
        re.IGNORECASE,
    )

    def _compute_parent_page_boost(self, page_metadata: dict[str, Any] | None) -> float:
        if not page_metadata:
            return 0.0

        texts_to_check = [
            (page_metadata.get("title") or "").lower(),
            (page_metadata.get("description") or "").lower(),
            (page_metadata.get("og:title") or "").lower(),
        ]

        for text in texts_to_check:
            if self._LEGAL_HUB_RE.search(text):
                return 3.0

        return 0.0

    def _remember_score(self, url: str, score: float) -> None:
        key = self.normalize_url(url)
        prev = self._url_scores.get(key)
        if prev is None or score > prev:
            self._url_scores[key] = score

    def _enqueue_best_first(self, url: str, depth: int, score: float, base_score: float) -> None:
        policy_rank = 0 if self.url_scorer.is_strong_policy_path(url) else 1
        heapq.heappush(self.url_priority_queue, (policy_rank, -score, url, depth, base_score))
        if base_score >= self.min_legal_score:
            self._frontier_real_leads += 1
            self._crawls_since_new_lead = 0

    def _frontier_top_base_score(self) -> float | None:
        if self.strategy != "best_first" or not self.url_priority_queue:
            return None
        return max(base_score for _, _, _, _, base_score in self.url_priority_queue)

    def _relevance_exhausted(self) -> bool:
        if (
            self.strategy != "best_first"
            or self._policy_pages_found < 1
            or self._crawls_since_new_lead < CRAWL_EXHAUSTION_GRACE
        ):
            return False
        top_base_score = self._frontier_top_base_score()
        return top_base_score is not None and top_base_score < self.min_legal_score

    def add_urls_to_queue(
        self,
        links: list[dict[str, str]],
        base_url: str,
        depth: int,
        page_metadata: dict[str, Any] | None = None,
    ) -> None:
        if page_metadata and self.respect_meta_robots:
            robots_meta = page_metadata.get("robots") or page_metadata.get("meta:robots")
            if isinstance(robots_meta, str) and "nofollow" in robots_meta.lower():
                return

        parent_boost = (
            self._compute_parent_page_boost(page_metadata) if self.strategy == "best_first" else 0.0
        )

        skipped_urls: set[str] = set()
        policy_lead_found = False
        for link in links:
            url = link["url"]
            anchor_text = link.get("text")
            rel = link.get("rel") or ""

            if rel and "nofollow" in rel and not self.follow_nofollow:
                skipped_urls.add(self.normalize_url(url))
                continue

            if not self.should_crawl_url(url, base_url, depth + 1):
                continue

            base_score = self.url_scorer.score_url(url, anchor_text=anchor_text)
            score = base_score
            if parent_boost and not self.url_scorer.is_non_policy_section(url):
                score += parent_boost
            self._remember_score(url, score)
            if score >= self.min_legal_score:
                policy_lead_found = True

            self.queued_urls.add(url)
            if self.strategy == "bfs":
                self.url_queue.append((url, depth + 1))
            elif self.strategy == "dfs":
                self.url_stack.append((url, depth + 1))
            elif self.strategy == "best_first":
                if score < self.min_legal_score:
                    self.queued_urls.discard(url)
                    continue
                self._enqueue_best_first(url, depth + 1, score, base_score)

        if depth == 0 and not self._sitemap_seeded and policy_lead_found:
            pass
        elif depth == 0 and not self._sitemap_seeded:
            potential_legal_urls = self.generate_potential_policy_urls(base_url)

            for url in potential_legal_urls:
                normalized = self.normalize_url(url)
                if normalized in skipped_urls:
                    continue

                if not self.should_crawl_url(url, base_url, 1):
                    continue

                score = self.url_scorer.score_url(url, anchor_text=None)
                self._remember_score(url, score)
                self._speculative_urls.add(normalized)

                self.queued_urls.add(url)
                if self.strategy == "bfs":
                    self.url_queue.append((url, 1))
                elif self.strategy == "dfs":
                    self.url_stack.append((url, 1))
                elif self.strategy == "best_first":
                    self._enqueue_best_first(url, 1, score, score)

    def get_next_url(self) -> tuple[str, int] | None:
        if self.strategy == "bfs" and self.url_queue:
            return self.url_queue.popleft()
        elif self.strategy == "dfs" and self.url_stack:
            return self.url_stack.pop()
        elif self.strategy == "best_first" and self.url_priority_queue:
            _, _, url, depth, base_score = heapq.heappop(self.url_priority_queue)
            if base_score >= self.min_legal_score:
                self._frontier_real_leads -= 1
            return url, depth
        return None

    def _report_crawl_progress(self, *, force: bool = False) -> None:
        if not self.progress_callback:
            return

        processed = self.stats.total_urls
        if not force and processed - self._last_progress_report < self.PROGRESS_REPORT_INTERVAL:
            return

        self._last_progress_report = processed
        pending = self._get_pending_url_count()
        total_known = min(self.max_pages, len(self.visited_urls) + pending)

        self.progress_callback(self.stats.crawled_urls, total_known)

    async def _emit_result(self, result: CrawlResult) -> None:
        if self.result_callback is not None:
            await self.result_callback(result)

    async def _should_stop_early(self) -> bool:
        if self.stop_callback is None:
            return False
        decision = self.stop_callback()
        if isinstance(decision, Awaitable):
            decision = await decision
        return bool(decision)

    async def _drain_render_retries(self, session: aiohttp.ClientSession) -> None:
        if not self._render_retry_queue:
            return

        pending = list(dict.fromkeys(self._render_retry_queue))
        self._render_retry_queue = []

        self._in_render_retry = True
        try:
            for url in pending:
                result = await self.fetch_page(session, url)
                if result.success:
                    self.stats.crawled_urls += 1
                    self.stats.failed_urls = max(0, self.stats.failed_urls - 1)
                    self.failed_urls.discard(url)
                    self.results.append(result)
                    await self._emit_result(result)
                self.stats.total_urls += 1
                self._report_crawl_progress(force=True)
        finally:
            self._in_render_retry = False

    def _get_pending_url_count(self) -> int:
        if self.strategy == "bfs":
            return len(self.url_queue)
        elif self.strategy == "dfs":
            return len(self.url_stack)
        elif self.strategy == "best_first":
            return len(self.url_priority_queue)
        return 0

    def _has_converged(self, found_policy: bool, pages_since_policy_hit: int) -> bool:
        return (
            self.no_policy_page_budget > 0
            and found_policy
            and pages_since_policy_hit >= self.no_policy_page_budget
        )

    async def crawl(self, base_url: str, *, cleanup: bool = True) -> list[CrawlResult]:
        try:
            base_url = self.normalize_url(base_url)
            self.stats = CrawlStats()
            self._frontier_real_leads = 0
            self._policy_pages_found = 0
            self._crawls_since_new_lead = 0
            self._english_locale_seen.clear()

            self.queued_urls.add(base_url)
            self._remember_score(
                base_url, max(self.url_scorer.score_url(base_url), self.min_legal_score)
            )
            if self.strategy == "bfs":
                self.url_queue.append((base_url, 0))
            elif self.strategy == "dfs":
                self.url_stack.append((base_url, 0))
            elif self.strategy == "best_first":
                score = self.url_scorer.score_url(base_url)
                self._enqueue_best_first(base_url, 0, score, score)

            connector = aiohttp.TCPConnector(limit=self.max_concurrent)
            timeout = aiohttp.ClientTimeout(total=self.timeout)

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                max_line_size=MAX_HEADER_BYTES,
                max_field_size=MAX_HEADER_BYTES,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            ) as session:
                try:
                    sitemap_urls = await self._discover_sitemap_urls(session, base_url)
                    seeded = 0
                    for url in sitemap_urls:
                        if not self.should_crawl_url(url, base_url, 0):
                            continue
                        score = self.url_scorer.score_url(url, anchor_text=None)
                        if score < self.min_legal_score:
                            continue
                        self._remember_score(url, score)
                        self.queued_urls.add(url)
                        if self.strategy == "bfs":
                            self.url_queue.append((url, 0))
                        elif self.strategy == "dfs":
                            self.url_stack.append((url, 0))
                        elif self.strategy == "best_first":
                            self._enqueue_best_first(url, 0, score, score)
                        seeded += 1
                    if seeded:
                        self._sitemap_seeded = True
                except Exception:
                    logger.debug("Sitemap discovery failed; continuing without sitemap")
                semaphore = asyncio.Semaphore(self.max_concurrent)

                async def process_url(url: str) -> CrawlResult:
                    async with semaphore:
                        return await self.fetch_page(session, url)

                pages_since_policy_hit = 0
                found_policy = False
                stop_requested = False
                termination_reason = "unknown"
                while len(self.visited_urls) < self.max_pages:
                    batch = []
                    batch_size = min(self.max_concurrent, self.max_pages - len(self.visited_urls))

                    for _ in range(batch_size):
                        next_item = self.get_next_url()
                        if next_item is None:
                            break
                        url, depth = next_item
                        if url not in self.visited_urls:
                            batch.append((url, depth))
                            self.visited_urls.add(url)

                    if not batch:
                        termination_reason = "url_queue_empty"
                        break

                    tasks = [process_url(url) for url, _depth in batch]
                    batch_results = await asyncio.gather(*tasks)

                    for result, (url, depth) in zip(batch_results, batch, strict=True):
                        self.stats.total_urls += 1
                        self._crawls_since_new_lead += 1

                        if result.success:
                            self.stats.crawled_urls += 1
                            self.results.append(result)
                            self._consecutive_blocked = 0

                            if (
                                result.legal_score is not None
                                and result.legal_score >= CONVERGENCE_LEGAL_SCORE
                            ):
                                found_policy = True
                                pages_since_policy_hit = 0
                                self._policy_pages_found += 1
                            else:
                                pages_since_policy_hit += 1
                        else:
                            self.stats.failed_urls += 1
                            self.failed_urls.add(url)
                            pages_since_policy_hit += 1
                            self._consecutive_blocked += 1
                            if result.blocked_by_robots_txt:
                                self.results.append(result)

                        if depth < self.max_depth and result.discovered_links:
                            self.add_urls_to_queue(
                                result.discovered_links,
                                base_url,
                                depth,
                                page_metadata=result.metadata,
                            )

                        await self._emit_result(result)
                        if await self._should_stop_early():
                            stop_requested = True
                            termination_reason = "stop_requested"
                            break

                    self._report_crawl_progress()

                    if stop_requested:
                        break

                    if self._has_converged(found_policy, pages_since_policy_hit):
                        termination_reason = "converged"
                        break

                    if self._relevance_exhausted():
                        termination_reason = "relevance_exhausted"
                        logger.warning(
                            "Crawl for %s terminated: relevance exhausted after %d pages "
                            "(no high-scoring URLs remain in frontier, "
                            "crawled=%d, policy_pages=%d)",
                            base_url,
                            self.stats.total_urls,
                            self.stats.crawled_urls,
                            self._policy_pages_found,
                        )
                        break

                    if self._consecutive_blocked >= CRAWL_BOT_WALL_ABORT:
                        termination_reason = "bot_wall_abort"
                        logger.warning(
                            "Crawl for %s aborted: %d consecutive URL failures "
                            "(CRAWL_BOT_WALL_ABORT=%d) — likely a bot-wall or auth gate. "
                            "crawled=%d, failed=%d",
                            base_url,
                            self._consecutive_blocked,
                            CRAWL_BOT_WALL_ABORT,
                            self.stats.crawled_urls,
                            self.stats.failed_urls,
                        )
                        break

                else:
                    termination_reason = "page_budget_reached"

                self._report_crawl_progress(force=True)

                # Diagnostic: warn when a crawl completes with 0 successfully crawled pages.
                if self.stats.crawled_urls == 0:
                    robots_blocked_count = sum(1 for r in self.results if r.blocked_by_robots_txt)
                    attempted = self.stats.total_urls
                    if robots_blocked_count > 0 and robots_blocked_count == attempted:
                        self.stats.all_seeds_robots_blocked = True
                        logger.warning(
                            "Crawl for %s completed with 0 pages — all %d attempted URL(s) "
                            "were blocked by robots.txt (termination_reason=%s)",
                            base_url,
                            robots_blocked_count,
                            termination_reason,
                        )
                    elif termination_reason == "url_queue_empty":
                        logger.warning(
                            "Crawl for %s completed with 0 pages — URL queue was empty "
                            "after seeding (sitemap_seeded=%s, robots_blocked=%d/%d, "
                            "termination_reason=%s)",
                            base_url,
                            self._sitemap_seeded,
                            robots_blocked_count,
                            attempted,
                            termination_reason,
                        )
                    elif termination_reason == "bot_wall_abort":
                        logger.warning(
                            "Crawl for %s completed with 0 pages — bot-wall abort triggered "
                            "after %d consecutive failures (termination_reason=%s)",
                            base_url,
                            self._consecutive_blocked,
                            termination_reason,
                        )
                    else:
                        logger.warning(
                            "Crawl for %s completed with 0 pages "
                            "(termination_reason=%s, total_attempted=%d, "
                            "robots_blocked=%d, sitemap_seeded=%s)",
                            base_url,
                            termination_reason,
                            attempted,
                            robots_blocked_count,
                            self._sitemap_seeded,
                        )

                if not stop_requested:
                    await self._drain_render_retries(session)

            return self.results
        finally:
            if cleanup:
                await self._shutdown_log_executor()

    async def crawl_multiple(self, urls: list[str]) -> list[CrawlResult]:
        all_results = []

        full_max_pages = self.max_pages
        per_seed_max_pages = max(MIN_PAGES_PER_SEED, full_max_pages // max(1, len(urls)))

        try:
            for _i, url in enumerate(urls, 1):
                if await self._should_stop_early():
                    break
                self.max_pages = per_seed_max_pages
                results = await self.crawl(url, cleanup=False)
                all_results.extend(results)

                self.visited_urls.clear()
                self.failed_urls.clear()
                self.queued_urls.clear()
                self._locale_seen_keys.clear()
                self._english_locale_seen.clear()
                self._sitemap_seeded = False
                self.url_queue.clear()
                self.url_stack.clear()
                self.url_priority_queue.clear()
                self._frontier_real_leads = 0
                self._policy_pages_found = 0
                self._crawls_since_new_lead = 0
                self.results.clear()

                if self.robots_checker:
                    self.robots_checker.clear_cache()
        finally:
            self.max_pages = full_max_pages
            await self._shutdown_log_executor()

        return all_results


# ---- Convenience functions ---------------------------------------------------------


async def crawl_for_policy_documents(
    base_url: str,
    max_depth: int = 4,
    max_pages: int = 1000,
    strategy: str = "bfs",
) -> list[CrawlResult]:
    crawler = ClauseaCrawler(
        max_depth=max_depth, max_pages=max_pages, strategy=strategy, min_legal_score=0.0
    )
    return await crawler.crawl(base_url)


async def test_specific_url(url: str) -> CrawlResult:
    crawler = ClauseaCrawler(max_depth=1, max_pages=1, strategy="bfs", min_legal_score=0.0)

    connector = aiohttp.TCPConnector(limit=1)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        max_line_size=MAX_HEADER_BYTES,
        max_field_size=MAX_HEADER_BYTES,
    ) as session:
        result = await crawler.fetch_page(session, url)

    return result


async def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.crawler.client <base_url> [--test-url specific_url]")
        return

    if len(sys.argv) >= 4 and sys.argv[2] == "--test-url":
        specific_url = sys.argv[3]
        await test_specific_url(specific_url)
        return

    base_url = sys.argv[1]
    await crawl_for_policy_documents(base_url=base_url, max_depth=4, max_pages=200, strategy="bfs")


if __name__ == "__main__":
    asyncio.run(main())
