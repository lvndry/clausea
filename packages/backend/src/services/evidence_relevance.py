"""Filter evidence spans using structural rules only.

Quote relevance and materiality are determined at extraction time via LLM labels
and verified anchor offsets — not keyword or regex heuristics here.

Structural rules:
- Empty quotes are rejected
- Non-empty quotes linked to a finding are kept (finding linkage)
- Verified spans (character offsets present) are ranked ahead of unverified spans
"""

from __future__ import annotations

from collections.abc import Sequence

from src.models.document import EvidenceSpan, InsightCategory

TOPIC_CITATION_LIMIT = 5
MIN_SUBSTANTIVE_CITATIONS_FOR_ELEVATED_RISK = 3


def infer_insight_category(
    text: str,
    *,
    quote: str | None = None,
    default: InsightCategory = "dangers",
) -> InsightCategory:
    """Return the default category; routing uses LLM materiality labels, not patterns."""
    _ = text, quote
    return default


def quote_signals_foreign_topic(quote: str, *, category: InsightCategory) -> bool:
    """Foreign-topic detection uses finding category linkage only, not keyword patterns."""
    _ = quote, category
    return False


def is_substantive_evidence(
    quote: str | None,
    *,
    category: InsightCategory,
    finding_value: str | None = None,
) -> bool:
    """True when a quote is non-empty and linked to a finding."""
    _ = category, finding_value
    return bool((quote or "").strip())


def score_evidence_relevance(
    quote: str,
    *,
    category: InsightCategory,
    finding_value: str,
) -> int:
    """Score evidence by structural presence only (0 or 100)."""
    _ = category, finding_value
    return 100 if (quote or "").strip() else 0


def filter_evidence_spans(
    evidence_spans: Sequence[EvidenceSpan],
    *,
    category: InsightCategory,
    finding_value: str | None = None,
    min_score: int = 20,
) -> list[EvidenceSpan]:
    """Keep non-empty evidence spans linked to the finding; prefer verified spans."""
    _ = category, finding_value, min_score
    ranked: list[tuple[int, EvidenceSpan]] = []
    seen: set[tuple] = set()
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
        ranked.append((100, span))

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


def count_substantive_evidence(
    evidence_spans: Sequence[EvidenceSpan],
    *,
    category: InsightCategory,
    finding_value: str | None = None,
) -> int:
    """Count non-empty evidence spans linked to a topic finding."""
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
    """Pick up to ``limit`` citations for a topic finding."""
    if limit <= 0:
        return []
    return filter_evidence_spans(
        evidence_spans,
        category=category,
        finding_value=finding_value,
    )[:limit]
