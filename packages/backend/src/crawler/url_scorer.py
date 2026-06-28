"""Heuristic URL scorer that ranks candidate URLs by policy-document relevance.

**What it does**
Assigns a cumulative relevance score to each *candidate URL* before the crawler
fetches it. Signals come only from the URL string and optional link anchor text —
never from fetched page HTML, titles, or body content. (Post-fetch classification
uses separate content pipelines.)

Scores path segments, query parameters (excluding redirect params), URL fragments,
and ``anchor_text`` when the crawler is following a discovered link.

**What it contains**
- ``URLScorer`` with ``score_url`` / ``score_urls``.
- ``compiled_high_value_patterns``: multi-word policy phrases in URL text.
- ``compiled_path_patterns``: weighted path-segment regexes.
- ``legal_keywords``: per-token weights applied to URL path/query/fragment words
  and anchor-text words (see ``score_url``). Not used on page content.
- ``is_strong_policy_path`` / ``is_non_policy_section``: hard frontier rules.

**What it allows/prevents**
Prioritises high-value URLs on the crawl frontier when the page budget is tight.
Prevents wasting browser renders on login walls, gallery templates, and glossary
``/terms/`` paths before the content classifier runs.
"""

import re
from functools import lru_cache
from urllib.parse import parse_qsl, urlparse

from src.crawler.constants import (
    _REDIRECT_QUERY_KEYS,
)


class URLScorer:
    """Scores candidate URLs for policy-document relevance (pre-fetch only)."""

    def __init__(self) -> None:
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
                # Direct policy slugs — terminal paths like /privacy, /tos
                r"/privacy/?": 5.0,
                r"/terms/?": 4.5,
                r"/tos/?": 5.0,
                r"/dpa/?": 5.0,
                r"/data-processing-addendum/?": 5.0,
                # Regulatory and addendum segments
                r"/gdpr/?": 4.5,
                r"/ccpa/?": 4.5,
                r"/addendum/?": 4.5,
                # Policy section hubs (listing pages, not a specific doc type)
                r"/legal/?": 4.0,
                r"/policy/?": 4.0,
                r"/policies/?": 4.0,
                r"/agreement/?": 3.5,
                r"/compliance/?": 3.5,
                r"/cookie/?": 4.0,
                r"/data-processing/?": 4.0,
                r"/subprocessors/?": 4.0,
                # Weak contextual signals
                r"/security/?": 3.0,
                r"/disclaimer/?": 3.0,
                r"/company/?": 3.0,
                r"/vendors/?": 3.0,
                r"/suppliers/?": 3.0,
                r"/transparency/?": 3.5,
                r"/[a-f0-9-]{32,}": 2.0,
                # Known site-section + policy-type layouts (stack with slugs above)
                r"/company/legal/?": 4.5,
                r"/company/privacy/?": 4.5,
                r"/company/terms/?": 4.5,
                r"/company/tos/?": 4.5,
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
                r"/policies/privacy/?": 4.5,
                r"/policies/terms/?": 4.5,
                r"/policies/cookies/?": 4.5,
                r"/legal/policies/?": 4.0,
                r"/legal/policies/privacy/?": 4.5,
                r"/legal/policies/terms/?": 4.5,
                r"/legal/policies/cookies/?": 4.5,
                r"/policy/privacy/?": 4.5,
                r"/policy/terms/?": 4.5,
                r"/policy/cookies/?": 4.5,
                r"/policy/cookie/?": 4.5,
                r"/policy/terms-of-service/?": 4.5,
                r"/policy/terms-of-use/?": 4.5,
                r"/policy/data/?": 4.0,
                r"/policy/gdpr/?": 4.5,
                r"/policy/ccpa/?": 4.5,
                r"/policy/community/?": 4.0,
                r"/policy/safety/?": 4.0,
                r"/policy/copyright/?": 4.0,
            }.items()
        }

        self.word_pattern = re.compile(r"\b\w+\b")

        self._glossary_terms_re = re.compile(
            r"/[^/]+/terms/"
            r"(?!service|use|conditions|sale|payment|payments|business|"
            r"general|user|website|privacy|cookie|cookies|policy|of-|and-)"
            r"[^/]+",
            re.IGNORECASE,
        )
        self._terms_signal_weight = 8.5

        self._non_policy_section_re = re.compile(
            r"^/(?:templates?|universe|marketplace|gallery|showcase|examples?)(?:/|$)",
            re.IGNORECASE,
        )
        self._auth_path_re = re.compile(
            r"(?:^|/)(?:log[-_]?in|log[-_]?out|sign[-_]?in|sign[-_]?out|sign[-_]?up|"
            r"signon|register|oauth2?|openid|sso|saml|authorize|authentication)(?:/|$)",
            re.IGNORECASE,
        )

        self._strong_policy_path_re = re.compile(
            r"(?:^|/)(?:privacy|terms|tos|legal|cookies?|gdpr|ccpa|dpa|"
            r"data-processing(?:-addendum)?|sub-?processors?|site-policy|policies|"
            r"policy|eula|acceptable-use|community-guidelines)(?:[-_/]|$)",
            re.IGNORECASE,
        )

        self.legal_keywords = {
            # Token weights for URL surfaces only (path, query, fragment, anchor text).
            # Applied in score_url — not on fetched page title/body/markdown.
            # Direct policy tokens (align with 5.0 path slugs: /privacy, /tos, /dpa)
            "privacy": 5.0,
            "dpa": 5.0,
            "privacy-policy": 5.0,
            "terms-of-service": 5.0,
            "terms-and-conditions": 5.0,
            "terms-of-use": 5.0,
            # Strong regulatory / addendum (align with 4.5 path segments)
            "terms": 4.0,
            "addendum": 4.5,
            "cookie-policy": 4.5,
            "gdpr": 4.5,
            "ccpa": 4.5,
            "hipaa": 4.5,
            "coppa": 4.5,
            "pipeda": 4.5,
            # Section / hub tokens (align with 4.0 path hubs: /legal, /policy, /cookie)
            "policy": 4.0,
            "cookie": 4.0,
            "cookies": 4.0,
            "subprocessors": 4.0,
            # Medium contextual (align with 3.5 path segments)
            "legal": 3.5,
            "agreement": 3.5,
            "conditions": 3.5,
            "compliance": 3.5,
            "processor": 3.5,
            "subprocessor": 3.5,
            "protection": 3.5,
            "dmca": 3.5,
            "transparency": 3.5,
            # Weak contextual (align with 3.0 path segments)
            "disclaimer": 3.0,
            "security": 3.0,
            "safety": 3.0,
            "copyright": 3.0,
            "consent": 3.0,
            "license": 3.0,
            "data": 2.5,
            "processing": 2.5,
            # Loose / noisy tokens — kept low to avoid inflating unrelated URLs
            "notice": 2.5,
            "rights": 2.5,
            "rules": 2.5,
            "trust": 2.0,
            "partners": 2.0,
            "vendor": 2.5,
            "suppliers": 2.5,
            "associate": 2.0,
            "report": 2.0,
            "company": 1.0,
            # Penalties — not policy documents
            "contact": -1.0,
            "news": -1.0,
        }

    @lru_cache(maxsize=10000)  # noqa: B019 - Cache is bounded and per-instance
    def score_url(self, url: str, anchor_text: str | None = None) -> float:
        """Score a candidate URL from its string and optional link anchor text.

        Uses only URL components (path, non-redirect query params, fragment) and
        ``anchor_text`` when scoring a discovered link. Does not read page content.

        ``legal_keywords`` contribute when tokens appear as URL/anchor words (full
        weight), as substrings in the raw path (0.8×), or embedded in hyphenated
        path segments (0.8×). Anchor-text keyword hits use 2.0× the listed weight.
        """
        url_lower = url.lower()
        parsed = urlparse(url_lower)
        path = parsed.path

        if self._auth_path_re.search(path):
            return 0.0

        scoring_query = " ".join(
            f"{key} {value}"
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in _REDIRECT_QUERY_KEYS
        )
        scoring_url = f"{path} {scoring_query}".strip()

        score = 0.0

        for pattern, weight in self.compiled_high_value_patterns.items():
            if pattern.search(scoring_url):
                score += weight

        if anchor_text:
            anchor_lower = anchor_text.lower()
            anchor_words = self.word_pattern.findall(anchor_lower)

            for pattern, weight in self.compiled_high_value_patterns.items():
                if pattern.search(anchor_lower):
                    score += weight * 2.5

            for word in anchor_words:
                if word in self.legal_keywords:
                    score += self.legal_keywords[word] * 2.0

        for pattern, weight in self.compiled_path_patterns.items():
            if pattern.search(path):
                score += weight

        url_text = (
            f"{path} {scoring_query} {parsed.fragment}".replace("/", " ")
            .replace("-", " ")
            .replace("_", " ")
        )
        words = self.word_pattern.findall(url_text)

        scored_keywords = set()

        for word in words:
            if word in self.legal_keywords:
                score += self.legal_keywords[word]
                scored_keywords.add(word.lower())

        path_lower = path.lower()
        for keyword, weight in self.legal_keywords.items():
            if weight > 0 and keyword not in scored_keywords:
                if keyword in path_lower:
                    score += weight * 0.8
                    scored_keywords.add(keyword)
                for word in words:
                    word_lower = word.lower()
                    if (
                        keyword in word_lower
                        and word_lower != keyword
                        and keyword not in scored_keywords
                    ):
                        score += weight * 0.8
                        scored_keywords.add(keyword)

        if self._glossary_terms_re.search(path):
            score -= self._terms_signal_weight

        if self.is_non_policy_section(url):
            return 0.0

        return max(0.0, score)

    def is_non_policy_section(self, url: str) -> bool:
        return bool(self._non_policy_section_re.search(urlparse(url.lower()).path))

    @lru_cache(maxsize=10000)  # noqa: B019
    def is_strong_policy_path(self, url: str) -> bool:
        return bool(self._strong_policy_path_re.search(urlparse(url.lower()).path))
