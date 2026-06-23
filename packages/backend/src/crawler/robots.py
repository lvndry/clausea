"""Robots.txt fetcher, parser, and compliance checker for the crawl frontier.

**What it does**
For every domain the crawler encounters, ``RobotsTxtChecker`` retrieves
``/robots.txt`` (once, then cached), parses it into:
- A list of ``(user_agent_pattern, path_regex, allow)`` tuples.
- An extracted ``crawl_delay`` in seconds for that user agent.

The ``is_allowed(url, user_agent)`` method iterates rule tuples in reverse order
(robots.txt priority — last matching rule wins) and returns ``True``/``False``.

**What it contains**
- ``RobotsTxtChecker`` with ``is_allowed``, ``fetch_robots``, and ``parse_robots``.
- ``_parse_robots_txt(text, user_agent)``: returns ``(rules, crawl_delay)``.
- ``_wildcard_to_regex(pattern)``: converts robots.txt wildcard to Python regex.
- ``self._cache: dict[str, RobotsTxtEntry]`` — per-domain parsed results.

**What it allows/prevents**
Allows the crawler to respect site operator crawl policies.  Prevents crawling
directories the site explicitly disallows (e.g. ``/login``, ``/admin``, API
endpoints) and enforces ``Crawl-delay`` directives.
"""

import re
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

import aiohttp

from src.core.logging import get_logger
from src.crawler.constants import DEFAULT_USER_AGENT

logger_robots = get_logger(__name__, component="crawler:robots")


class RobotsTxtChecker:
    """Checks robots.txt compliance with improved parsing."""

    def __init__(self, max_cache_size: int = 1000) -> None:
        self.robots_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max_cache_size = max_cache_size
        self.user_agent = DEFAULT_USER_AGENT
        self.user_agent_patterns = [
            "*",
            "all",
            "any",
            "bot",
            "crawler",
            "spider",
            "robot",
            "crawl",
            "spider",
            "bot",
        ]

    async def can_fetch(self, session: aiohttp.ClientSession, url: str) -> tuple[bool, str]:
        try:
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            robots_url = f"{base_url}/robots.txt"

            if base_url not in self.robots_cache:
                try:
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
                            parsed_rules = {"allow_all": True}
                except Exception as e:
                    logger_robots.debug(
                        f"error fetching robots.txt from {robots_url}: {e}; allowing all requests"
                    )
                    parsed_rules = {"allow_all": True}

                self._add_to_cache(base_url, parsed_rules)

            robots_rules = self.robots_cache.pop(base_url)
            self.robots_cache[base_url] = robots_rules
            if robots_rules.get("allow_all", False):
                return True, "No robots.txt rules found"

            return self._check_url_allowed(url, robots_rules)

        except Exception as e:
            logger_robots.warning(f"error checking robots.txt for {url}: {e}")
            return True, f"Error checking robots.txt: {str(e)}"

    def _add_to_cache(self, base_url: str, rules: dict[str, Any]) -> None:
        if len(self.robots_cache) >= self.max_cache_size:
            self.robots_cache.popitem(last=False)
        self.robots_cache[base_url] = rules

    def clear_cache(self) -> None:
        self.robots_cache.clear()

    def _parse_robots_txt(self, content: str) -> dict[str, Any]:
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        logger_robots.debug(f"parsing robots.txt: {len(lines)} directive lines")

        user_agents: dict[str, dict[str, Any]] = {}
        current_user_agent = None
        sitemaps: list[str] = []

        for line in lines:
            if line.startswith("#") or not line:
                continue

            if ":" in line:
                directive, value = line.split(":", 1)
                directive = directive.strip().lower()
                value = value.strip()

                if directive == "user-agent":
                    current_user_agent = value.lower()
                    if current_user_agent not in user_agents:
                        user_agents[current_user_agent] = {"disallow": [], "allow": []}
                elif directive == "disallow" and current_user_agent:
                    if value:
                        user_agents[current_user_agent]["disallow"].append(value)
                elif directive == "allow" and current_user_agent:
                    user_agents[current_user_agent]["allow"].append(value)
                elif directive == "crawl-delay" and current_user_agent:
                    try:
                        delay = float(value)
                        user_agents[current_user_agent]["crawl_delay"] = delay
                    except ValueError:
                        logger_robots.warning(f"invalid crawl-delay value in robots.txt: {value}")
                elif directive == "sitemap":
                    sitemaps.append(value)

        parsed: dict[str, Any] = {"user_agents": user_agents}
        if sitemaps:
            parsed["sitemaps"] = sitemaps
        return parsed

    def _resolve_applicable_rules(self, robots_rules: dict[str, Any]) -> dict[str, Any] | None:
        user_agents = robots_rules.get("user_agents", {})

        user_agent_lower = self.user_agent.lower()
        if user_agent_lower in user_agents:
            return user_agents[user_agent_lower]

        matching = [
            ua
            for ua in user_agents
            if ua in user_agent_lower and ua not in self.user_agent_patterns
        ]
        if matching:
            best = max(matching, key=len)
            return user_agents[best]

        for pattern in self.user_agent_patterns:
            if pattern in user_agents:
                return user_agents[pattern]

        return None

    def get_crawl_delay(self, url: str) -> float | None:
        """Return robots.txt Crawl-delay for this URL's origin, if cached and set."""
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        robots_rules = self.robots_cache.get(base_url)
        if not robots_rules or robots_rules.get("allow_all"):
            return None

        applicable_rules = self._resolve_applicable_rules(robots_rules)
        if not applicable_rules:
            return None

        delay = applicable_rules.get("crawl_delay")
        if delay is None:
            return None
        try:
            return max(0.0, float(delay))
        except (TypeError, ValueError):
            return None

    def _check_url_allowed(self, url: str, robots_rules: dict[str, Any]) -> tuple[bool, str]:
        parsed = urlparse(url)
        path = parsed.path
        if not path:
            path = "/"

        applicable_rules = self._resolve_applicable_rules(robots_rules)
        if not applicable_rules:
            return True, "No matching rules found"

        for allow_pattern in applicable_rules.get("allow", []):
            if self._path_matches_pattern(path, allow_pattern):
                return True, f"Explicitly allowed by pattern: {allow_pattern}"

        for disallow_pattern in applicable_rules.get("disallow", []):
            if self._path_matches_pattern(path, disallow_pattern):
                for allow_pattern in applicable_rules.get("allow", []):
                    if self._path_matches_pattern(path, allow_pattern) and len(allow_pattern) > len(
                        disallow_pattern
                    ):
                        return True, f"Allowed by more specific pattern: {allow_pattern}"
                return False, f"Blocked by pattern: {disallow_pattern}"

        if applicable_rules.get("disallow"):
            return True, "No matching disallow rules"

        return True, "No blocking rules found"

    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        if not pattern:
            return False
        if pattern == "/":
            return True

        if "*" in pattern:
            regex_pattern = re.escape(pattern).replace(r"\*", ".*")
            return bool(re.match(f"^{regex_pattern}$", path))

        if pattern.endswith("*"):
            return path.startswith(pattern[:-1])

        if pattern.startswith("*"):
            return path.endswith(pattern[1:])

        return path.startswith(pattern)
