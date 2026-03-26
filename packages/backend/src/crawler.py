"""
Legal document crawler for extracting privacy policies, terms of service, and other legal content.
"""

import asyncio
import heapq
import json
import logging
import random
import re
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

import aiohttp
import markdownify
import tldextract
from bs4 import BeautifulSoup
from camoufox import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page, Route
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.logging import get_logger

logger = get_logger(__name__, component="crawler")
logger_robots = get_logger(__name__, component="crawler:robots")
logger_rate_limit = get_logger(__name__, component="crawler:rate_limit")
logger_fetch = get_logger(__name__, component="crawler:fetch")
logger_proxy = get_logger(__name__, component="crawler:proxy")

_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

# Standard user agent string following RFC 7231 format
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; ClauseaBot/2.0; +https://www.clausea.co/bot.html; lvndry@proton.me)"
)

ACCEPT_HEADER = (
    "text/markdown, text/html;q=0.9, text/plain;q=0.8, application/json;q=0.7, */*;q=0.5"
)


@dataclass
class StaticFetchResult:
    """Raw result from an HTTP GET before any content extraction.

    When ``blocked_by_robots_txt`` is True, the crawler did not perform the GET
    because robots.txt disallows the URL.
    """

    url: str
    status_code: int
    content_type: str
    body: str
    raw_bytes: bytes | None = None
    headers: dict[str, str] = dataclass_field(default_factory=dict)
    blocked_by_robots_txt: bool = False
    error_message: str | None = None
    cached: bool = False
    # The final URL after following HTTP redirects (301/302).  When the
    # server responds with a redirect chain, aiohttp follows it silently
    # and ``response.url`` gives the landing page.  We store it here so
    # downstream code (link extraction, deduplication) uses the correct URL.
    resolved_url: str | None = None

    def to_failed_crawl_result(self) -> "CrawlResult":
        return CrawlResult(
            url=self.url,
            title="",
            content="",
            markdown="",
            metadata={"content-type": self.content_type} if self.content_type else {},
            status_code=self.status_code,
            success=False,
            error_message=self.error_message or f"HTTP {self.status_code}",
        )


@dataclass
class PageContent:
    """Intermediate container between raw fetch and CrawlResult.

    Holds extracted text, markdown, metadata, and links before the result
    is finalised. Produced by content extraction, consumed by result building.
    """

    text: str
    markdown: str
    title: str
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)
    discovered_links: list[dict[str, str]] = dataclass_field(default_factory=list)
    status_code: int = 200


class CrawlResult(BaseModel):
    """Container for crawl results."""

    url: str = Field(description="The final URL after redirects")
    title: str = Field(description="The page title")
    content: str = Field(description="The raw text content of the page")
    markdown: str = Field(description="The content converted to Markdown format")
    metadata: dict[str, Any] = Field(
        description="Metadata extracted from the page (e.g., tags, headers)"
    )
    status_code: int = Field(description="The HTTP status code of the response")
    success: bool = Field(description="Whether the crawl was successful")
    error_message: str | None = Field(
        default=None, description="Detailed error message if crawl failed"
    )
    legal_score: float | None = Field(
        default=None,
        description="Content-based legal relevance score (0.0–1.0); None if not analyzed",
    )
    discovered_links: list[dict[str, str]] = Field(
        default_factory=list, description="List of links with both URL and original anchor text"
    )


class CrawlStats(BaseModel):
    """Crawl statistics."""

    total_urls: int = 0
    crawled_urls: int = 0
    failed_urls: int = 0
    start_time: float = Field(default_factory=time.time)

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    @property
    def crawl_rate(self) -> float:
        return self.crawled_urls / self.elapsed_time if self.elapsed_time > 0 else 0


class URLScorer:
    """Scores URLs based on legal document relevance."""

    def __init__(self) -> None:
        # Compile regex patterns once for efficiency
        self.compiled_high_value_patterns = {
            re.compile(pattern, re.IGNORECASE): weight
            for pattern, weight in {
                r"privacy-policy": 8.0,
                r"\bprivacy\s+policy\b": 8.0,
                r"\bprivacy\s+notice\b": 7.0,
                r"terms-of-service": 8.0,
                r"\bterms\s+of\s+service\b": 8.0,
                r"\bterms\s+of\s+use\b": 7.5,
                r"\bterms\s+and\s+conditions\b": 7.5,
                r"cookie-policy": 7.0,
                r"\bcookie\s+policy\b": 7.0,
                r"data-processing-addendum": 8.0,
                r"\bdata\s+processing\s+addendum\b": 8.0,
                r"subprocessors": 6.0,
                r"gdpr": 6.0,
                r"ccpa": 6.0,
            }.items()
        }

        self.compiled_path_patterns = {
            re.compile(pattern): weight
            for pattern, weight in {
                r"/legal/?": 4.0,
                r"/terms/?": 4.5,
                r"/tos/?": 4.5,
                r"/privacy/?": 5.0,
                r"/policy/?": 4.0,
                r"/policies/?": 4.0,
                r"/agreement/?": 3.5,
                r"/compliance/?": 3.5,
                r"/cookie/?": 4.0,
                r"/gdpr/?": 4.5,
                r"/ccpa/?": 4.5,
                r"/data-processing/?": 4.0,
                r"/security/?": 3.0,
                r"/disclaimer/?": 3.0,
                r"/company/?": 3.0,
                r"/data-processing-addendum/?": 5.0,
                r"/dpa/?": 5.0,
                r"/addendum/?": 4.5,
                r"/subprocessors/?": 4.0,
                r"/vendors/?": 3.0,
                r"/suppliers/?": 3.0,
                r"/transparency/?": 3.5,
                r"/[a-f0-9-]{32,}": 2.0,
                r"/company/legal/?": 5.0,
                r"/company/privacy/?": 5.0,
                r"/company/terms/?": 5.0,
                r"/company/tos/?": 5.0,
                r"/about/legal/?": 4.5,
                r"/about/privacy/?": 4.5,
                r"/about/terms/?": 4.5,
                r"/about/tos/?": 4.5,
                r"/support/legal/?": 4.0,
                r"/support/privacy/?": 4.0,
                r"/support/terms/?": 4.0,
                r"/help/legal/?": 4.0,
                r"/help/privacy/?": 4.0,
                r"/help/terms/?": 4.0,
                r"/policies/privacy/?": 5.0,
                r"/policies/terms/?": 5.0,
                r"/policies/cookies/?": 4.5,
                r"/legal/policies/?": 5.0,
                r"/legal/policies/privacy/?": 5.0,
                r"/legal/policies/terms/?": 5.0,
                r"/legal/policies/cookies/?": 4.5,
            }.items()
        }

        # Compile word extraction pattern once
        self.word_pattern = re.compile(r"\b\w+\b")

        self.legal_keywords = {
            # Generic legal terms
            "legal": 3.5,
            "terms": 4.0,
            "privacy": 5.0,
            "policy": 4.0,
            "agreement": 3.5,
            "conditions": 3.5,
            "disclaimer": 3.0,
            "notice": 2.5,
            "consent": 3.0,
            "rights": 2.5,
            "compliance": 3.0,
            "trust": 2.0,
            "rules": 2.5,
            "license": 3.0,
            # Specific document types
            "privacy-policy": 5.0,
            "terms-of-service": 5.0,
            "terms-and-conditions": 5.0,
            "terms-of-use": 5.0,
            "cookie-policy": 4.5,
            "cookie": 3.5,
            "cookies": 3.5,
            # Data and processing
            "data": 3.0,
            "processor": 3.5,
            "subprocessor": 3.5,
            "partners": 2.0,
            "processing": 3.0,
            "protection": 3.5,
            "addendum": 4.5,  # Added for DPAs
            "dpa": 5.0,  # Data Processing Agreement
            "subprocessors": 3.5,
            # Regional and compliance
            "gdpr": 4.0,
            "ccpa": 4.0,
            "hipaa": 4.0,
            "coppa": 4.0,
            "pipeda": 4.0,
            # Security and safety
            "security": 3.0,
            "safety": 3.0,
            "copyright": 3.0,
            "dmca": 3.5,
            # Additional legal terms
            "vendor": 2.5,
            "suppliers": 2.5,
            "associate": 2.0,
            "transparency": 3.0,
            "report": 2.0,
            "company": 1.0,
            # Negative keywords (reduce score)
            # NOTE: Only penalise paths that are genuinely unlikely to host
            # legal content.  Paths like /help, /support, /about and /blog
            # are neutral — many companies publish legal documents under these
            # sections (e.g. Airbnb ToS at /help/article/2908).
            "contact": -1.0,
            "news": -1.0,
        }

    @lru_cache(maxsize=10000)  # noqa: B019 - Cache is bounded and per-instance
    def score_url(self, url: str, anchor_text: str | None = None) -> float:
        """
        Score a URL based on legal document relevance.

        Uses LRU cache to avoid recomputing scores for the same URLs.
        Lowercases URL once and reuses for all pattern matching.
        """
        # Lowercase once and reuse
        url_lower = url.lower()
        parsed = urlparse(url_lower)
        path = parsed.path

        score = 0.0

        # Check high-value patterns in URL using compiled regex
        for pattern, weight in self.compiled_high_value_patterns.items():
            if pattern.search(url_lower):
                score += weight

        # Score based on anchor text if provided.
        # Anchor text is what the *linking page* calls the target — often the
        # strongest signal we have, especially when the URL is opaque
        # (e.g. /help/article/2908 for "Terms of Service").
        if anchor_text:
            anchor_lower = anchor_text.lower()
            anchor_words = self.word_pattern.findall(anchor_lower)

            # Phrase matches are the highest-confidence anchor signal
            for pattern, weight in self.compiled_high_value_patterns.items():
                if pattern.search(anchor_lower):
                    score += weight * 2.5

            # Individual keyword matches
            for word in anchor_words:
                if word in self.legal_keywords:
                    score += self.legal_keywords[word] * 2.0

        # Score based on path patterns using compiled regex
        for pattern, weight in self.compiled_path_patterns.items():
            if pattern.search(path):
                score += weight

        # Score based on keywords in URL
        url_text = (
            f"{path} {parsed.query} {parsed.fragment}".replace("/", " ")
            .replace("-", " ")
            .replace("_", " ")
        )
        words = self.word_pattern.findall(url_text)

        # Track which keywords we've already scored to avoid double-counting
        scored_keywords = set()

        for word in words:
            if word in self.legal_keywords:
                score += self.legal_keywords[word]
                scored_keywords.add(word.lower())

        # Check for legal keywords as substrings in path and words
        # This catches cases where legal keywords are embedded in compound words
        path_lower = path.lower()
        for keyword, weight in self.legal_keywords.items():
            # Only check positive-weight keywords (skip negative ones like "blog")
            if weight > 0 and keyword not in scored_keywords:
                # Check if keyword appears as substring in path
                # If it's not in scored_keywords, it means it wasn't an exact word match
                if keyword in path_lower:
                    # It's a substring match (like "privacy" in "safetyandprivacy")
                    score += weight * 0.8  # Slightly lower weight for substring matches
                    scored_keywords.add(keyword)
                # Also check in extracted words for compound words
                for word in words:
                    word_lower = word.lower()
                    if (
                        keyword in word_lower
                        and word_lower != keyword
                        and keyword not in scored_keywords
                    ):
                        score += weight * 0.8
                        scored_keywords.add(keyword)

        return max(0.0, score)


class ContentAnalyzer:
    """Analyzes page content for legal document characteristics."""

    def __init__(self) -> None:
        self.compiled_legal_phrases = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"by using (?:this|our) (?:service|website|platform)",
                r"you agree to (?:these|our) terms",
                r"we (?:collect|process|use) your (?:personal )?(?:data|information)",
                r"this policy (?:describes|explains) how we",
                r"we may (?:update|modify|change) this policy",
                r"your (?:privacy|data|personal information) is important",
                r"we are committed to protecting your privacy",
                r"cookies (?:are|help us)",
                r"you have the right to",
                r"data retention period",
                r"lawful basis for processing",
                r"data processing addendum",
                r"this addendum (?:forms|supplements|amends)",
                r"subprocessor(?:s)? (?:list|agreement)",
                r"we (?:engage|use) (?:third.party|sub.?processor)",
                r"processing (?:activities|operations|purposes)",
                r"data subject (?:rights|requests)",
                r"cross.border (?:transfer|data transfer)",
                r"adequacy decision",
                r"standard contractual clauses",
                r"security (?:measures|safeguards|controls)",
                r"data (?:breach|incident) (?:notification|response)",
                r"controller (?:and|to) processor",
                r"processor (?:instructions|obligations)",
            ]
        ]

        # Quick check pattern for early exit (compiled once)
        # This pattern matches common legal keywords for fast filtering
        self.quick_check_pattern = re.compile(
            r"\b(?:privacy|terms|policy|agreement|legal|gdpr|ccpa|cookie|data protection|"
            r"liability|disclaimer|jurisdiction|compliance|consent|rights)\b",
            re.IGNORECASE,
        )

        self.legal_indicators = [
            "terms of service",
            "privacy policy",
            "cookie policy",
            "data protection",
            "personal information",
            "third parties",
            "we collect",
            "your rights",
            "lawful basis",
            "consent",
            "legitimate interest",
            "data controller",
            "data processor",
            "retention period",
            "delete your data",
            "opt out",
            "agreement",
            "binding",
            "governing law",
            "jurisdiction",
            "liability",
            "disclaimer",
            "limitation of liability",
            "indemnification",
            "intellectual property",
            "copyright",
            "trademark",
            "infringement",
            "compliance",
            "regulatory",
            "gdpr",
            "ccpa",
            "hipaa",
            "coppa",
            # Enhanced indicators for DPAs and similar documents
            "data processing addendum",
            "dpa",
            "subprocessor",
            "subprocessors",
            "sub-processor",
            "sub-processors",
            "vendor",
            "suppliers",
            "third party service provider",
            "service provider",
            "data transfer",
            "international transfer",
            "adequacy decision",
            "standard contractual clauses",
            "scc",
            "binding corporate rules",
            "bcr",
            "data subject rights",
            "data security",
            "data breach",
            "processing activities",
            "personal data",
            "special categories",
            "sensitive data",
            "transparency report",
        ]

        # Title keywords for bonus scoring (used in multiple places)
        self.title_keywords = [
            "terms",
            "privacy",
            "policy",
            "cookie",
            "legal",
            "agreement",
            "data",
            "gdpr",
        ]

    def analyze_content(
        self, content: str, title: str = "", metadata: dict[str, Any] | None = None
    ) -> tuple[bool, float, list[str]]:
        """
        Analyze content to determine if it's a legal document.

        Returns:
            Tuple of (is_legal, confidence_score, matched_indicators)
        """
        if not content:
            return False, 0.0, []

        # Calculate content metrics first (needed for early exit)
        word_count = len(content.split())
        char_count = len(content)

        # Minimum content thresholds to avoid tiny snippets
        if word_count < 50 or char_count < 300:
            return False, 0.0, ["content_too_short"]

        # Early exit: Quick check for obvious non-legal content
        # This avoids expensive full analysis for clearly non-legal documents
        if not self.quick_check_pattern.search(content):
            # No legal keywords found at all - very unlikely to be legal
            return False, 0.0, ["no_legal_keywords"]

        # Now do full analysis (only if quick check passed)
        content_lower = content.lower()
        title_lower = title.lower() if title else ""

        matched_indicators = []
        raw_score = 0.0

        # Track matched content for density calculation
        matched_content_chars = 0

        # Check for legal indicators in content
        for indicator in self.legal_indicators:
            if indicator in content_lower:
                matched_indicators.append(indicator)
                raw_score += 1.0
                # Add to matched content length (count occurrences)
                matched_content_chars += len(indicator) * content_lower.count(indicator)

        # Check for legal phrases using compiled regex patterns
        for compiled_pattern in self.compiled_legal_phrases:
            matches = compiled_pattern.finditer(content_lower)
            for match in matches:
                # Store pattern string for debugging (get from original pattern if needed)
                matched_indicators.append(compiled_pattern.pattern)
                raw_score += 2.0
                matched_content_chars += len(match.group())

        # Calculate legal content density
        legal_density = matched_content_chars / char_count

        # Bonus for legal terms in title (more important)
        title_bonus = 0.0
        for keyword in self.title_keywords:
            if keyword in title_lower:
                title_bonus += 3.0
                matched_indicators.append(f"title:{keyword}")

        # Check metadata
        metadata_bonus = 0.0
        if metadata:
            meta_title = metadata.get("title", "").lower()
            meta_description = metadata.get("description", "").lower()

            for text in [meta_title, meta_description]:
                for keyword in self.title_keywords:
                    if keyword in text:
                        metadata_bonus += 1.0

        # Combined scoring with density weighting
        base_score = raw_score * legal_density * 100  # Scale density
        final_score = base_score + title_bonus + metadata_bonus

        # Normalize to 0-10 scale
        normalized_score = min(10.0, final_score)

        # More sophisticated thresholds
        min_density_threshold = 0.05  # At least 5% of content should be legal-related
        min_score_threshold = 2.0

        # Document is legal if:
        # 1. Has sufficient legal density (5%+)
        # 2. Meets minimum score threshold
        # 3. OR has strong title indicators (overrides density for short legal docs)
        is_legal = (
            (legal_density >= min_density_threshold and normalized_score >= min_score_threshold)
            or title_bonus >= 6.0  # Strong title indicators
        )

        # Add density information to indicators for debugging
        matched_indicators.append(f"density:{legal_density:.3f}")
        matched_indicators.append(f"word_count:{word_count}")

        return is_legal, normalized_score, matched_indicators


class DomainRateLimiter:
    """Per-domain rate limiter for efficient concurrent crawling."""

    def __init__(self, delay_between_requests: float = 1.0, jitter: float = 0.0) -> None:
        """
        Initialize the domain rate limiter.

        Args:
            delay_between_requests: Minimum delay between requests to the same domain in seconds
            jitter: Randomized jitter to add to the delay (0.0 to 1.0)
        """
        self.delay_between_requests = delay_between_requests
        self.jitter = jitter
        self.domain_locks: dict[str, asyncio.Lock] = {}
        self.domain_last_request: dict[str, float] = {}
        self.lock = asyncio.Lock()  # Protects domain_locks and domain_last_request dicts

    def _normalize_domain(self, url: str) -> str:
        """Extract and normalize domain from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www prefix for consistency
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    async def rate_limit(self, url: str) -> None:
        """
        Apply rate limiting per domain.

        Different domains can be crawled concurrently, but requests to the same
        domain are rate-limited according to delay_between_requests.

        Args:
            url: The URL being requested
        """
        domain = self._normalize_domain(url)

        # Get or create lock for this domain
        async with self.lock:
            if domain not in self.domain_locks:
                self.domain_locks[domain] = asyncio.Lock()
                self.domain_last_request[domain] = 0.0

        domain_lock = self.domain_locks[domain]

        # Apply rate limiting for this specific domain
        async with domain_lock:
            last_time = self.domain_last_request[domain]
            elapsed = time.time() - last_time

            if elapsed < self.delay_between_requests:
                base_sleep = self.delay_between_requests - elapsed

                # Add randomized jitter if configured
                if self.jitter > 0:
                    # random.uniform ensures the delay varies around the target
                    jitter_amt = random.uniform(-self.jitter, self.jitter)
                    sleep_time = max(0, base_sleep + jitter_amt)

                    if sleep_time > 0:
                        logger_rate_limit.debug(
                            f"rate limiting domain '{domain}': sleeping {sleep_time:.2f}s (base: {base_sleep:.2f}s, jitter: {jitter_amt:+.2f}s)"
                        )
                        await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(base_sleep)

            self.domain_last_request[domain] = time.time()

    def clear_cache(self) -> None:
        """
        Clear the rate limiter cache (useful for long-running processes).

        This is a synchronous method that clears the cache. For thread-safety,
        it should ideally be called when no requests are in progress.
        """
        # Clear the dictionaries (this is safe if no concurrent access)
        # In practice, this should be called between crawl sessions
        self.domain_locks.clear()
        self.domain_last_request.clear()


class RobotsTxtChecker:
    """Checks robots.txt compliance with improved parsing."""

    def __init__(self, max_cache_size: int = 1000) -> None:
        """
        Initialize the robots.txt checker.

        Args:
            max_cache_size: Maximum number of robots.txt files to cache (LRU eviction)
        """
        self.robots_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max_cache_size = max_cache_size
        self.user_agent = DEFAULT_USER_AGENT
        # Common user agent patterns that should be treated as wildcards
        self.user_agent_patterns = [
            "*",  # Standard wildcard
            "all",  # Common alias
            "any",  # Common alias
            "bot",  # Generic bot identifier
            "crawler",  # Generic crawler identifier
            "spider",  # Generic spider identifier
            "robot",  # Generic robot identifier
            "crawl",  # Common prefix
            "spider",  # Common prefix
            "bot",  # Common suffix
        ]

    async def can_fetch(self, session: aiohttp.ClientSession, url: str) -> tuple[bool, str]:
        """Check if URL can be fetched according to robots.txt."""
        try:
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            robots_url = f"{base_url}/robots.txt"

            if base_url not in self.robots_cache:
                try:
                    # Fetch robots.txt content directly
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with session.get(robots_url, timeout=timeout) as response:
                        if response.status == 200:
                            robots_content = await response.text()
                            logger_robots.debug(f"fetched robots.txt from {robots_url}")
                            parsed_rules = self._parse_robots_txt(robots_content)
                        else:
                            logger_robots.debug(
                                f"robots.txt not found at {robots_url} (status: {response.status}); allowing all requests"
                            )
                            # If we can't fetch robots.txt, allow all
                            parsed_rules = {"allow_all": True}
                except Exception as e:
                    logger_robots.debug(
                        f"error fetching robots.txt from {robots_url}: {e}; allowing all requests"
                    )
                    # If we can't fetch robots.txt, allow all
                    parsed_rules = {"allow_all": True}

                # Add to cache with LRU eviction
                self._add_to_cache(base_url, parsed_rules)

            robots_rules = self.robots_cache.pop(base_url)
            self.robots_cache[base_url] = robots_rules
            if robots_rules.get("allow_all", False):
                logger_robots.debug(
                    f"no robots.txt rules found for {base_url}; allowing all access"
                )
                return True, "No robots.txt rules found"

            # Sitemap directives are stored on robots_rules for callers; they must not
            # bypass Allow/Disallow — always apply URL rules.
            return self._check_url_allowed(url, robots_rules)

        except Exception as e:
            logger_robots.warning(f"error checking robots.txt for {url}: {e}")
            return True, f"Error checking robots.txt: {str(e)}"

    def _add_to_cache(self, base_url: str, rules: dict[str, Any]) -> None:
        """Add robots.txt rules to cache with LRU eviction."""
        # Remove oldest entry if cache is full
        if len(self.robots_cache) >= self.max_cache_size:
            # Remove least recently used (first item in OrderedDict)
            self.robots_cache.popitem(last=False)
        # Add new entry (will be at end, most recently used)
        self.robots_cache[base_url] = rules

    def clear_cache(self) -> None:
        """Clear the robots.txt cache (useful between crawl sessions)."""
        self.robots_cache.clear()

    def _parse_robots_txt(self, content: str) -> dict[str, Any]:
        """Parse robots.txt content into rules following the standard format.

        This parser also collects `Sitemap:` directives and returns them under
        the `sitemaps` key in the returned dict if present.
        """
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        logger_robots.debug(f"parsing robots.txt: {len(lines)} directive lines")

        user_agents: dict[str, dict[str, Any]] = {}
        current_user_agent = None

        for line in lines:
            # Skip comments and empty lines
            if line.startswith("#") or not line:
                continue

            # Handle line continuation
            if line.startswith(" ") or line.startswith("\t"):
                if current_user_agent:
                    # Append to the last rule
                    last_rule_type = list(user_agents[current_user_agent].keys())[-1]
                    user_agents[current_user_agent][last_rule_type][-1] += line.strip()
                continue

            # Parse directive
            if ":" in line:
                directive, value = line.split(":", 1)
                directive = directive.strip().lower()
                value = value.strip()

                if directive == "user-agent":
                    current_user_agent = value.lower()
                    if current_user_agent not in user_agents:
                        user_agents[current_user_agent] = {"disallow": [], "allow": []}
                    logger_robots.debug(f"found user-agent directive: {current_user_agent}")
                elif directive == "disallow" and current_user_agent:
                    if value:  # Only add non-empty disallow rules
                        user_agents[current_user_agent]["disallow"].append(value)
                        logger_robots.debug(
                            f"added disallow rule for {current_user_agent}: {value}"
                        )
                elif directive == "allow" and current_user_agent:
                    user_agents[current_user_agent]["allow"].append(value)
                    logger_robots.debug(f"added allow rule for {current_user_agent}: {value}")
                elif directive == "crawl-delay" and current_user_agent:
                    # Store crawl delay for rate limiting
                    try:
                        delay = float(value)
                        user_agents[current_user_agent]["crawl_delay"] = delay
                        logger_robots.debug(f"added crawl-delay for {current_user_agent}: {delay}s")
                    except ValueError:
                        logger_robots.warning(f"invalid crawl-delay value in robots.txt: {value}")
                elif directive == "sitemap":
                    # Record sitemap directives for later discovery
                    if "sitemaps" not in locals():
                        sitemaps: list[str] = []
                    sitemaps.append(value)
                    logger_robots.debug(f"found sitemap directive: {value}")

        # Return user agent rules and sitemaps (if any were found via directives)
        parsed: dict[str, Any] = {"user_agents": user_agents}
        if "sitemaps" in locals():
            parsed["sitemaps"] = sitemaps
        return parsed

    def _check_url_allowed(self, url: str, robots_rules: dict[str, Any]) -> tuple[bool, str]:
        """Check if URL is allowed based on parsed robots.txt rules."""
        parsed = urlparse(url)
        path = parsed.path
        if not path:
            path = "/"

        user_agents = robots_rules.get("user_agents", {})
        logger_robots.debug(f"checking robots.txt rules for path: {path}")

        # Find applicable rules by checking user agent patterns
        applicable_rules = None
        matched_user_agent = None
        user_agent_lower = self.user_agent.lower()

        # First check exact match (full User-Agent string)
        if user_agent_lower in user_agents:
            applicable_rules = user_agents[user_agent_lower]
            matched_user_agent = user_agent_lower
            logger_robots.debug(f"found exact user-agent match: {user_agent_lower}")
        # Then check if any robots.txt User-agent token is our bot name (e.g. "ClauseaBot")
        elif matching := [
            ua
            for ua in user_agents
            if ua in user_agent_lower and ua not in self.user_agent_patterns
        ]:
            # Prefer longest matching token (most specific)
            best = max(matching, key=len)
            applicable_rules = user_agents[best]
            matched_user_agent = best
            logger_robots.debug(f"found bot-name user-agent match: {best}")
        # Then check wildcard patterns
        else:
            for pattern in self.user_agent_patterns:
                if pattern in user_agents:
                    applicable_rules = user_agents[pattern]
                    matched_user_agent = pattern
                    logger_robots.debug(f"found wildcard user-agent match: {pattern}")
                    break

        # If robots_rules include sitemaps (collected during parsing), attach for callers
        sitemaps = robots_rules.get("sitemaps")
        if sitemaps:
            logger_robots.debug(f"robots.txt contains {len(sitemaps)} sitemap directive(s)")

        # If no rules found, allow by default
        if not applicable_rules:
            return True, "No matching rules found"

        logger_robots.debug(f"applying rules for user-agent: {matched_user_agent}")

        # Check allow rules first (most specific wins)
        for allow_pattern in applicable_rules.get("allow", []):
            if self._path_matches_pattern(path, allow_pattern):
                logger_robots.debug(f"URL allowed by allow pattern: {allow_pattern}")
                return True, f"Explicitly allowed by pattern: {allow_pattern}"

        # Then check disallow rules
        for disallow_pattern in applicable_rules.get("disallow", []):
            if self._path_matches_pattern(path, disallow_pattern):
                # If we have a matching disallow rule, check if there's a more specific allow rule
                for allow_pattern in applicable_rules.get("allow", []):
                    if self._path_matches_pattern(path, allow_pattern) and len(allow_pattern) > len(
                        disallow_pattern
                    ):
                        logger_robots.debug(
                            f"URL allowed by more specific allow pattern: {allow_pattern} (overrides disallow: {disallow_pattern})"
                        )
                        return (
                            True,
                            f"Allowed by more specific pattern: {allow_pattern}",
                        )
                return False, f"Blocked by pattern: {disallow_pattern}"

        # If we have disallow rules but no match, the path is allowed
        # (Disallow creates a blacklist, not a whitelist)
        if applicable_rules.get("disallow"):
            # No matching disallow rule found, so path is allowed
            return True, "No matching disallow rules"

        # No rules or only allow rules - default is to allow
        return True, "No blocking rules found"

    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches robots.txt pattern following standard rules."""
        if not pattern:
            return False
        if pattern == "/":
            return True  # Allow: / means allow everything

        # Handle wildcards
        if "*" in pattern:
            # Convert pattern to regex
            regex_pattern = pattern.replace(".", "\\.").replace("*", ".*")
            return bool(re.match(f"^{regex_pattern}$", path))

        # Handle trailing wildcard
        if pattern.endswith("*"):
            return path.startswith(pattern[:-1])

        # Handle leading wildcard
        if pattern.startswith("*"):
            return path.endswith(pattern[1:])

        # Exact match
        return path.startswith(pattern)


class HTTPCache:
    """
    HTTP response cache for ETag and Last-Modified headers.

    Implements conditional requests using If-None-Match (ETag) and
    If-Modified-Since (Last-Modified) headers to avoid re-downloading
    unchanged content.
    """

    def __init__(self, max_cache_size: int = 10000):
        """
        Initialize the HTTP cache.

        Args:
            max_cache_size: Maximum number of URLs to cache (LRU eviction)
        """
        self.cache: OrderedDict[str, dict[str, str]] = OrderedDict()
        self.max_cache_size = max_cache_size

    def get_cache_headers(self, url: str) -> dict[str, str]:
        """
        Get cache headers (If-None-Match, If-Modified-Since) for a URL.

        Args:
            url: The URL to get cache headers for

        Returns:
            Dictionary with cache headers, empty if URL not in cache
        """
        if url not in self.cache:
            return {}

        cache_entry = self.cache[url]
        headers = {}

        if "etag" in cache_entry:
            headers["If-None-Match"] = cache_entry["etag"]

        if "last_modified" in cache_entry:
            headers["If-Modified-Since"] = cache_entry["last_modified"]

        return headers

    def update_cache(self, url: str, response: aiohttp.ClientResponse) -> None:
        """
        Update cache with ETag and Last-Modified from response headers.

        Args:
            url: The URL that was requested
            response: The HTTP response
        """
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")

        # Only cache if we have at least one cache header
        if not etag and not last_modified:
            return

        # Remove oldest entry if cache is full
        if len(self.cache) >= self.max_cache_size:
            self.cache.popitem(last=False)

        cache_entry: dict[str, str] = {}
        if etag:
            cache_entry["etag"] = etag
        if last_modified:
            cache_entry["last_modified"] = last_modified

        # Remove from cache if exists (to move to end for LRU)
        if url in self.cache:
            del self.cache[url]

        # Add to end (most recently used)
        self.cache[url] = cache_entry

    def clear_cache(self) -> None:
        """Clear the HTTP cache (useful between crawl sessions)."""
        self.cache.clear()

    def remove_from_cache(self, url: str) -> None:
        """Remove a specific URL from cache."""
        if url in self.cache:
            del self.cache[url]


class AsyncFileLogHandler(logging.Handler):
    """Async logging handler that writes to file in a thread pool (fire-and-forget)."""

    def __init__(self, file_handler: logging.FileHandler, executor: ThreadPoolExecutor):
        super().__init__()
        self.file_handler = file_handler
        self.executor = executor
        self._shutdown = False  # Track if executor is shut down

    def set_shutdown(self, shutdown: bool = True) -> None:
        """Mark handler as shut down to prevent new submissions."""
        self._shutdown = shutdown

    def emit(self, record: logging.LogRecord) -> None:
        """Write log record to file in thread pool without blocking."""
        # Silently ignore if executor is shut down
        if self._shutdown:
            return

        try:
            # Submit file write to thread pool - truly fire-and-forget
            # This doesn't block the calling thread at all
            self.executor.submit(self.file_handler.emit, record)
        except RuntimeError as e:
            # Executor is shut down - silently ignore to prevent logging loops
            if "cannot schedule new futures after shutdown" in str(e):
                self._shutdown = True
                return
            # Re-raise other RuntimeErrors
            raise
        except Exception:
            # Ignore any other errors to prevent logging from breaking the crawler
            # Don't call handleError to avoid potential logging loops
            pass


class ClauseaCrawler:
    """Powerful legal document crawler."""

    def __init__(
        self,
        max_depth: int = 5,
        max_pages: int = 1000,
        max_concurrent: int = 10,
        delay_between_requests: float = 1.0,
        timeout: int = 60,
        allowed_domains: list[str] | None = None,
        respect_robots_txt: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        follow_external_links: bool = False,
        follow_nofollow: bool = False,  # Whether to follow links marked rel="nofollow"
        respect_meta_robots: bool = True,  # Respect <meta name="robots" content="nofollow"> on pages
        min_legal_score: float = 2.0,
        strategy: str = "bfs",  # "bfs", "dfs", "best_first"
        ignore_robots_for_domains: list[str]
        | None = None,  # List of domains to ignore robots.txt for
        max_retries: int = 3,  # Maximum retry attempts for transient errors
        log_file_path: str | None = None,  # Optional path to log file for crawl session
        use_browser: bool = False,  # Whether to use a headless browser for dynamic rendering
        proxy: str | None = None,  # Optional proxy URL (e.g., "http://user:pass@host:port")
        allowed_paths: list[str] | None = None,  # Optional list of allowed path regexes
        denied_paths: list[str] | None = None,  # Optional list of denied path regexes
        delay_jitter: float = 0.0,  # Randomized jitter to add to the delay (0.0 to 1.0)
        # Opt-in binary crawling and parser preferences
        enable_binary_crawling: bool = False,
        use_tika_for_binaries: bool = False,
        use_pdfminer_for_pdf: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,  # Optional progress callback
    ):
        """
        Initialize the ClauseaCrawler.

        Args:
            max_depth: Maximum crawl depth
            max_pages: Maximum number of pages to crawl
            max_concurrent: Maximum concurrent requests
            delay_between_requests: Delay between requests in seconds
            timeout: Request timeout in seconds
            allowed_domains: List of allowed domains (None = allow all)
            respect_robots_txt: Whether to respect robots.txt
            user_agent: User agent string
            follow_external_links: Whether to follow external links
            min_legal_score: Minimum score to consider a URL legal-relevant
            strategy: Crawling strategy ("bfs", "dfs", "best_first")
            ignore_robots_for_domains: List of domains to ignore robots.txt for
            max_retries: Maximum retry attempts for transient network errors (default: 3)
            log_file_path: Optional path to log file for crawl session (e.g., "logs/20240101_123456_companyid_crawl.log")
            use_browser: Whether to use a headless browser for dynamic rendering
            proxy: Optional proxy URL
        """
        self.max_depth = max_depth
        self.max_pages = max_pages
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
        self.proxy = proxy
        self.allowed_paths = allowed_paths
        self.denied_paths = denied_paths

        # Opt-in: whether to fetch and parse binary documents (PDF/Office)
        self.enable_binary_crawling = enable_binary_crawling
        # Optional parsing strategies (these are hints; the processor will attempt them if available)
        self.use_tika_for_binaries = use_tika_for_binaries
        self.use_pdfminer_for_pdf = use_pdfminer_for_pdf

        # Progress callback for external monitoring
        self.progress_callback = progress_callback

        # Compile path patterns
        self.compiled_allowed_paths = (
            [re.compile(p) for p in allowed_paths] if allowed_paths else []
        )
        self.compiled_denied_paths = [re.compile(p) for p in denied_paths] if denied_paths else []

        # Components
        self.url_scorer = URLScorer()
        self.content_analyzer = ContentAnalyzer()
        self.robots_checker = RobotsTxtChecker(max_cache_size=1000) if respect_robots_txt else None
        self.http_cache = HTTPCache(
            max_cache_size=10000
        )  # HTTP response cache for ETag/Last-Modified

        # Set up file logging if log_file_path is provided
        self.file_handler: logging.FileHandler | None = None
        self._async_handler: AsyncFileLogHandler | None = None
        self._log_executor: ThreadPoolExecutor | None = None
        if self.log_file_path:
            self._setup_file_logging()

        # Browser state
        self.browser_instance: AsyncCamoufox | None = None
        self.browser_context: Browser | BrowserContext | None = None
        self.browser_lock = asyncio.Lock()

        # State
        self.visited_urls: set[str] = set()
        self.failed_urls: set[str] = set()
        self.queued_urls: set[str] = set()  # Prevents duplicate queue entries
        self.url_queue: deque[tuple[str, int]] = deque()  # For BFS
        self.url_stack: list[tuple[str, int]] = []  # For DFS
        self.url_priority_queue: list[tuple[float, str, int]] = []  # For best-first (scored URLs)
        self._sitemap_seeded: bool = False  # True when sitemaps provided seed URLs
        self.results: list[CrawlResult] = []
        self.stats = CrawlStats()

        # Per-domain rate limiting (allows concurrent requests to different domains)
        self.rate_limiter = DomainRateLimiter(
            delay_between_requests=delay_between_requests, jitter=self.delay_jitter
        )

        # Compile skip patterns once for efficiency
        # PDFs are optionally crawlable via `enable_binary_crawling`.
        # Note: We allow plain XML files (sitemaps, RSS) as they can be parsed for links
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
                r"#",  # Skip anchor links
                r"mailto:",
                r"tel:",
                r"javascript:",
                r"/search\?",
                r"/api/",
                r"/ajax/",
                # Skip compressed files and archives (we can't easily parse these)
                r"\.(gz|zip|tar|bz2|7z|rar|xz)$",
                # Skip common binary/media files
                r"\.(mp4|mp3|avi|mov|wmv|flv|wav|ogg|webm)$",
                # Skip document formats we don't support
                r"\.(doc|docx|xls|xlsx|ppt|pptx)$",
            ]
        ]

    def _setup_file_logging(self) -> None:
        """Set up file logging for the crawl session with fire-and-forget thread pool pattern."""
        if not self.log_file_path:
            return

        try:
            # Ensure the directory exists
            log_path = Path(self.log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Create file handler with append mode
            self.file_handler = logging.FileHandler(self.log_file_path, mode="a", encoding="utf-8")
            self.file_handler.setLevel(logging.DEBUG)

            # Use a simple format for file logging (more readable than JSON)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            self.file_handler.setFormatter(formatter)

            # Create thread pool executor for fire-and-forget file writes
            # Single thread is sufficient for sequential file writes
            self._log_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="log-writer")

            # Create async handler that writes in thread pool
            self._async_handler = AsyncFileLogHandler(self.file_handler, self._log_executor)
            self._async_handler.setLevel(logging.DEBUG)
            self._async_handler.setFormatter(formatter)

            # Add handler to the root logger (structlog uses standard logging underneath)
            root_logger = logging.getLogger()
            root_logger.addHandler(self._async_handler)

            logger.info(f"📝 File logging enabled (async): {self.log_file_path}")
        except Exception as e:
            logger.warning(f"Failed to set up file logging: {e}")

    async def _shutdown_log_executor(self) -> None:
        """Shutdown the log executor and wait for pending writes to complete."""
        # Mark handler as shut down first to prevent new log submissions
        if self._async_handler:
            try:
                self._async_handler.set_shutdown(True)
            except Exception:
                pass

        if self._log_executor:
            # Shutdown executor and wait for pending tasks to complete
            # Use asyncio.to_thread to avoid blocking the event loop
            await asyncio.to_thread(self._log_executor.shutdown, wait=True)

    def _cleanup_file_logging(self) -> None:
        """Clean up file logging handler. Safe to call multiple times."""
        root_logger = logging.getLogger()

        # Mark handler as shut down FIRST to prevent new log submissions
        if self._async_handler:
            try:
                self._async_handler.set_shutdown(True)
            except Exception:
                pass

        # Remove async handler from logger BEFORE shutting down executor
        # This prevents new log records from reaching the handler
        if self._async_handler:
            try:
                if self._async_handler in root_logger.handlers:
                    root_logger.removeHandler(self._async_handler)
            except Exception as e:
                logger.warning(f"Error removing async handler: {e}")
            finally:
                self._async_handler = None

        # Shutdown executor if it exists (after handler is removed)
        if self._log_executor:
            try:
                self._log_executor.shutdown(wait=False)  # Don't wait in sync cleanup
            except Exception as e:
                logger.warning(f"Error shutting down log executor: {e}")
            finally:
                self._log_executor = None

        # Close file handler if it exists
        if self.file_handler:
            try:
                if self.file_handler in root_logger.handlers:
                    root_logger.removeHandler(self.file_handler)
                self.file_handler.close()
                if self.log_file_path:
                    logger.info(f"📝 File logging closed: {self.log_file_path}")
            except Exception as e:
                logger.warning(f"Error closing file handler: {e}")
            finally:
                self.file_handler = None

    async def _setup_browser(self) -> tuple[AsyncCamoufox, Browser | BrowserContext]:
        """Initialize and return a Camoufox browser and context."""
        async with self.browser_lock:
            if self.browser_instance is None:
                # Prepare Camoufox initialization arguments
                init_kwargs: dict[str, Any] = {
                    "headless": True,
                }

                if self.proxy:
                    # Camoufox supports proxy configuration directly
                    init_kwargs["proxy"] = {"server": self.proxy}

                # __aenter__ launches Firefox, stores the result in self.browser, and
                # returns it. We capture the return value as browser_context.
                logger.debug("Launching Camoufox browser with kwargs: %s", init_kwargs)
                try:
                    self.browser_instance = AsyncCamoufox(**init_kwargs)
                    self.browser_context = await self.browser_instance.__aenter__()
                    logger.debug(
                        "Camoufox browser launched successfully: context=%r", self.browser_context
                    )
                except Exception:
                    logger.error(
                        "Camoufox browser failed to start",
                        exc_info=True,
                    )
                    self.browser_instance = None
                    raise

            if self.browser_context is None:
                raise RuntimeError(
                    "Camoufox browser failed to initialize: __aenter__ returned None"
                )

            return self.browser_instance, self.browser_context

    async def _cleanup_browser(self) -> None:
        """Clean up Camoufox resources."""
        async with self.browser_lock:
            if self.browser_instance:
                try:
                    await self.browser_instance.__aexit__(None, None, None)
                except Exception:
                    logger.warning("Error while closing Camoufox browser", exc_info=True)
                finally:
                    # Always null out state so the next call to _setup_browser
                    # reinitialises instead of reusing a dead instance.
                    self.browser_instance = None
                    self.browser_context = None
                logger.debug("Camoufox browser closed")

    @staticmethod
    def _is_garbled_content(text: str, *, sample_size: int = 1024) -> bool:
        """Detect garbled/binary content that slipped through as text.

        Checks the ratio of non-printable / unusual characters in a sample.
        Returns True when the text is likely compressed, encoded, or binary data
        that was incorrectly decoded as a string (common with JS-heavy SPAs that
        inline binary bundles).
        """
        if not text or len(text) < 100:
            return False

        sample = text[:sample_size]
        non_text_chars = sum(
            1 for ch in sample if not ch.isprintable() and ch not in ("\n", "\r", "\t")
        )
        ratio = non_text_chars / len(sample)
        if ratio > 0.08:
            return True

        # Also flag content with extremely high density of non-ASCII (e.g. encoded blobs)
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

    def _content_is_sufficient(self, page: PageContent, url: str) -> bool:
        """Decide whether the statically-fetched content is good enough to keep.

        If this returns False and ``use_browser`` is enabled the caller should
        retry with the headless browser.

        High URL legal-relevance scores use a higher minimum length so thin
        static HTML (common for SPAs) still triggers a browser retry.
        """
        text = page.text or ""
        if self._is_garbled_content(text):
            return False
        if self._has_js_required_markers(text):
            return False
        url_score = self.url_scorer.score_url(url)
        min_len = 1000 if url_score >= 5.0 else 500
        return len(text) >= min_len

    # ------------------------------------------------------------------
    # Static fetch (pure HTTP, no content processing)
    # ------------------------------------------------------------------

    async def _static_fetch(self, session: aiohttp.ClientSession, url: str) -> StaticFetchResult:
        """Perform a raw HTTP GET with rate-limiting, robots check, and caching.

        Returns a :class:`StaticFetchResult` with the raw body/bytes.  No
        content parsing or legal analysis happens here.
        """
        await self.rate_limit(url)

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

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": ACCEPT_HEADER,
        }
        cache_headers = self.http_cache.get_cache_headers(url)
        headers.update(cache_headers)

        request_args: dict[str, Any] = {"timeout": timeout, "headers": headers}
        if self.proxy:
            request_args["proxy"] = self.proxy

        async with session.get(url, **request_args) as response:
            # Capture the final URL after any redirect chain (301/302).
            # aiohttp follows redirects by default; response.url reflects
            # the landing page.
            final_url = str(response.url)
            if final_url != url:
                logger.debug(f"Redirect detected: {url} -> {final_url}")

            if response.status == 304:
                logger.debug(f"Content not modified (304) for {url}, using cached metadata")
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
                    "text/plain",
                    "text/xml",
                    "application/xml",
                    "application/rss+xml",
                    "application/atom+xml",
                )
            )

            if is_text:
                body = await response.text()
                return StaticFetchResult(
                    url=url,
                    status_code=response.status,
                    content_type=content_type,
                    body=body,
                    headers=resp_headers,
                    resolved_url=final_url,
                )
            else:
                raw_bytes = await response.read()
                return StaticFetchResult(
                    url=url,
                    status_code=response.status,
                    content_type=content_type,
                    body="",
                    raw_bytes=raw_bytes,
                    headers=resp_headers,
                    resolved_url=final_url,
                )

    # ------------------------------------------------------------------
    # Content extraction (content-type routing, no legal analysis)
    # ------------------------------------------------------------------

    async def _extract_page_content(self, raw: StaticFetchResult, url: str) -> PageContent | None:
        """Route by content-type and extract text/markdown/links.

        Returns ``None`` for unsupported or unparseable content types.
        """
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
                "text/plain",
                "text/xml",
                "application/xml",
                "application/rss+xml",
                "application/atom+xml",
            )
        )
        if not is_text_type:
            return await self._extract_binary_content(raw, url)

        if "text/html" in ct:
            # BeautifulSoup parsing + markdownify conversion are CPU-bound and can
            # block the event loop for hundreds of ms on large pages.  Offload to a
            # thread so other requests stay responsive during a crawl job.
            return await asyncio.to_thread(self._extract_html_content, raw, url)
        elif "text/plain" in ct:
            return self._extract_plain_text_content(raw, url)
        else:
            return self._extract_xml_content(raw, url)

    def _parse_html_string(
        self, html: str, url: str
    ) -> tuple[str, str, str, dict[str, Any], list[dict[str, str]]]:
        """Parse an HTML string and return (title, text, markdown, metadata, links).

        This is the shared, synchronous CPU-bound core used by both
        ``_extract_html_content`` (static fetch) and ``_browser_fetch``
        (headless browser).  Callers that run inside an async context should
        dispatch this via ``asyncio.to_thread`` to avoid blocking the event loop.
        """
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
                logger.info(f"📄 Parsed sitemap/RSS feed, found {len(sitemap_urls)} URLs")
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

    # ------------------------------------------------------------------
    # Browser fetch (returns PageContent)
    # ------------------------------------------------------------------

    # Playwright error message fragments that indicate the browser process has died.
    # We check these to distinguish a recoverable page-level error (timeout, navigation
    # failure) from a fatal crash that requires reinitialising the browser.
    _BROWSER_CRASH_MARKERS = (
        "browser has been closed",
        "target closed",
        "connection closed",
        "context or browser has been closed",
        "browser closed",
    )

    async def _browser_fetch(self, url: str) -> PageContent | None:
        """Fetch page with Camoufox headless browser, returning PageContent or None on failure."""
        _browser_manager, context = await self._setup_browser()
        page: Page = await context.new_page()

        try:
            # Only block heavy media. CSS and fonts are often required for SPA rendering
            # or for bot-detection scripts to verify "visibility".
            # Route handler MUST be async — a sync lambda returning a coroutine would
            # produce an unawaited coroutine object that Playwright silently discards,
            # meaning requests would never actually be aborted.
            async def _abort_media(route: Route) -> None:
                await route.abort()

            await page.route("**/*.{png,jpg,jpeg,gif,svg}", _abort_media)

            total_timeout_ms = self.timeout * 1000

            # Initiate navigation once; domcontentloaded balances speed vs. DOM readiness.
            # Progressive load-state waits below refine readiness further.
            logger.debug(f"🌐 Initiating browser fetch for {url}")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=total_timeout_ms)

            if not response:
                logger.warning(f"❌ Browser fetch failed to initiate for {url}")
                return None

            # Progressively wait for more complete states without restarting navigation.
            # We try for 'networkidle' but settle for 'load' or 'domcontentloaded' if they complete.
            wait_states: list[Literal["domcontentloaded", "load", "networkidle"]] = [
                "domcontentloaded",
                "load",
                "networkidle",
            ]

            # Allocate a portion of total timeout for each state check
            state_timeout = total_timeout_ms // 2

            for state in wait_states:
                try:
                    logger.debug(f"⏳ Waiting for {state} state for {url}")
                    await page.wait_for_load_state(state, timeout=state_timeout)
                    logger.debug(f"✅ Reached {state} state for {url}")
                except Exception as e:
                    logger.debug(f"⚠️ Wait for {state} timed out for {url} (continuing): {e}")
                    # If we reached domcontentloaded, we can try to extract content even if others fail.
                    # We continue the loop to try the next state if time remains.
                    continue

            title = await page.title()
            content = await page.content()

            # Use the browser's actual URL (after redirects / JS navigation)
            # so that relative links are resolved against the correct base.
            final_url = page.url or url
            if final_url != url:
                logger.debug(f"Browser redirect detected: {url} -> {final_url}")

            # CPU-bound HTML parsing — offload to a thread to keep the event loop free.
            # _parse_html_string derives its own title from the <title> tag; we override
            # it with the live browser title which is more reliable for JS-rendered pages.
            _, text_content, markdown_content, metadata, discovered_links = await asyncio.to_thread(
                self._parse_html_string, content, final_url
            )

            # Wait for SPA hydration if initial content is too thin
            body_text_len = len(text_content) if text_content else 0
            if body_text_len < 500:
                for _ in range(3):
                    await asyncio.sleep(1)
                    new_content = await page.content()
                    _, new_text, new_md, new_meta, new_links = await asyncio.to_thread(
                        self._parse_html_string, new_content, final_url
                    )
                    new_len = len(new_text) if new_text else 0
                    if new_len >= 500 or new_len == body_text_len:
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

            # Store the resolved URL so the caller can update dedup / result URL.
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
                # Firefox process died. Reset browser state so the next call to
                # _setup_browser reinitialises instead of reusing a dead instance.
                logger.warning(
                    f"Browser crash detected fetching {url}; resetting browser state",
                    exc_info=True,
                )
                await self._cleanup_browser()
            else:
                logger.warning(f"Browser fetch failed for {url}: {e}", exc_info=True)
            return None
        finally:
            try:
                await page.close()
            except Exception:
                # Page.close() raises if the browser already crashed; ignore it
                # since the browser state has already been reset above.
                pass

    # ------------------------------------------------------------------
    # Result building (content legal score + CrawlResult assembly)
    # ------------------------------------------------------------------

    def _build_crawl_result(self, url: str, page: PageContent) -> CrawlResult:
        """Assemble a :class:`CrawlResult` from extracted :class:`PageContent`.

        Resolves canonical URLs and populates ``legal_score`` from
        :class:`ContentAnalyzer` when configured.
        """
        resolved_url = self._choose_effective_url(url, page.metadata)
        if resolved_url != url:
            page.metadata["canonical_resolved"] = True
            logger.debug(f"Using canonical URL for result: {resolved_url} (original: {url})")
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
            # Normalize analyzer's 0–10 scale to 0.0–1.0 for pipeline thresholds
            result = result.model_copy(update={"legal_score": min(1.0, raw_score / 10.0)})
        return result

    def _extract_main_content_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Extract likely primary content region and remove common boilerplate."""
        main_candidate = None

        # Prefer semantically meaningful content containers first.
        for selector in (
            "main",
            "article",
            '[role="main"]',
            '[id*="content" i]',
            '[class*="content" i]',
            '[data-testid*="content" i]',
            '[data-testid*="article" i]',
            '[data-testid="CEPHtmlSection"]',  # Specifically for Airbnb help articles
            '[data-qa*="content" i]',
            '[id*="legal" i]',
            '[class*="legal" i]',
            '[id*="privacy" i]',
            '[class*="privacy" i]',
            '[id*="terms" i]',
            '[class*="terms" i]',
            '[id*="policy" i]',
            '[class*="policy" i]',
        ):
            candidate = soup.select_one(selector)
            if candidate:
                candidate_text = candidate.get_text(" ", strip=True)
                # For specific modern selectors, we can be more lenient with length
                # as they are likely high-precision.
                min_len = 50 if "data-testid" in selector else 300
                if len(candidate_text) >= min_len:
                    main_candidate = candidate
                    break

        content_root = main_candidate or soup.body or soup
        cleaned = BeautifulSoup(str(content_root), "html.parser")

        # Remove elements that almost never contain legal body text.
        for tag in cleaned(["script", "style", "noscript", "template", "svg", "canvas", "iframe"]):
            tag.decompose()

        for tag in cleaned.find_all(
            ["nav", "header", "footer", "aside", "form", "button", "input", "select", "textarea"]
        ):
            tag.decompose()

        # Remove common boilerplate containers (cookie banners, menus, popups, etc.).
        boilerplate_pattern = re.compile(
            r"(cookie|consent|banner|popup|modal|newsletter|subscribe|breadcrumb|"
            r"social|share|tracking|advert|promo|sidebar|drawer|menu|navigation|"
            r"footer|header|masthead|toolbar)",
            re.IGNORECASE,
        )

        for tag in cleaned.find_all(True):
            # Skip tags with None attrs (can happen with malformed/edge-case HTML)
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
                # Preserve substantial legal-policy content wrappers even when their
                # class/id contains "cookie" or similar boilerplate-like terms.
                tag_text = tag.get_text(" ", strip=True)
                if self._is_substantive_legal_policy_container(attrs, tag_text):
                    continue
                tag.decompose()

        return cleaned

    @staticmethod
    def _is_substantive_legal_policy_container(attrs: str, text: str) -> bool:
        """Return True when a boilerplate-looking container likely holds legal policy text."""
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

        # Require enough body text to avoid preserving tiny cookie banners.
        if len(text_lower) < 300:
            return False

        legal_text_pattern = re.compile(
            r"\b(?:privacy|terms|policy|agreement|legal|gdpr|ccpa|cookie|data protection|"
            r"liability|disclaimer|jurisdiction|compliance|consent|rights)\b",
            re.IGNORECASE,
        )
        return bool(legal_text_pattern.search(text_lower))

    def _extract_text_from_soup(self, soup: BeautifulSoup) -> str:
        """Extract normalized text while preserving some block separation."""
        text_content = soup.get_text(separator="\n")
        text_content = text_content.replace("\xa0", " ")
        text_content = re.sub(r"[ \t]+", " ", text_content)
        text_content = re.sub(r"\n{3,}", "\n\n", text_content)
        return text_content.strip()

    @staticmethod
    @lru_cache(maxsize=50000)  # noqa: B019 - Static method cache is safe
    def _parse_url(url: str) -> ParseResult:
        """Parse URL with caching to avoid repeated parsing."""
        return urlparse(url)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Normalize domain by lowercasing, removing protocol, and removing www prefix."""
        domain_lower = domain.lower().strip()

        # Remove protocol if present (http://, https://)
        if "://" in domain_lower:
            domain_lower = domain_lower.split("://", 1)[1]

        # Remove path if present
        if "/" in domain_lower:
            domain_lower = domain_lower.split("/", 1)[0]

        # Remove port if present
        if ":" in domain_lower:
            domain_lower = domain_lower.split(":", 1)[0]

        # Remove www prefix
        if domain_lower.startswith("www."):
            domain_lower = domain_lower[4:]

        return domain_lower

    def normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and unnecessary query params."""
        parsed = self._parse_url(url)

        # Remove fragment
        normalized = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                "",  # Remove fragment
            )
        )

        # Remove trailing slash for consistency
        if normalized.endswith("/") and len(parsed.path) > 1:
            normalized = normalized[:-1]

        return normalized

    def _choose_effective_url(self, url: str, metadata: dict[str, Any]) -> str:
        """Choose the effective URL between the original URL and canonical URL from metadata.

        Returns the canonical URL if it exists and is valid (same domain), otherwise returns the original URL.

        Args:
            url: The original URL
            metadata: Metadata dict that may contain 'canonical_url'

        Returns:
            The effective URL to use
        """
        candidate = None
        if metadata:
            candidate = metadata.get("canonical_url") or metadata.get("og:url")
        if not candidate:
            return self.normalize_url(url)

        try:
            # Resolve relative canonical against the response URL
            candidate_abs = urljoin(url, str(candidate).strip())
            canonical_normalized = self.normalize_url(candidate_abs)

            # Allow canonical if it is same-domain OR within allowed_domains if configured
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

    def _parse_sitemap_xml(self, content: str) -> list[str]:
        """Parse XML sitemap content and extract URLs.

        Supports both regular sitemaps (<urlset>) and sitemap index files (<sitemapindex>).
        For sitemap index files, returns the sitemap URLs (not the URLs within them).

        Args:
            content: XML sitemap content as string

        Returns:
            List of URLs found in the sitemap
        """
        urls: list[str] = []
        try:
            soup = BeautifulSoup(content, "xml")

            # Check if it's a sitemap index (contains <sitemap> tags)
            sitemap_tags = soup.find_all("sitemap")
            if sitemap_tags:
                # It's a sitemap index - extract sitemap URLs
                for sitemap in sitemap_tags:
                    loc = sitemap.find("loc")
                    if loc and loc.string:
                        urls.append(loc.string.strip())
            else:
                # Regular sitemap - extract URL locations
                url_tags = soup.find_all("url")
                for url_tag in url_tags:
                    loc = url_tag.find("loc")
                    if loc and loc.string:
                        urls.append(loc.string.strip())
        except Exception as e:
            logger.warning(f"Failed to parse sitemap XML: {e}")

        return urls

    # Well-known sitemap paths to probe when robots.txt has no directive.
    _WELL_KNOWN_SITEMAP_PATHS = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-index.xml",
        "/sitemaps.xml",
    ]

    async def _discover_sitemap_urls(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> list[str]:
        """Discover page URLs by fetching and parsing sitemaps.

        Discovery sources (tried in order):
        1. ``Sitemap:`` directives in ``robots.txt``
        2. Well-known sitemap paths (``/sitemap.xml``, …)

        Sitemap index files are followed one level deep.

        Returns:
            Deduplicated list of page URLs found across all sitemaps.
        """
        parsed_url = urlparse(base_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        headers = {"User-Agent": self.user_agent}

        # ------------------------------------------------------------------
        # 1. Collect candidate sitemap URLs to fetch
        # ------------------------------------------------------------------
        sitemap_candidates: list[str] = []

        # 1a. robots.txt directives
        if self.robots_checker:
            try:
                async with session.get(f"{origin}/robots.txt", headers=headers) as response:
                    if response.status == 200:
                        robots_content = await response.text()
                        rules = self.robots_checker._parse_robots_txt(robots_content)
                        sitemap_candidates.extend(rules.get("sitemaps", []))
            except Exception as e:
                logger.debug(f"Failed to fetch robots.txt: {e}")

        # 1b. Well-known paths (only those not already found via robots.txt)
        known = {s.rstrip("/") for s in sitemap_candidates}
        for path in self._WELL_KNOWN_SITEMAP_PATHS:
            candidate = f"{origin}{path}"
            if candidate.rstrip("/") not in known:
                sitemap_candidates.append(candidate)

        # ------------------------------------------------------------------
        # 2. Fetch each sitemap, follow indexes one level deep
        # ------------------------------------------------------------------
        seen_urls: set[str] = set()
        discovered_urls: list[str] = []

        async def _fetch_and_parse_sitemap(sitemap_url: str) -> list[str]:
            """Fetch a single sitemap and return the URLs it contains."""
            try:
                async with session.get(sitemap_url, headers=headers) as resp:
                    if resp.status != 200:
                        return []
                    return self._parse_sitemap_xml(await resp.text())
            except Exception as e:
                logger.debug(f"Failed to fetch sitemap {sitemap_url}: {e}")
                return []

        for sitemap_url in sitemap_candidates:
            urls = await _fetch_and_parse_sitemap(sitemap_url)
            if not urls:
                continue

            # Separate sitemap-index entries from regular page URLs
            child_sitemaps: list[str] = []
            for url in urls:
                if "sitemap" in url.lower() and url.endswith(".xml"):
                    child_sitemaps.append(url)
                elif url not in seen_urls:
                    seen_urls.add(url)
                    discovered_urls.append(url)

            # Follow child sitemaps one level deep
            for child_url in child_sitemaps:
                nested_urls = await _fetch_and_parse_sitemap(child_url)
                for url in nested_urls:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        discovered_urls.append(url)

        return discovered_urls

    def _parse_robots_txt(self, content: str) -> dict[str, Any]:
        """Parse robots.txt content into rules.

        This is a convenience method that delegates to RobotsTxtChecker.
        Used primarily for testing.

        Args:
            content: robots.txt content as string

        Returns:
            Parsed robots.txt rules including sitemaps
        """
        if self.robots_checker:
            return self.robots_checker._parse_robots_txt(content)
        # If robots checking is disabled, return empty structure
        return {"user_agents": {}}

    def is_allowed_domain(self, url: str) -> bool:
        """Check if URL domain is allowed.

        Uses tldextract to compare registered domains, which correctly handles:
        - Subdomains (e.g., www.airbnb.com matches airbnb.com)
        - ccTLD variants (e.g., airbnb.com.ua matches airbnb.com via shared 'airbnb' domain)
        - Rejects unrelated domains (e.g., evil.com, notairbnb.com)
        """
        if not self.allowed_domains:
            return True

        url_ext = _TLD_EXTRACT(url)
        url_domain = url_ext.domain  # e.g., "airbnb"

        for allowed in self.allowed_domains:
            allowed_ext = _TLD_EXTRACT(allowed)
            # Compare the registered domain name (ignoring suffix/subdomain)
            if url_domain == allowed_ext.domain:
                return True

        return False

    def is_same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs are from the same domain."""
        parsed1 = self._parse_url(url1)
        parsed2 = self._parse_url(url2)
        domain1 = self._normalize_domain(parsed1.netloc)
        domain2 = self._normalize_domain(parsed2.netloc)

        return domain1 == domain2

    def should_crawl_url(self, url: str, base_url: str, depth: int) -> bool:
        """
        Determine if URL should be crawled.

        Optimized to parse URLs once and reuse parsed components.
        """
        if depth > self.max_depth:
            logger.debug(f"❌ URL {url} rejected: depth {depth} > max_depth {self.max_depth}")
            return False

        if url in self.visited_urls or url in self.failed_urls or url in self.queued_urls:
            logger.debug(f"❌ URL {url} rejected: already visited, failed, or queued")
            return False

        # Parse URL once and reuse for multiple checks
        parsed_url = self._parse_url(url)

        # Enforce HTTPS
        if parsed_url.scheme != "https":
            logger.debug(f"❌ URL {url} rejected: non-HTTPS scheme '{parsed_url.scheme}'")
            return False

        url_domain = self._normalize_domain(parsed_url.netloc)

        # Check allowed domain
        if self.allowed_domains:
            if not self.is_allowed_domain(url):
                logger.debug(
                    f"❌ URL {url} rejected: domain '{url_domain}' not in allowed domains: {self.allowed_domains}"
                )
                return False

        # Check same domain (only if not following external links)
        if not self.follow_external_links:
            parsed_base = self._parse_url(base_url)
            base_domain = self._normalize_domain(parsed_base.netloc)
            # Check if URL is same domain or subdomain of base domain
            is_same_domain = url_domain == base_domain or url_domain.endswith("." + base_domain)

            # If we have allowed_domains, we already checked that this URL is in one of them.
            # In that case, we permit it even if it's "external" relative to the current base_url.
            if not is_same_domain and not self.allowed_domains:
                logger.debug(
                    f"❌ URL {url} rejected: external link and follow_external_links=False"
                )
                return False

        # Check path-based allow/deny rules
        path = parsed_url.path or "/"

        # 1. Deny rules take precedence
        for pattern in self.compiled_denied_paths:
            if pattern.search(path):
                logger.debug(f"❌ URL {url} rejected: path matches deny pattern {pattern.pattern}")
                return False

        # 2. If allow rules exist, path must match at least one
        if self.compiled_allowed_paths:
            is_path_allowed = False
            for pattern in self.compiled_allowed_paths:
                if pattern.search(path):
                    is_path_allowed = True
                    break
            if not is_path_allowed:
                logger.debug(f"❌ URL {url} rejected: path does not match any allow patterns")
                return False

        # Skip common non-content URLs using compiled patterns
        for pattern in self.compiled_skip_patterns:
            if pattern.search(url):
                logger.debug(f"❌ URL {url} rejected: matches skip pattern {pattern.pattern}")
                return False

        logger.debug(f"✅ URL {url} accepted for crawling at depth {depth}")
        return True

    def extract_links(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
        """Extract links from HTML and from various attributes and scripts.

        The extractor now records `rel` attributes on links and also captures
        canonical link tags in metadata (handled by `extract_metadata`).
        """
        links: list[dict[str, str]] = []

        def add_url(raw_url: str | None, text: str = "", rel: str | None = None) -> None:
            if not raw_url:
                return
            raw_url = str(raw_url).strip()
            # Ignore non-http schemes and fragment-only anchors
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

        # Standard anchors and common data-* attributes
        for a in soup.find_all("a"):
            href = a.get("href")
            # Get primary text from tag content
            text = (a.get_text() or "").strip()

            # Enrich text with title or aria-label if content is thin
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

        # <link> tags (canonical, alternate, etc.)
        # For alternate/canonical links, propagate the page title as anchor text
        # so the URL scorer can see legal keywords.
        # Prioritize meta titles over standard <title> tag.
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

        # Image map areas
        for area in soup.find_all("area", href=True):
            href_value = area.get("href")
            alt_value = area.get("alt")
            add_url(str(href_value) if href_value else None, str(alt_value) if alt_value else "")

        # Forms (action attributes can point to endpoints)
        for form in soup.find_all("form", action=True):
            action_value = form.get("action")
            add_url(str(action_value) if action_value else None, "form action")

        # Buttons and other elements using data-href/data-url
        for el in soup.find_all():
            for attr in ("data-href", "data-url", "data-action", "data-link"):
                attr_value = el.get(attr)
                if attr_value:
                    add_url(str(attr_value), (el.get_text() or "").strip())

        # onclick handlers that perform location changes
        onclick_elements = soup.find_all(attrs={"onclick": True})
        for el in onclick_elements:
            onclick = str(el.get("onclick") or "")
            # capture direct assignments and common APIs
            matches = re.findall(
                r"(?:location(?:\.href)?|window\.location(?:\.href)?)\s*=\s*['\"](.*?)['\"]|location\.assign\(['\"](.*?)['\"]\)|location\.replace\(['\"](.*?)['\"]\)",
                onclick,
            )
            for m in matches:
                url_candidate = next((x for x in m if x), None)
                if url_candidate:
                    add_url(url_candidate, (el.get_text() or "").strip())

        # JSON-LD scripts may contain URLs
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

        # Meta properties like og:url or twitter:url
        for meta in soup.find_all("meta"):
            property_value = meta.get("property")
            content_value = meta.get("content")
            if property_value and content_value:
                prop = str(property_value).lower()
                if prop in ("og:url", "og:see_also", "twitter:url"):
                    add_url(str(content_value), prop)

        # Extract plain http(s) URLs from visible text (sometimes pages list endpoints)
        visible_text = soup.get_text(" ")
        for m in re.findall(r"https?://[^\s'\"<>]+", visible_text):
            add_url(m, "text")

        # Remove duplicates while preserving order
        seen_urls = set()
        unique_links: list[dict[str, str]] = []
        for link in links:
            if link["url"] not in seen_urls:
                seen_urls.add(link["url"])
                unique_links.append(link)

        logger.debug(f"🔗 Discovered {len(unique_links)} unique links from {base_url}")

        return unique_links

    def extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Extract metadata from HTML."""
        metadata: dict[str, Any] = {}

        # HTML lang attribute (most reliable for language detection)
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            metadata["lang"] = html_tag.get("lang")

        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text().strip()

        # Meta tags
        for meta in soup.find_all("meta"):
            if hasattr(meta, "get"):
                name = meta.get("name") or meta.get("property") or meta.get("http-equiv")
                content = meta.get("content")

                if name and content and isinstance(name, str):
                    metadata[name.lower()] = content

        # Link tags (canonical, alternate languages, etc.)
        for link in soup.find_all("link", rel=True):
            rel = link.get("rel")
            href = link.get("href")
            if rel and href:
                # rel can be a list or string
                rel_list = rel if isinstance(rel, list) else [rel]
                for rel_value in rel_list:
                    rel_lower = rel_value.lower()
                    if rel_lower == "canonical":
                        metadata["canonical_url"] = href
                        # Also capture canonical link as discovered link for visibility
                        # (will be normalized later when adding to queues)
                        # Note: we don't automatically follow cross-domain canonicals
                    elif rel_lower == "alternate":
                        hreflang = link.get("hreflang")
                        if hreflang:
                            if "alternate_languages" not in metadata:
                                metadata["alternate_languages"] = {}
                            metadata["alternate_languages"][hreflang] = href

        # Character encoding (useful for proper text extraction)
        charset_tag = soup.find("meta", charset=True)
        if charset_tag:
            metadata["charset"] = charset_tag.get("charset")
        else:
            # Fallback: check http-equiv charset
            charset_equiv = soup.find(
                "meta", attrs={"http-equiv": re.compile(r"content-type", re.I)}
            )
            if charset_equiv and charset_equiv.get("content"):
                content = charset_equiv.get("content", "")
                charset_match = re.search(r"charset=([^;]+)", content, re.I)
                if charset_match:
                    metadata["charset"] = charset_match.group(1).strip()

        # Headers
        for i in range(1, 7):
            headers = soup.find_all(f"h{i}")
            if headers:
                metadata[f"h{i}"] = [h.get_text().strip() for h in headers[:5]]  # First 5

        return metadata

    async def rate_limit(self, url: str) -> None:
        """
        Apply per-domain rate limiting.

        Different domains can be crawled concurrently, but requests to the same
        domain are rate-limited according to delay_between_requests.

        Args:
            url: The URL being requested
        """
        await self.rate_limiter.rate_limit(url)

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable (transient) or permanent.

        Retryable errors:
        - Network errors (connection failures, DNS issues)
        - Timeout errors
        - Server errors (5xx)
        - Rate limiting (429)

        Non-retryable errors:
        - Client errors (4xx except 429)
        - Content type errors
        - Robots.txt blocks
        """
        # Network and timeout errors are retryable
        if isinstance(error, aiohttp.ClientError | asyncio.TimeoutError):
            return True

        # Check if it's an HTTP error with retryable status code
        if isinstance(error, aiohttp.ClientResponseError):
            status = error.status
            # Retry on server errors (5xx) and rate limiting (429)
            if status >= 500 or status == 429:
                return True
            # Don't retry on client errors (4xx except 429)
            return False

        # Other exceptions are not retryable
        return False

    async def _fetch_page_internal(self, session: aiohttp.ClientSession, url: str) -> CrawlResult:
        """Fetch and extract content for a single URL (without retry logic).

        Pipeline:
          1. Static HTTP fetch
          2. Content extraction (route by content-type)
          3. Quality gate — if content is insufficient and browser is enabled, retry with Camoufox
          4. Build CrawlResult (includes content ``legal_score`` when analyzer is set)
        """
        try:
            raw = await self._static_fetch(session, url)

            if raw.blocked_by_robots_txt:
                return raw.to_failed_crawl_result()

            # Use the resolved URL (after redirects) for all downstream work
            # so that link extraction, deduplication, and the final CrawlResult
            # URL reflect the actual page location.
            effective_url = raw.resolved_url or url
            if effective_url != url:
                # Mark the redirect target as visited so we don't re-crawl it
                # when it appears as a discovered link from another page.
                self.visited_urls.add(self.normalize_url(effective_url))

            page = await self._extract_page_content(raw, effective_url)

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

            if not self._content_is_sufficient(page, effective_url) and self.use_browser:
                logger.info(f"🔄 Static content insufficient, trying browser: {effective_url}")
                browser_page = await self._browser_fetch(effective_url)
                if browser_page is not None:
                    if not self._content_is_sufficient(browser_page, effective_url):
                        logger.warning(f"⚠️ Browser content still insufficient: {effective_url}")
                        return CrawlResult(
                            url=effective_url,
                            title=browser_page.title,
                            content="",
                            markdown="",
                            metadata=browser_page.metadata,
                            status_code=browser_page.status_code,
                            success=False,
                            error_message="Browser rendered content is still insufficient",
                        )
                    # The browser may have followed additional redirects / JS
                    # navigations; prefer its resolved URL if available.
                    browser_resolved = browser_page.metadata.pop("_browser_resolved_url", None)
                    if browser_resolved and browser_resolved != effective_url:
                        effective_url = browser_resolved
                        self.visited_urls.add(self.normalize_url(effective_url))
                    page = browser_page
                else:
                    logger.warning(f"⚠️ Browser and static fetch both failed for: {effective_url}")
                    return CrawlResult(
                        url=effective_url,
                        title=page.title if page else "",
                        content="",
                        markdown="",
                        metadata=page.metadata if page else {},
                        status_code=page.status_code if page else 0,
                        success=False,
                        error_message="Static content insufficient and browser rendering failed",
                    )

            return self._build_crawl_result(effective_url, page)

        except aiohttp.ClientResponseError as e:
            if e.status >= 500 or e.status == 429:
                raise
            logger.warning(f"Client error fetching {url}: HTTP {e.status}: {e.message}")
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
        """
        Fetch and process a single page with automatic retry logic.

        This method handles retries for transient network errors with exponential backoff.
        Non-retryable errors (4xx client errors) are returned immediately without retry.
        """
        # Adjust retry attempts based on instance configuration
        # We need to create a new retry decorator with the configured max_retries
        max_attempts = self.max_retries + 1  # +1 for initial attempt

        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
            reraise=True,
        )
        async def _fetch_with_configurable_retry() -> CrawlResult:
            result = await self._fetch_page_internal(session, url)
            return result

        try:
            result: CrawlResult = await _fetch_with_configurable_retry()
            return result
        except aiohttp.ClientResponseError as e:
            # Handle HTTP errors that weren't retried
            if e.status >= 500 or e.status == 429:
                # Should have been retried, but if we get here, all retries failed
                logger.error(
                    f"Failed to fetch {url} after {self.max_retries} retries: HTTP {e.status}"
                )
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
                # Non-retryable client error
                logger.warning(f"Client error fetching {url}: HTTP {e.status}: {e.message}")
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
            # All retries exhausted for network/timeout errors
            logger.error(
                f"Failed to fetch {url} after {self.max_retries} retries: {type(e).__name__}: {e}"
            )
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

    # Locale-like path segment pattern (e.g. "en", "fr-FR", "pt-br", "zh-Hans")
    _LOCALE_RE = re.compile(r"^[a-z]{2}(?:[-_][a-zA-Z]{2,4})?$")

    def generate_potential_legal_urls(self, base_url: str) -> list[str]:
        """Generate potential legal document URLs based on common patterns.

        The generator is *path-prefix-aware*: if the base URL contains a
        non-trivial path (e.g. a locale prefix like ``/en`` or a sub-section
        like ``/help``), legal paths are generated both at the domain root
        **and** under that prefix so that sites structured as
        ``/en/articles/…`` or ``/help/legal/…`` are discovered.

        It also produces hub / listing page URLs (``/articles``,
        ``/collections``, …) that are common in knowledge-base platforms
        (Intercom, Zendesk, Freshdesk, …) and frequently link to individual
        legal documents.
        """
        parsed = urlparse(base_url)
        domain = parsed.netloc

        # Common legal document paths
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
        ]

        # Hub / listing / index pages common on knowledge-base platforms
        # (Intercom, Zendesk, Freshdesk, HelpScout, …).  These intermediate
        # pages typically link to individual articles containing the actual
        # legal text.
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

        # ------------------------------------------------------------------
        # Detect meaningful path prefixes from the base URL.
        #
        # Examples:
        #   https://privacy.example.com/en           → prefix "/en"
        #   https://help.example.com/hc/en-us        → prefix "/hc/en-us"
        #   https://example.com                      → no prefix
        #   https://example.com/                     → no prefix
        # ------------------------------------------------------------------
        base_path = parsed.path.rstrip("/")
        prefixes: list[str] = [""]  # always generate root-level URLs

        if base_path and base_path != "/":
            prefixes.append(base_path)

            # If the path has multiple segments, also add each cumulative
            # sub-prefix.  For "/hc/en-us" this yields ["/hc", "/hc/en-us"].
            segments = [s for s in base_path.split("/") if s]
            if len(segments) > 1:
                for i in range(1, len(segments)):
                    sub = "/" + "/".join(segments[:i])
                    if sub not in prefixes:
                        prefixes.append(sub)

        # ------------------------------------------------------------------
        # Build the final URL set (deduplicated, preserving order).
        # ------------------------------------------------------------------
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

    # Keywords whose presence in a page title / description indicates the
    # page is a "legal hub" — i.e. a page whose outgoing links are more
    # likely to point to legal documents.
    _LEGAL_HUB_KEYWORDS = frozenset(
        [
            "terms",
            "privacy",
            "policy",
            "legal",
            "cookie",
            "agreement",
            "gdpr",
            "compliance",
            "data protection",
        ]
    )

    def _compute_parent_page_boost(self, page_metadata: dict[str, Any] | None) -> float:
        """Return a score boost for links discovered on a page with legal indicators.

        When the page title or meta description contains legal keywords the
        page is likely a "legal hub" (e.g. a help centre section listing
        policies).  Links FROM such pages deserve a priority boost in the
        ``best_first`` strategy so that opaque URLs (``/help/article/2908``)
        are not buried behind thousands of irrelevant sitemap entries.
        """
        if not page_metadata:
            return 0.0

        texts_to_check = [
            (page_metadata.get("title") or "").lower(),
            (page_metadata.get("description") or "").lower(),
            (page_metadata.get("og:title") or "").lower(),
        ]

        for text in texts_to_check:
            if any(kw in text for kw in self._LEGAL_HUB_KEYWORDS):
                return 3.0

        return 0.0

    def add_urls_to_queue(
        self,
        links: list[dict[str, str]],
        base_url: str,
        depth: int,
        page_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add URLs to the appropriate queue based on strategy.

        Respects rel="nofollow" on links if `follow_nofollow` is False and will skip
        adding discovered links entirely if the page contains a meta robots:nofollow
        directive when `respect_meta_robots` is True.
        """
        # Honor page-level meta robots (e.g., <meta name="robots" content="nofollow">)
        if page_metadata and self.respect_meta_robots:
            robots_meta = page_metadata.get("robots") or page_metadata.get("meta:robots")
            if isinstance(robots_meta, str) and "nofollow" in robots_meta.lower():
                logger.debug(
                    f"Page meta robots contains 'nofollow'; skipping discovered links for {base_url}"
                )
                return

        # Compute a priority boost for links coming from a "legal hub" page.
        # Only relevant for best_first where score ordering matters.
        parent_boost = (
            self._compute_parent_page_boost(page_metadata) if self.strategy == "best_first" else 0.0
        )
        if parent_boost > 0:
            logger.debug(
                f"Legal hub detected on parent page; boosting discovered link scores by {parent_boost:.1f}"
            )

        # Track URLs explicitly skipped due to rel='nofollow' so generated potential
        # legal URLs that match them are not redundantly added.
        skipped_urls: set[str] = set()
        for link in links:
            url = link["url"]
            anchor_text = link.get("text")
            rel = link.get("rel") or ""

            # Skip links explicitly marked as nofollow when configured to do so
            if rel and "nofollow" in rel and not self.follow_nofollow:
                logger.debug(f"Skipping link {url} due to rel='nofollow'")
                skipped_urls.add(self.normalize_url(url))
                continue

            if not self.should_crawl_url(url, base_url, depth + 1):
                continue

            self.queued_urls.add(url)
            if self.strategy == "bfs":
                self.url_queue.append((url, depth + 1))
                logger.debug(f"Added to BFS queue: {url} (depth: {depth + 1})")
            elif self.strategy == "dfs":
                self.url_stack.append((url, depth + 1))
                logger.debug(f"Added to DFS stack: {url} (depth: {depth + 1})")
            elif self.strategy == "best_first":
                score = self.url_scorer.score_url(url, anchor_text=anchor_text) + parent_boost
                if score < self.min_legal_score:
                    logger.debug(
                        f"Skipping URL below min_legal_score ({score:.2f} < {self.min_legal_score}): {url}"
                    )
                    self.queued_urls.discard(url)
                    continue
                heapq.heappush(self.url_priority_queue, (-score, url, depth + 1))
                logger.debug(
                    f"Added to Best-First queue: {url} (score: {score:.2f}, anchor: {anchor_text})"
                )

        # Fallback: if sitemaps didn't provide seeds, speculatively probe
        # common legal paths from the starting page.  When sitemaps DID
        # provide seeds we skip this — the sitemap already tells us what
        # pages exist, so blind probing would only waste requests.
        if depth == 0 and not self._sitemap_seeded:
            potential_legal_urls = self.generate_potential_legal_urls(base_url)
            logger.info(
                f"🔍 No sitemap seeds — probing {len(potential_legal_urls)} potential legal URLs"
            )

            for url in potential_legal_urls:
                normalized = self.normalize_url(url)
                # Skip potential URLs that match links explicitly skipped due to rel='nofollow'
                if normalized in skipped_urls:
                    logger.debug(
                        f"Skipping generated potential URL {url} because it was marked nofollow on the page"
                    )
                    continue

                if not self.should_crawl_url(url, base_url, 1):
                    continue

                self.queued_urls.add(url)
                if self.strategy == "bfs":
                    self.url_queue.append((url, 1))
                    logger.debug(f"Added potential legal URL to BFS queue: {url}")
                elif self.strategy == "dfs":
                    self.url_stack.append((url, 1))
                    logger.debug(f"Added potential legal URL to DFS stack: {url}")
                elif self.strategy == "best_first":
                    score = self.url_scorer.score_url(url, anchor_text=None)
                    heapq.heappush(self.url_priority_queue, (-score, url, 1))
                    logger.debug(
                        f"Added potential legal URL to Best-First queue: {url} (score: {score:.2f})"
                    )

    def get_next_url(self) -> tuple[str, int] | None:
        """Get next URL from queue based on strategy."""
        if self.strategy == "bfs" and self.url_queue:
            return self.url_queue.popleft()
        elif self.strategy == "dfs" and self.url_stack:
            return self.url_stack.pop()
        elif self.strategy == "best_first" and self.url_priority_queue:
            _, url, depth = heapq.heappop(self.url_priority_queue)
            return url, depth
        return None

    def _get_pending_url_count(self) -> int:
        """Return the number of URLs waiting in the active queue/stack."""
        if self.strategy == "bfs":
            return len(self.url_queue)
        elif self.strategy == "dfs":
            return len(self.url_stack)
        elif self.strategy == "best_first":
            return len(self.url_priority_queue)
        return 0

    async def crawl(self, base_url: str) -> list[CrawlResult]:
        """
        Crawl starting from base URL.

        Args:
            base_url: Starting URL

        Returns:
            List of crawl results
        """
        try:
            logger.info(f"🕷️  Starting crawl from: {base_url}")
            logger.info(
                f"📊 Strategy: {self.strategy}, Max depth: {self.max_depth}, Max pages: {self.max_pages}"
            )

            # Initialize
            base_url = self.normalize_url(base_url)
            self.stats = CrawlStats()

            # Add base URL to queue
            self.queued_urls.add(base_url)
            if self.strategy == "bfs":
                self.url_queue.append((base_url, 0))
                logger.debug(f"Added base URL to BFS queue: {base_url} (depth: 0)")
            elif self.strategy == "dfs":
                self.url_stack.append((base_url, 0))
                logger.debug(f"Added base URL to DFS stack: {base_url} (depth: 0)")
            elif self.strategy == "best_first":
                score = self.url_scorer.score_url(base_url)
                heapq.heappush(self.url_priority_queue, (-score, base_url, 0))
                logger.debug(f"Added base URL to Best-First queue: {base_url} (score: {score:.2f})")

            # Create session with connection pooling
            connector = aiohttp.TCPConnector(limit=self.max_concurrent)
            timeout = aiohttp.ClientTimeout(total=self.timeout)

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Discover sitemaps and use their URLs as depth-0 seeds.
                # This gives every sitemap URL the full max_depth of crawling
                # and avoids wasting requests on speculative path guessing.
                try:
                    sitemap_urls = await self._discover_sitemap_urls(session, base_url)
                    seeded = 0
                    for url in sitemap_urls:
                        if not self.should_crawl_url(url, base_url, 0):
                            continue
                        self.queued_urls.add(url)
                        if self.strategy == "bfs":
                            self.url_queue.append((url, 0))
                        elif self.strategy == "dfs":
                            self.url_stack.append((url, 0))
                        elif self.strategy == "best_first":
                            score = self.url_scorer.score_url(url, anchor_text=None)
                            heapq.heappush(self.url_priority_queue, (-score, url, 0))
                        seeded += 1
                    if seeded:
                        self._sitemap_seeded = True
                        logger.info(f"🗺️  Seeded {seeded} URLs from sitemaps (depth 0)")
                except Exception:
                    logger.debug("Sitemap discovery failed; continuing without sitemap")

                # Semaphore to limit concurrent requests
                semaphore = asyncio.Semaphore(self.max_concurrent)

                async def process_url(url: str) -> CrawlResult:
                    async with semaphore:
                        return await self.fetch_page(session, url)

                # Main crawl loop
                while len(self.visited_urls) < self.max_pages:
                    # Get batch of URLs to process
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
                        break

                    # Process batch concurrently
                    tasks = [process_url(url) for url, _depth in batch]
                    batch_results = await asyncio.gather(*tasks)

                    # Process results
                    for result, (url, depth) in zip(batch_results, batch, strict=True):
                        self.stats.total_urls += 1

                        if result.success:
                            self.stats.crawled_urls += 1
                            self.results.append(result)

                            # Add discovered URLs to queue
                            if depth < self.max_depth:
                                self.add_urls_to_queue(
                                    result.discovered_links,
                                    base_url,
                                    depth,
                                    page_metadata=result.metadata,
                                )
                            logger.info(
                                f"✅ [{self.stats.crawled_urls}/{self.max_pages}] "
                                f"{url} — {len(result.discovered_links)} links"
                            )
                        else:
                            self.stats.failed_urls += 1
                            self.failed_urls.add(url)
                            logger.warning(f"❌ Failed: {url} - {result.error_message}")

                    # Progress update
                    if self.stats.total_urls % 10 == 0:
                        logger.info(
                            f"📊 Progress: {self.stats.total_urls} processed, "
                            f"{self.stats.crawled_urls} successful, "
                            f"{self.stats.crawl_rate:.1f} pages/sec"
                        )
                        if self.progress_callback:
                            pending = self._get_pending_url_count()
                            total_known = min(self.max_pages, len(self.visited_urls) + pending)
                            self.progress_callback(self.stats.total_urls, total_known)

                # Ensure the UI gets a final progress update even if we finish
                # before hitting the next modulo threshold.
                if self.progress_callback:
                    pending = self._get_pending_url_count()
                    total_known = min(self.max_pages, len(self.visited_urls) + pending)
                    self.progress_callback(self.stats.total_urls, total_known)

            # Final statistics
            logger.info("🎉 Crawl completed!")
            logger.info(f"📊 Total URLs: {self.stats.total_urls}")
            logger.info(f"✅ Successfully crawled: {self.stats.crawled_urls}")
            logger.info(f"❌ Failed: {self.stats.failed_urls}")
            logger.info(f"⏱️  Total time: {self.stats.elapsed_time:.1f} seconds")
            logger.info(f"🚀 Average rate: {self.stats.crawl_rate:.1f} pages/sec")

            return self.results
        finally:
            # Shutdown log executor to ensure all pending writes complete
            await self._shutdown_log_executor()

    def clear_rate_limiter_cache(self) -> None:
        """Clear the rate limiter cache (useful between crawl sessions)."""
        self.rate_limiter.clear_cache()

    async def crawl_multiple(self, urls: list[str]) -> list[CrawlResult]:
        """Crawl multiple base URLs."""
        all_results = []

        for i, url in enumerate(urls, 1):
            logger.info(f"🔄 Processing URL {i}/{len(urls)}: {url}")
            results = await self.crawl(url)
            all_results.extend(results)

            # Reset state for next URL
            self.visited_urls.clear()
            self.failed_urls.clear()
            self.queued_urls.clear()
            self._sitemap_seeded = False
            self.url_queue.clear()
            self.url_stack.clear()
            self.url_priority_queue.clear()
            self.results.clear()
            # Clear caches between different base URLs
            if self.robots_checker:
                self.robots_checker.clear_cache()
            # Optionally clear rate limiter cache between different base URLs
            # Uncomment if you want to reset rate limiting between different sites:
            # self.clear_rate_limiter_cache()

        return all_results


# Convenience functions
async def crawl_for_legal_documents(
    base_url: str,
    max_depth: int = 4,
    max_pages: int = 1000,
    strategy: str = "bfs",
) -> list[CrawlResult]:
    """
    Simple interface to crawl for legal documents.

    Args:
        base_url: Starting URL
        max_depth: Maximum crawl depth
        max_pages: Maximum pages to crawl
        strategy: Crawling strategy

    Returns:
        List of crawl results, sorted by legal relevance
    """
    crawler = ClauseaCrawler(
        max_depth=max_depth, max_pages=max_pages, strategy=strategy, min_legal_score=0.0
    )

    return await crawler.crawl(base_url)


async def test_specific_url(url: str) -> CrawlResult:
    """
    Test a specific URL to see how it scores and what content is extracted.

    Args:
        url: The URL to test

    Returns:
        CrawlResult for the specific URL
    """
    crawler = ClauseaCrawler(max_depth=1, max_pages=1, strategy="bfs", min_legal_score=0.0)

    # Test URL scoring
    url_score = crawler.url_scorer.score_url(url)
    logger.info(f"🔍 URL Score for {url}: {url_score}")

    # Create session and fetch the page
    connector = aiohttp.TCPConnector(limit=1)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        result = await crawler.fetch_page(session, url)

        if result.success:
            logger.info(f"✅ Successfully fetched: {url}")
            logger.info(f"📄 Title: {result.title}")
            logger.info(f"📊 Content Length: {len(result.content)} chars")
            logger.info(f"🔗 Discovered Links: {len(result.discovered_links)}")
        else:
            logger.error(f"❌ Failed to fetch: {url} - {result.error_message}")

    return result


# Example usage
async def main() -> None:
    """Example usage of the ClauseaCrawler."""
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python crawler.py <base_url> [--test-url specific_url]")
        return

    # Check if we're testing a specific URL
    if len(sys.argv) >= 4 and sys.argv[2] == "--test-url":
        specific_url = sys.argv[3]
        logger.info(f"🔍 Testing specific URL: {specific_url}")
        result = await test_specific_url(specific_url)

        logger.info("\n🎯 Test Result:")
        logger.info(f"📄 Title: {result.title or 'Untitled'}")
        logger.info(f"   URL: {result.url}")
        logger.info(f"   Success: {result.success}")
        logger.info(f"   Content Length: {len(result.content)} chars")
        if not result.success:
            logger.info(f"   Error: {result.error_message}")
        return

    base_url = sys.argv[1]

    results = await crawl_for_legal_documents(
        base_url=base_url, max_depth=4, max_pages=200, strategy="bfs"
    )

    logger.info(f"\n📊 All crawled pages ({len(results)} total):")
    for i, result in enumerate(results, 1):
        logger.info(f"{i:3d}. {result.title or 'Untitled'[:50]}")
        logger.info(f"     URL: {result.url}")
        logger.info(f"     Content Length: {len(result.content)} chars")
        logger.info("")


if __name__ == "__main__":
    asyncio.run(main())
