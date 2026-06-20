"""Filter weak or off-topic evidence quotes before surfacing as topic citations.

Term materiality (standard vs material risk) is handled by LLM labels in
``standard_terms`` / ``term_materiality_classifier`` — not here.

This module uses lightweight lexical heuristics only for quote-to-topic
relevance scoring (0–100). Limits:
- Cannot judge nuance or mixed clauses; token/keyword overlap only.
- ``_FOREIGN_TOPIC_SIGNALS`` rejects quotes that clearly belong to another
  insight category (e.g. arbitration quote cited under data_sharing).
- ``_BOILERPLATE_PATTERNS`` drops generic cookie-consent filler, not legal terms.
- Prefer substantive quotes with topic keyword overlap; see ``score_evidence_relevance``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from src.models.document import EvidenceSpan, InsightCategory

# Generic cookie/consent boilerplate that rarely substantiates a policy finding.
_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"cookies?\s+are\s+(small\s+)?(text\s+files?|files)",
        r"what\s+are\s+cookies",
        r"cookie-?based\s+opt-?outs?\s+are\s+not\s+effective",
        r"placed\s+in\s+(your\s+)?(device\s+)?browsers?",
        r"use\s+(your\s+)?browser\s+settings",
        r"click\s+(the\s+)?(link\s+to\s+)?manage\s+cookies",
        r"manage\s+cookies\s+(link|footer|tool|banner|preferences)",
        r"cookie\s+consent\s+(tool|banner|manager)",
        r"eu\s+cookie\s+consent",
        r"for\s+more\s+information\s+about\s+cookies",
        r"please\s+see\s+our\s+cookie\s+policy",
    )
)

_PROCEDURAL_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^manage\s+cookies\b",
        r"^cookie\s+settings\b",
        r"^how\s+to\s+(disable|manage|control)\s+cookies\b",
    )
)

# Strong lexical signals that a quote belongs to another insight category.
_FOREIGN_TOPIC_SIGNALS: tuple[tuple[str, InsightCategory], ...] = (
    ("binding arbitration", "dispute_resolution"),
    ("class action waiver", "dispute_resolution"),
    ("class action", "dispute_resolution"),
    ("jury trial", "dispute_resolution"),
    ("arbitration clause", "dispute_resolution"),
    ("arbitration", "dispute_resolution"),
    ("repeat infringer", "termination_consequences"),
    ("dmca", "termination_consequences"),
    ("copyright takedown", "termination_consequences"),
    ("account termination", "termination_consequences"),
    ("terminate your account", "termination_consequences"),
    ("non-assignable", "content_ownership"),
    ("not assignable", "content_ownership"),
    ("intellectual property rights", "content_ownership"),
    ("intellectual property", "content_ownership"),
    ("copyright infringement", "content_ownership"),
    ("copyright", "content_ownership"),
    ("ip rights", "content_ownership"),
    ("hereby assign", "content_ownership"),
    ("creator agreement", "content_ownership"),
    ("limitation of liability", "liability"),
    ("indemnif", "indemnification"),
)

_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_collection": (
        "collect",
        "collection",
        "personal data",
        "personal information",
        "information we",
        "data we",
    ),
    "data_purposes": ("purpose", "purposes", "use your", "used for", "legal basis"),
    "data_sharing": (
        "share",
        "sharing",
        "third party",
        "third-party",
        "disclose",
        "recipient",
        "service provider",
    ),
    "user_rights": (
        "right",
        "access",
        "delete",
        "deletion",
        "portability",
        "rectification",
        "opt out",
        "opt-out",
        "object",
    ),
    "retention": (
        "retain",
        "retention",
        "store",
        "storage",
        "keep",
        "period",
        "days",
        "months",
        "years",
        "delete",
        "deletion",
    ),
    "security": (
        "security",
        "encrypt",
        "encryption",
        "protect",
        "safeguard",
        "breach",
        "access control",
    ),
    "cookies_tracking": (
        "cookie",
        "cookies",
        "tracker",
        "tracking",
        "analytics",
        "pixel",
        "advertising",
    ),
    "data_sale": ("sell", "sale", "monetiz", "commercial", "advertising partner"),
    "international_transfers": (
        "transfer",
        "cross-border",
        "international",
        "adequacy",
        "standard contractual",
        "outside",
    ),
    "government_access": (
        "government",
        "law enforcement",
        "legal request",
        "subpoena",
        "court order",
        "national security",
    ),
    "corporate_family_sharing": (
        "affiliate",
        "subsidiary",
        "corporate family",
        "group company",
        "related entity",
    ),
    "ai_training": (
        "train",
        "training",
        "model",
        "machine learning",
        "generative",
        "prompt",
        "llm",
        "artificial intelligence",
    ),
    "automated_decisions": (
        "automated decision",
        "profiling",
        "algorithm",
        "automated processing",
    ),
    "content_ownership": (
        "license",
        "ownership",
        "assign",
        "intellectual property",
        "copyright",
        "user content",
    ),
    "dispute_resolution": (
        "arbitration",
        "arbitrate",
        "dispute",
        "class action",
        "jury",
        "governing law",
        "venue",
        "litigation",
    ),
    "liability": ("liability", "liable", "damages", "warranty", "disclaimer"),
    "indemnification": ("indemnif", "hold harmless", "defend"),
    "termination_consequences": (
        "terminat",
        "suspend",
        "infringer",
        "account closure",
        "deactivate",
    ),
    "consent_mechanisms": ("consent", "opt in", "opt-in", "opt out", "opt-out", "permission"),
    "account_lifecycle": ("account", "register", "registration", "close", "deletion"),
    "children": ("child", "children", "minor", "parental", "under 13", "under 16"),
    "breach_notification": ("breach", "security incident", "notify", "notification"),
    "scope_expansion": ("change", "update", "modify", "scope", "future product"),
}

_SUBSTANTIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "share",
        "shared",
        "sharing",
        "sell",
        "sold",
        "sale",
        "third party",
        "third-party",
        "partner",
        "affiliate",
        "advertis",
        "retain",
        "retention",
        "store",
        "stored",
        "delete",
        "deletion",
        "train",
        "training",
        "model",
        "transfer",
        "rights",
        "collect",
        "disclose",
        "profile",
        "track",
        "tracking",
        "analytics",
        "personal information",
        "personal data",
        "opt out",
        "opt-out",
        "opt in",
        "opt-in",
        "consent",
    }
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "we",
        "with",
        "your",
        "you",
        "our",
        "may",
        "will",
        "not",
        "all",
        "any",
        "can",
        "has",
        "have",
        "if",
        "when",
        "where",
        "which",
        "who",
        "yes",
        "no",
        "unclear",
        "null",
        "none",
    }
)

_COOKIE_TOPICS: frozenset[InsightCategory] = frozenset({"cookies_tracking", "consent_mechanisms"})


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _has_substantive_keyword(text: str) -> bool:
    normalized = _normalized(text)
    return any(keyword in normalized for keyword in _SUBSTANTIVE_KEYWORDS)


def _is_cookie_focused(text: str) -> bool:
    normalized = _normalized(text)
    return "cookie" in normalized or "cookies" in normalized


def _significant_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", _normalized(text))
    return {token for token in tokens if len(token) >= 3 and token not in _STOPWORDS}


def _match_foreign_topic_category(
    text: str,
    *,
    exclude_category: InsightCategory | None = None,
) -> InsightCategory | None:
    """Return the first insight category signaled by ``text``, if any."""
    normalized = _normalized(text)
    if not normalized:
        return None
    for signal, signal_category in _FOREIGN_TOPIC_SIGNALS:
        if exclude_category is not None and signal_category == exclude_category:
            continue
        if signal in normalized:
            return signal_category
    return None


def infer_insight_category(
    text: str,
    *,
    quote: str | None = None,
    default: InsightCategory = "dangers",
) -> InsightCategory:
    """Map cross-cutting extraction text to a specific insight category when possible."""
    combined = _normalized(f"{text} {quote or ''}")
    matched = _match_foreign_topic_category(combined, exclude_category=default)
    return matched or default


def quote_signals_foreign_topic(quote: str, *, category: InsightCategory) -> bool:
    """True when ``quote`` strongly signals a different insight category."""
    return _match_foreign_topic_category(quote, exclude_category=category) is not None


def is_substantive_evidence(
    quote: str | None,
    *,
    category: InsightCategory,
    finding_value: str | None = None,
) -> bool:
    """Return True when a quote is strong enough to cite for the given topic."""
    return (
        score_evidence_relevance(
            quote or "",
            category=category,
            finding_value=finding_value or "",
        )
        >= 20
    )


def score_evidence_relevance(
    quote: str,
    *,
    category: InsightCategory,
    finding_value: str,
) -> int:
    """Score how well ``quote`` supports ``finding_value`` for ``category`` (0-100)."""
    text = (quote or "").strip()
    if not text:
        return 0

    normalized = _normalized(text)

    if _matches_any(normalized, _BOILERPLATE_PATTERNS):
        return 0
    if _matches_any(normalized, _PROCEDURAL_ONLY_PATTERNS):
        return 0
    if quote_signals_foreign_topic(normalized, category=category):
        return 0
    if finding_value and quote_signals_foreign_topic(_normalized(finding_value), category=category):
        return 0

    if category not in _COOKIE_TOPICS and _is_cookie_focused(normalized):
        if not _has_substantive_keyword(normalized):
            return 0

    if category in _COOKIE_TOPICS:
        if _is_cookie_focused(normalized) and not _has_substantive_keyword(normalized):
            if not re.search(
                r"\b(google|facebook|meta|analytics|pixel|sdk|advertis)\b",
                normalized,
            ):
                return 0

    score = 0
    if finding_value:
        value_tokens = _significant_tokens(finding_value)
        quote_tokens = _significant_tokens(normalized)
        overlap = value_tokens & quote_tokens
        score += min(40, 10 * len(overlap))
        if value_tokens and not overlap and not _has_substantive_keyword(normalized):
            topic_keywords = _TOPIC_KEYWORDS.get(category, ())
            if not any(keyword in normalized for keyword in topic_keywords):
                return 0

    for keyword in _TOPIC_KEYWORDS.get(category, ()):
        if keyword in normalized:
            score += 12

    if _has_substantive_keyword(normalized):
        score += 10
    if len(normalized) >= 40:
        score += 8

    return min(score, 100)


def filter_evidence_spans(
    evidence_spans: Sequence[EvidenceSpan],
    *,
    category: InsightCategory,
    finding_value: str | None = None,
    min_score: int = 20,
) -> list[EvidenceSpan]:
    """Keep only evidence spans that substantively support the topic finding."""
    ranked: list[tuple[int, EvidenceSpan]] = []
    seen: set[tuple] = set()
    value = finding_value or ""
    for span in evidence_spans:
        quote = (span.quote or "").strip()
        if not quote:
            continue
        key = (
            span.document_id,
            quote,
            span.start_char,
            span.end_char,
            span.section_title or "",
        )
        if key in seen:
            continue
        seen.add(key)
        relevance = score_evidence_relevance(quote, category=category, finding_value=value)
        if relevance < min_score:
            continue
        ranked.append((relevance, span))

    ranked.sort(
        key=lambda item: (
            -item[0],
            not item[1].verified,
            item[1].document_id,
            item[1].section_title or "",
            item[1].quote,
        )
    )
    return [span for _, span in ranked]


TOPIC_CITATION_LIMIT = 5
MIN_SUBSTANTIVE_CITATIONS_FOR_ELEVATED_RISK = 3


def count_substantive_evidence(
    evidence_spans: Sequence[EvidenceSpan],
    *,
    category: InsightCategory,
    finding_value: str | None = None,
) -> int:
    """Count evidence spans that substantively support a topic finding."""
    return len(
        filter_evidence_spans(
            evidence_spans,
            category=category,
            finding_value=finding_value,
        )
    )


def select_topic_citations(
    evidence_spans: Sequence[EvidenceSpan],
    *,
    category: InsightCategory,
    finding_value: str | None = None,
    limit: int = TOPIC_CITATION_LIMIT,
) -> list[EvidenceSpan]:
    """Pick up to ``limit`` best citations for a topic finding."""
    if limit <= 0:
        return []
    return filter_evidence_spans(
        evidence_spans,
        category=category,
        finding_value=finding_value,
    )[:limit]
