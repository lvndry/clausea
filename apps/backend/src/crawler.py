"""
Legal document crawler for extracting privacy policies, terms of service, and other legal content.
"""

import asyncio
import heapq
import json
import logging
import re
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

import aiohttp
import markdownify
from bs4 import BeautifulSoup
from camoufox import AsyncCamoufox
from playwright.async_api import BrowserContext, Page
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.logging import get_logger

logger = get_logger(__name__)

# Standard user agent string following RFC 7231 format
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; ClauseaBot/2.0; +https://www.clausea.co/bot.html; lvndry@proton.me)"
)


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
    legal_score: float = Field(
        default=0.0, description="Calculated relevance score for legal content"
    )
    discovered_links: list[dict[str, str]] = Field(
        default_factory=list, description="List of links with both URL and original anchor text"
    )


class CrawlStats(BaseModel):
    """Crawl statistics."""

    total_urls: int = 0
    crawled_urls: int = 0
    failed_urls: int = 0
    legal_documents_found: int = 0
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
                r"terms-of-service": 8.0,
                r"cookie-policy": 7.0,
                r"data-processing-addendum": 8.0,
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
            "blog": -1.0,
            "news": -1.0,
            "product": -0.5,
            "help": -0.5,
            "contact": -0.5,
            "about": -0.5,
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

        # Score based on anchor text if provided
        if anchor_text:
            anchor_lower = anchor_text.lower()
            # If anchor text explicitly contains legal keywords, give it a high boost
            anchor_words = self.word_pattern.findall(anchor_lower)
            for word in anchor_words:
                if word in self.legal_keywords:
                    # Give anchor text matches a weight boost
                    score += self.legal_keywords[word] * 1.5

            # Also check for phrases in anchor text
            for pattern, weight in self.compiled_high_value_patterns.items():
                if pattern.search(anchor_lower):
                    score += weight * 1.5

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

    def __init__(self, delay_between_requests: float = 1.0) -> None:
        """
        Initialize the domain rate limiter.

        Args:
            delay_between_requests: Minimum delay between requests to the same domain in seconds
        """
        self.delay_between_requests = delay_between_requests
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
                sleep_time = self.delay_between_requests - elapsed
                await asyncio.sleep(sleep_time)
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
                            logger.debug(f"Fetched robots.txt from {robots_url}")
                            parsed_rules = self._parse_robots_txt(robots_content)
                        else:
                            logger.debug(
                                f"Could not fetch robots.txt from {robots_url} (status: {response.status})"
                            )
                            # If we can't fetch robots.txt, allow all
                            parsed_rules = {"allow_all": True}
                except Exception as e:
                    logger.debug(f"Error fetching robots.txt from {robots_url}: {e}")
                    # If we can't fetch robots.txt, allow all
                    parsed_rules = {"allow_all": True}

                # Add to cache with LRU eviction
                self._add_to_cache(base_url, parsed_rules)

            robots_rules = self.robots_cache.pop(base_url)
            self.robots_cache[base_url] = robots_rules
            if robots_rules.get("allow_all", False):
                logger.debug(f"No robots.txt rules for {base_url}, allowing access")
                return True, "No robots.txt rules found"

            # If sitemaps exist in parsed rules, expose them to the caller
            return (
                self._check_url_allowed(url, robots_rules)
                if not robots_rules.get("sitemaps")
                else (True, "Sitemap directives present")
            )

        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {e}")
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
        logger.debug(f"Parsing robots.txt with {len(lines)} lines")

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
                    logger.debug(f"Found user-agent: {current_user_agent}")
                elif directive == "disallow" and current_user_agent:
                    if value:  # Only add non-empty disallow rules
                        user_agents[current_user_agent]["disallow"].append(value)
                        logger.debug(f"Added disallow rule for {current_user_agent}: {value}")
                elif directive == "allow" and current_user_agent:
                    user_agents[current_user_agent]["allow"].append(value)
                    logger.debug(f"Added allow rule for {current_user_agent}: {value}")
                elif directive == "crawl-delay" and current_user_agent:
                    # Store crawl delay for rate limiting
                    try:
                        delay = float(value)
                        user_agents[current_user_agent]["crawl_delay"] = delay
                        logger.debug(f"Added crawl-delay for {current_user_agent}: {delay}")
                    except ValueError:
                        logger.warning(f"Invalid crawl-delay value: {value}")
                elif directive == "sitemap":
                    # Record sitemap directives for later discovery
                    if "sitemaps" not in locals():
                        sitemaps: list[str] = []
                    sitemaps.append(value)
                    logger.debug(f"Found sitemap directive: {value}")

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
        logger.debug(f"Checking rules for URL: {url} (path: {path})")

        # Find applicable rules by checking user agent patterns
        applicable_rules = None
        matched_user_agent = None
        user_agent_lower = self.user_agent.lower()

        # First check exact match
        if user_agent_lower in user_agents:
            applicable_rules = user_agents[user_agent_lower]
            matched_user_agent = user_agent_lower
            logger.debug(f"Found exact user-agent match: {user_agent_lower}")
        # Then check wildcard patterns
        else:
            for pattern in self.user_agent_patterns:
                if pattern in user_agents:
                    applicable_rules = user_agents[pattern]
                    matched_user_agent = pattern
                    logger.debug(f"Found wildcard user-agent match: {pattern}")
                    break

        # If robots_rules include sitemaps (collected during parsing), attach for callers
        sitemaps = robots_rules.get("sitemaps")
        if sitemaps:
            logger.debug(f"Robots.txt contains {len(sitemaps)} sitemaps")

        # If no rules found, allow by default
        if not applicable_rules:
            return True, "No matching rules found"

        logger.debug(f"Using rules for user-agent: {matched_user_agent}")

        # Check allow rules first (most specific wins)
        for allow_pattern in applicable_rules.get("allow", []):
            if self._path_matches_pattern(path, allow_pattern):
                logger.debug(f"URL allowed by pattern: {allow_pattern}")
                return True, f"Explicitly allowed by pattern: {allow_pattern}"

        # Then check disallow rules
        for disallow_pattern in applicable_rules.get("disallow", []):
            if self._path_matches_pattern(path, disallow_pattern):
                # If we have a matching disallow rule, check if there's a more specific allow rule
                for allow_pattern in applicable_rules.get("allow", []):
                    if self._path_matches_pattern(path, allow_pattern) and len(allow_pattern) > len(
                        disallow_pattern
                    ):
                        logger.debug(
                            f"URL allowed by more specific pattern: {allow_pattern} (overrides {disallow_pattern})"
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
        max_depth: int = 3,
        max_pages: int = 1000,
        max_concurrent: int = 10,
        delay_between_requests: float = 1.0,
        timeout: int = 30,
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
        # Opt-in binary crawling and parser preferences
        enable_binary_crawling: bool = False,
        use_tika_for_binaries: bool = False,
        use_pdfminer_for_pdf: bool = False,
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
        self.browser_context: BrowserContext | None = None
        self.browser_lock = asyncio.Lock()

        # State
        self.visited_urls: set[str] = set()
        self.failed_urls: set[str] = set()
        self.url_queue: deque[tuple[str, int]] = deque()  # For BFS
        self.url_stack: list[tuple[str, int]] = []  # For DFS
        self.url_priority_queue: list[tuple[float, str, int]] = []  # For best-first (scored URLs)
        self.results: list[CrawlResult] = []
        self.stats = CrawlStats()

        # Per-domain rate limiting (allows concurrent requests to different domains)
        self.rate_limiter = DomainRateLimiter(delay_between_requests=delay_between_requests)

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

    async def _setup_browser(self) -> tuple[AsyncCamoufox, BrowserContext]:  # type: ignore[return-value, name-defined]
        """Initialize and return a Camoufox browser and context."""
        async with self.browser_lock:
            if self.browser_instance is None:
                # Configure Camoufox with fingerprint spoofing and anti-detection
                config = {
                    "navigator.userAgent": self.user_agent,
                    "window.innerWidth": 1280,
                    "window.innerHeight": 800,
                    "window.outerWidth": 1280,
                    "window.outerHeight": 800,
                }

                # Prepare Camoufox initialization arguments
                init_kwargs: dict[str, Any] = {
                    "config": config,
                    "headless": True,
                }

                if self.proxy:
                    # Camoufox supports proxy configuration directly
                    init_kwargs["proxy"] = {"server": self.proxy}

                # Create Camoufox browser instance
                self.browser_instance = AsyncCamoufox(**init_kwargs)
                await self.browser_instance.__aenter__()  # Manually enter context manager

                # Get the browser context (Camoufox's AsyncCamoufox acts as both browser and context)
                self.browser_context = self.browser_instance  # type: ignore[assignment]

            return self.browser_instance, self.browser_context  # type: ignore[return-value]

    async def _cleanup_browser(self) -> None:
        """Clean up Camoufox resources."""
        async with self.browser_lock:
            if self.browser_instance:
                await self.browser_instance.__aexit__(
                    None, None, None
                )  # Manually exit context manager
                self.browser_instance = None
                self.browser_context = None
                logger.debug("🌐 Camoufox browser closed")

    async def _fetch_with_browser(self, url: str) -> CrawlResult:
        """
        Fetch page content using a headless browser (for dynamic rendering).

        Tries progressively less strict wait conditions:
        1. networkidle (most strict, waits for all network activity to stop)
        2. load (waits for page load event)
        3. domcontentloaded (waits for DOM to be ready)

        Returns a failed result if all strategies fail, which can be used
        by the caller to fall back to static HTML parsing.
        """
        browser, context = await self._setup_browser()
        # Camoufox's AsyncCamoufox instance can create pages directly
        page: Page = await browser.new_page()  # type: ignore[assignment, name-defined]

        try:
            # Block heavy resources for performance
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,otf}", lambda route: route.abort()
            )

            # Try progressively less strict wait conditions
            wait_strategies: list[
                tuple[str, Literal["networkidle", "load", "domcontentloaded"]]
            ] = [
                ("networkidle", "networkidle"),
                ("load", "load"),
                ("domcontentloaded", "domcontentloaded"),
            ]

            response = None
            last_error = None

            for strategy_name, wait_until in wait_strategies:
                try:
                    logger.debug(f"Trying browser fetch with {strategy_name} strategy for {url}")
                    response = await page.goto(
                        url, wait_until=wait_until, timeout=self.timeout * 1000
                    )
                    if response:
                        logger.debug(f"Successfully loaded {url} with {strategy_name} strategy")
                        break
                except Exception as e:
                    last_error = e
                    logger.debug(f"Browser fetch with {strategy_name} failed for {url}: {e}")
                    # Continue to next strategy
                    continue

            if not response:
                # All strategies failed
                logger.warning(f"All browser fetch strategies failed for {url}: {last_error}")
                return CrawlResult(
                    url=url,
                    title="",
                    content="",
                    markdown="",
                    metadata={},
                    status_code=500,
                    success=False,
                    error_message=f"Browser fetch error: {str(last_error)}",
                )

            # Extract content
            title = await page.title()
            content = await page.content()

            # Process with BeautifulSoup to extract structured data (links, metadata)
            soup = BeautifulSoup(content, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            text_content = soup.get_text()
            text_content = re.sub(r"\s+", " ", text_content).strip()
            markdown_content = markdownify.markdownify(str(soup), heading_style="ATX")
            metadata = self.extract_metadata(soup)
            discovered_links = self.extract_links(soup, url)

            # Prefer canonical if present and valid
            resolved_url = self._choose_effective_url(url, metadata)
            if resolved_url != url:
                metadata["canonical_resolved"] = True
                logger.debug(f"Using canonical URL for result: {resolved_url} (original: {url})")
                url = resolved_url

            return CrawlResult(
                url=url,
                title=title,
                content=text_content,
                markdown=markdown_content,
                metadata=metadata,
                status_code=response.status,
                success=True,
                discovered_links=discovered_links,
            )

        except Exception as e:
            logger.warning(f"Browser fetch failed for {url}: {e}")
            return CrawlResult(
                url=url,
                title="",
                content="",
                markdown="",
                metadata={},
                status_code=500,
                success=False,
                error_message=f"Browser fetch error: {str(e)}",
            )
        finally:
            await page.close()

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

    async def _discover_sitemap_urls(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> list[str]:
        """Discover sitemap URLs from robots.txt and fetch/parse sitemap files.

        This method:
        1. Fetches robots.txt for the base URL
        2. Parses it to extract sitemap directives
        3. Fetches and parses sitemap XML files
        4. Returns all discovered URLs from sitemaps

        Args:
            session: aiohttp session for making requests
            base_url: Base URL to discover sitemaps for

        Returns:
            List of URLs discovered from sitemaps
        """
        discovered_urls: list[str] = []

        try:
            # Get robots.txt rules (this will use the cache if available)
            if self.robots_checker:
                parsed_url = urlparse(base_url)
                robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"

                # Fetch robots.txt
                try:
                    async with session.get(
                        robots_url, headers={"User-Agent": self.user_agent}
                    ) as response:
                        if response.status == 200:
                            robots_content = await response.text()
                            robots_rules = self.robots_checker._parse_robots_txt(robots_content)

                            # Extract sitemap URLs from robots.txt
                            sitemap_urls = robots_rules.get("sitemaps", [])

                            # Fetch and parse each sitemap
                            for sitemap_url in sitemap_urls:
                                try:
                                    async with session.get(
                                        sitemap_url, headers={"User-Agent": self.user_agent}
                                    ) as sitemap_response:
                                        if sitemap_response.status == 200:
                                            sitemap_content = await sitemap_response.text()
                                            urls = self._parse_sitemap_xml(sitemap_content)

                                            # Check if it's a sitemap index (returns sitemap URLs)
                                            # or a regular sitemap (returns page URLs)
                                            if urls:
                                                # If URLs look like sitemap URLs (contain "sitemap" in path),
                                                # recursively fetch them
                                                for url in urls:
                                                    if "sitemap" in url.lower():
                                                        # It's another sitemap index - fetch it
                                                        try:
                                                            async with session.get(
                                                                url,
                                                                headers={
                                                                    "User-Agent": self.user_agent
                                                                },
                                                            ) as nested_response:
                                                                if nested_response.status == 200:
                                                                    nested_content = (
                                                                        await nested_response.text()
                                                                    )
                                                                    nested_urls = (
                                                                        self._parse_sitemap_xml(
                                                                            nested_content
                                                                        )
                                                                    )
                                                                    discovered_urls.extend(
                                                                        nested_urls
                                                                    )
                                                        except Exception as e:
                                                            logger.debug(
                                                                f"Failed to fetch nested sitemap {url}: {e}"
                                                            )
                                                    else:
                                                        # It's a regular page URL
                                                        discovered_urls.append(url)
                                except Exception as e:
                                    logger.debug(f"Failed to fetch sitemap {sitemap_url}: {e}")
                except Exception as e:
                    logger.debug(f"Failed to fetch robots.txt from {robots_url}: {e}")
        except Exception as e:
            logger.debug(f"Error discovering sitemaps for {base_url}: {e}")

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
        """Check if URL domain is allowed."""
        if not self.allowed_domains:
            return True

        parsed = self._parse_url(url)
        domain = self._normalize_domain(parsed.netloc)

        # Check if domain matches any allowed domain
        return any(
            domain == self._normalize_domain(allowed)
            or domain.endswith("." + self._normalize_domain(allowed))
            for allowed in (self.allowed_domains or set())
        )

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

        if url in self.visited_urls or url in self.failed_urls:
            logger.debug(f"❌ URL {url} rejected: already visited or failed")
            return False

        # Parse URL once and reuse for multiple checks
        parsed_url = self._parse_url(url)
        url_domain = self._normalize_domain(parsed_url.netloc)

        # Check allowed domain
        if self.allowed_domains:
            normalized_allowed = [
                self._normalize_domain(allowed) for allowed in self.allowed_domains
            ]
            is_allowed = any(
                url_domain == normalized or url_domain.endswith("." + normalized)
                for normalized in normalized_allowed
            )
            if not is_allowed:
                logger.debug(
                    f"❌ URL {url} rejected: domain '{url_domain}' not in allowed domains: {normalized_allowed}"
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
            normalized = self.normalize_url(absolute)
            entry = {"url": normalized, "text": (text or "").strip()}
            if rel:
                entry["rel"] = rel
            links.append(entry)

        # Standard anchors and common data-* attributes
        for a in soup.find_all("a"):
            href = a.get("href")
            text = a.get_text().strip() if a.get_text() else ""
            rel_attr = a.get("rel")
            rel = (
                " ".join(rel_attr).lower()
                if isinstance(rel_attr, (list, tuple))
                else (str(rel_attr).lower() if rel_attr else "")
            )
            add_url(str(href) if href else None, text, rel or None)
            for attr in ("data-href", "data-url", "data-link", "data-target"):
                attr_value = a.get(attr)
                if attr_value:
                    add_url(str(attr_value), text, rel or None)

        # <link> tags (canonical, alternate, etc.)
        for link_tag in soup.find_all("link", href=True):
            rel = " ".join(link_tag.get("rel") or [])
            href_value = link_tag.get("href")
            add_url(str(href_value) if href_value else None, f"link:{rel}", rel)

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
        for link in unique_links[:20]:
            logger.debug(f"  - {link['url']} ({link['text'][:60]})")
        if len(unique_links) > 20:
            logger.debug(f"  ... and {len(unique_links) - 20} more links")

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
        """
        Internal method to fetch and process a single page (without retry logic).

        This is the actual implementation that will be retried on transient errors.
        """
        await self.rate_limit(url)

        try:
            # Check if we should ignore robots.txt for this domain
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]

            should_check_robots = (
                self.respect_robots_txt and domain not in self.ignore_robots_for_domains
            )

            # Check robots.txt
            if should_check_robots and self.robots_checker:
                is_allowed, reason = await self.robots_checker.can_fetch(session, url)
                if not is_allowed:
                    logger.warning(f"URL blocked by robots.txt: {url} - Reason: {reason}")
                    return CrawlResult(
                        url=url,
                        title="",
                        content="",
                        markdown="",
                        metadata={},
                        status_code=403,
                        success=False,
                        error_message=f"Blocked by robots.txt: {reason}",
                    )

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {"User-Agent": self.user_agent}

            # Add HTTP cache headers (If-None-Match, If-Modified-Since)
            cache_headers = self.http_cache.get_cache_headers(url)
            headers.update(cache_headers)

            # Use proxy if configured
            request_args = {
                "timeout": timeout,
                "headers": headers,
            }
            if self.proxy:
                request_args["proxy"] = self.proxy

            async with session.get(url, **request_args) as response:
                # Handle 304 Not Modified - content hasn't changed
                if response.status == 304:
                    logger.debug(f"Content not modified (304) for {url}, using cached metadata")
                    # Return a result indicating no change (but still successful)
                    # The caller can decide whether to process this or skip
                    return CrawlResult(
                        url=url,
                        title="",
                        content="",
                        markdown="",
                        metadata={"cached": True, "status": "not_modified"},
                        status_code=304,
                        success=True,
                        error_message=None,
                    )

                # Update cache with ETag/Last-Modified if present
                if response.status == 200:
                    self.http_cache.update_cache(url, response)

                content_type = response.headers.get("content-type", "").lower()

                # Process HTML, plain text, and XML content
                if (
                    "text/html" not in content_type
                    and "text/plain" not in content_type
                    and "text/xml" not in content_type
                    and "application/xml" not in content_type
                    and "application/rss+xml" not in content_type
                    and "application/atom+xml" not in content_type
                ):
                    # Optionally support binary parsing (PDF/Office) when enabled
                    if self.enable_binary_crawling and (
                        "application/pdf" in content_type or content_type.startswith("application/")
                    ):
                        # Read raw bytes
                        raw_bytes = await response.read()
                        # Try to extract text using DocumentProcessor (opt-in)
                        from src.document_processor import DocumentProcessor

                        processor = DocumentProcessor(
                            max_content_length=5000,
                            enable_binary_parsing=True,
                            prefer_tika=self.use_tika_for_binaries,
                            prefer_pdfminer=self.use_pdfminer_for_pdf,
                        )

                        filename = urlparse(url).path.split("/")[-1] or "document"
                        text_content = await processor._extract_text(
                            raw_bytes, filename, content_type
                        )

                        if not text_content:
                            return CrawlResult(
                                url=url,
                                title="",
                                content="",
                                markdown="",
                                metadata={"content-type": content_type},
                                status_code=response.status,
                                success=False,
                                error_message=f"Unsupported or unparseable binary content type: {content_type}",
                            )

                        # Build simple metadata and markdown
                        title_text = filename
                        lines = text_content.splitlines()
                        markdown_content = text_content

                        metadata = {
                            "content-type": content_type,
                            "estimated_title": title_text,
                            "line_count": len(lines),
                            "character_count": len(text_content),
                        }

                        discovered_links = []

                        # Analyze for legal content
                        is_legal, legal_score, indicators = self.content_analyzer.analyze_content(
                            text_content, title_text, metadata
                        )

                        if is_legal:
                            self.stats.legal_documents_found += 1

                        effective_url = self._choose_effective_url(url, metadata)
                        if effective_url != url:
                            metadata["canonical_resolved"] = True
                            logger.debug(
                                f"Returning canonical URL for result: {effective_url} (original: {url})"
                            )
                            url = effective_url

                        return CrawlResult(
                            url=url,
                            title=title_text,
                            content=text_content,
                            markdown=markdown_content,
                            metadata=metadata,
                            status_code=response.status,
                            success=True,
                            error_message=None,
                            legal_score=legal_score,
                            discovered_links=discovered_links,
                        )

                    return CrawlResult(
                        url=url,
                        title="",
                        content="",
                        markdown="",
                        metadata={},
                        status_code=response.status,
                        success=False,
                        error_message=f"Unsupported content type: {content_type}",
                    )

                text_response = await response.text()

                # Handle HTML content
                if "text/html" in content_type:
                    soup = BeautifulSoup(text_response, "html.parser")

                    # Extract data
                    title = soup.find("title")
                    title_text = title.get_text().strip() if title else ""

                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()

                    # Get text content
                    text_content = soup.get_text()
                    text_content = re.sub(r"\s+", " ", text_content).strip()

                    # Check if we should fallback to browser for dynamic content
                    # Fallback criteria:
                    # 1. use_browser is enabled
                    # 2. Content is very short (likely bootstrap only)
                    # 3. Content contains JS required markers
                    js_required_markers = [
                        "javascript is required",
                        "enable javascript",
                        "you need to enable javascript",
                        "please enable js",
                    ]

                    should_fallback = self.use_browser and (
                        len(text_content) < 500
                        or any(marker in text_content.lower() for marker in js_required_markers)
                    )

                    if should_fallback:
                        logger.info(
                            f"🔄 Detected dynamic content or short page, trying browser: {url}"
                        )
                        browser_result = await self._fetch_with_browser(url)

                        # If browser fetch succeeded, use it
                        if browser_result.success:
                            return browser_result

                        # Browser fetch failed, fall back to static HTML parsing
                        logger.info(
                            f"⚠️ Browser fetch failed, falling back to static HTML parsing: {url}"
                        )
                        # Continue with static HTML parsing below (don't return)

                    # Convert to markdown
                    markdown_content = markdownify.markdownify(str(soup), heading_style="ATX")

                    # Extract metadata
                    metadata = self.extract_metadata(soup)

                    # Extract links
                    discovered_links = self.extract_links(soup, url)

                    # If page has a canonical URL, prefer it for the result URL (when appropriate)
                    resolved_url = self._choose_effective_url(url, metadata)
                    if resolved_url != url:
                        metadata["canonical_resolved"] = True
                        logger.debug(
                            f"Using canonical URL for result: {resolved_url} (original: {url})"
                        )
                    url = resolved_url

                # Handle plain text content
                elif "text/plain" in content_type:
                    # For plain text, use the content as-is
                    text_content = text_response.strip()

                    # Try to extract title from first line or URL
                    lines = text_content.split("\n")
                    title_text = ""

                    # Look for title indicators in first few lines
                    for line in lines[:5]:
                        line = line.strip()
                        if line and (
                            any(
                                keyword in line.lower()
                                for keyword in [
                                    "privacy",
                                    "terms",
                                    "policy",
                                    "agreement",
                                    "license",
                                    "legal",
                                    "notice",
                                ]
                            )
                            or len(line) < 100  # Short lines might be titles
                        ):
                            title_text = line
                            break

                    # Fallback: extract title from URL
                    if not title_text:
                        url_parts = url.rstrip("/").split("/")
                        if url_parts:
                            title_text = url_parts[-1].replace("-", " ").replace("_", " ").title()

                    # Use text content as markdown (it's already plain text)
                    markdown_content = text_content

                    # Basic metadata for plain text
                    metadata = {
                        "content-type": content_type,
                        "estimated_title": title_text,
                        "line_count": len(lines),
                        "character_count": len(text_content),
                    }

                    # No links can be extracted from plain text
                    discovered_links = []

                # Handle XML content (sitemaps, RSS/Atom feeds)
                elif (
                    "text/xml" in content_type
                    or "application/xml" in content_type
                    or "application/rss+xml" in content_type
                    or "application/atom+xml" in content_type
                ):
                    # Parse XML to extract URLs
                    discovered_links = []
                    text_content = ""
                    title_text = ""

                    try:
                        # Try parsing as sitemap first
                        sitemap_urls = self._parse_sitemap_xml(text_response)
                        if sitemap_urls:
                            logger.info(
                                f"📄 Parsed sitemap/RSS feed, found {len(sitemap_urls)} URLs"
                            )
                            discovered_links = [
                                {"url": self.normalize_url(url), "text": ""} for url in sitemap_urls
                            ]
                            title_text = "XML Sitemap or Feed"
                            text_content = f"Contains {len(sitemap_urls)} URLs"
                    except Exception as e:
                        logger.debug(f"Failed to parse XML content from {url}: {e}")
                        # Fallback to treating as plain text
                        text_content = text_response.strip()
                        title_text = "XML Document"

                    # Basic metadata for XML
                    metadata = {
                        "content-type": content_type,
                        "estimated_title": title_text,
                        "link_count": len(discovered_links),
                    }

                # Analyze content for legal relevance (works for HTML, plain text, and XML)
                is_legal, legal_score, indicators = self.content_analyzer.analyze_content(
                    text_content, title_text, metadata
                )

                if is_legal:
                    self.stats.legal_documents_found += 1

                # Ensure the URL we return is the preferred canonical when appropriate
                effective_url = self._choose_effective_url(url, metadata)
                if effective_url != url:
                    metadata["canonical_resolved"] = True
                    logger.debug(
                        f"Returning canonical URL for result: {effective_url} (original: {url})"
                    )
                    url = effective_url

                return CrawlResult(
                    url=url,
                    title=title_text,
                    content=text_content,
                    markdown=markdown_content,
                    metadata=metadata,
                    status_code=response.status,
                    success=True,
                    legal_score=legal_score,
                    discovered_links=discovered_links,
                )
        except aiohttp.ClientResponseError as e:
            # Handle HTTP errors
            status = e.status
            error_msg = f"HTTP {status}: {e.message}"

            # Check if this is a retryable error
            if status >= 500 or status == 429:
                # Server error or rate limit - will be retried
                raise
            else:
                # Client error (4xx) - don't retry
                logger.warning(f"Client error fetching {url}: {error_msg}")
                return CrawlResult(
                    url=url,
                    title="",
                    content="",
                    markdown="",
                    metadata={},
                    status_code=status,
                    success=False,
                    error_message=error_msg,
                )
        except (aiohttp.ClientError, TimeoutError):
            # Network/timeout errors - will be retried
            raise
        except Exception as e:
            # Other errors - don't retry
            logger.error(f"Unexpected error fetching {url}: {e}")
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

    def generate_potential_legal_urls(self, base_url: str) -> list[str]:
        """Generate potential legal document URLs based on common patterns."""
        parsed = urlparse(base_url)
        domain = parsed.netloc
        scheme = parsed.scheme

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

        # Generate URLs for each path
        potential_urls = []
        for path in legal_paths:
            url = f"{scheme}://{domain}{path}"
            potential_urls.append(url)

        return potential_urls

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

            if self.strategy == "bfs":
                self.url_queue.append((url, depth + 1))
                logger.debug(f"Added to BFS queue: {url} (depth: {depth + 1})")
            elif self.strategy == "dfs":
                self.url_stack.append((url, depth + 1))
                logger.debug(f"Added to DFS stack: {url} (depth: {depth + 1})")
            elif self.strategy == "best_first":
                score = self.url_scorer.score_url(url, anchor_text=anchor_text)
                heapq.heappush(self.url_priority_queue, (-score, url, depth + 1))
                logger.debug(
                    f"Added to Best-First queue: {url} (score: {score:.2f}, text: {anchor_text})"
                )

        # If we're at depth 0 (starting page), also add potential legal URLs
        if depth == 0:
            potential_legal_urls = self.generate_potential_legal_urls(base_url)
            logger.info(f"🔍 Generated {len(potential_legal_urls)} potential legal URLs")

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

                if self.strategy == "bfs":
                    self.url_queue.append((url, 1))
                    logger.debug(f"Added potential legal URL to BFS queue: {url}")
                elif self.strategy == "dfs":
                    self.url_stack.append((url, 1))
                    logger.debug(f"Added potential legal URL to DFS stack: {url}")
                elif self.strategy == "best_first":
                    # For generated URLs, we don't have anchor text
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
                # Discover sitemaps early (before main loop) to seed queue
                try:
                    sitemap_urls = await self._discover_sitemap_urls(session, base_url)
                    if sitemap_urls:
                        logger.info(f"🔍 Found {len(sitemap_urls)} sitemap URLs for {base_url}")
                        for url in sitemap_urls:
                            if not self.should_crawl_url(url, base_url, 1):
                                continue
                            if self.strategy == "bfs":
                                self.url_queue.append((url, 1))
                            elif self.strategy == "dfs":
                                self.url_stack.append((url, 1))
                            elif self.strategy == "best_first":
                                score = self.url_scorer.score_url(url, anchor_text=None)
                                heapq.heappush(self.url_priority_queue, (-score, url, 1))
                except Exception:
                    logger.debug("Sitemap discovery failed; continuing without sitemap")

                # Semaphore to limit concurrent requests
                semaphore = asyncio.Semaphore(self.max_concurrent)

                async def process_url(url: str, depth: int) -> CrawlResult:
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
                    tasks = [process_url(url, depth) for url, depth in batch]
                    batch_results = await asyncio.gather(*tasks)

                    # Process results
                    for result, (url, depth) in zip(batch_results, batch, strict=False):
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
                                f"{url} (Legal: {result.legal_score:.1f}) "
                                f"Found: {len(result.discovered_links)} links"
                            )
                        else:
                            self.stats.failed_urls += 1
                            self.failed_urls.add(url)
                            logger.warning(f"❌ Failed: {url} - {result.error_message}")

                    # Progress update
                    if self.stats.crawled_urls % 10 == 0:
                        logger.info(
                            f"📊 Progress: {self.stats.crawled_urls} crawled, "
                            f"{self.stats.legal_documents_found} legal docs, "
                            f"{self.stats.crawl_rate:.1f} pages/sec"
                        )

            # Final statistics
            logger.info("🎉 Crawl completed!")
            logger.info(f"📊 Total URLs: {self.stats.total_urls}")
            logger.info(f"✅ Successfully crawled: {self.stats.crawled_urls}")
            logger.info(f"❌ Failed: {self.stats.failed_urls}")
            logger.info(f"⚖️  Legal documents found: {self.stats.legal_documents_found}")
            logger.info(f"⏱️  Total time: {self.stats.elapsed_time:.1f} seconds")
            logger.info(f"🚀 Average rate: {self.stats.crawl_rate:.1f} pages/sec")

            # Sort results by legal score (highest first)
            self.results.sort(key=lambda x: x.legal_score, reverse=True)

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

        # Log detailed analysis
        if result.success:
            logger.info(f"✅ Successfully fetched: {url}")
            logger.info(f"📄 Title: {result.title}")
            logger.info(f"⚖️ Legal Score: {result.legal_score}")
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
        logger.info(f"   Legal Score: {result.legal_score:.1f}")
        logger.info(f"   Content Length: {len(result.content)} chars")
        if not result.success:
            logger.info(f"   Error: {result.error_message}")
        return

    base_url = sys.argv[1]

    results = await crawl_for_legal_documents(
        base_url=base_url, max_depth=4, max_pages=200, strategy="bfs"
    )

    # Display all results with scores
    logger.info(f"\n📊 All crawled pages ({len(results)} total):")
    for i, result in enumerate(results, 1):
        logger.info(f"{i:3d}. {result.title or 'Untitled'[:50]}")
        logger.info(f"     URL: {result.url}")
        logger.info(f"     Legal Score: {result.legal_score:.1f}")
        logger.info("")

    # Display legal documents
    legal_docs = [r for r in results if r.legal_score >= 3.0]

    logger.info(f"\n🎯 Found {len(legal_docs)} potential legal documents:")
    for result in legal_docs:
        logger.info(f"📄 {result.title or 'Untitled'}")
        logger.info(f"   URL: {result.url}")
        logger.info(f"   Legal Score: {result.legal_score:.1f}")
        logger.info(f"   Content Length: {len(result.content)} chars")
        logger.info("")

    # Display moderate scoring pages that might be legal but scored lower
    moderate_docs = [r for r in results if 1.0 <= r.legal_score < 3.0]

    if moderate_docs:
        logger.info(f"\n📋 Found {len(moderate_docs)} pages with moderate legal scores:")
        for result in moderate_docs[:10]:  # Top 10 moderate scoring
            logger.info(f"📄 {result.title or 'Untitled'}")
            logger.info(f"   URL: {result.url}")
            logger.info(f"   Legal Score: {result.legal_score:.1f}")
            logger.info("")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(main())
