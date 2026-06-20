"""Classify legal/policy terms for consumer-facing risk surfacing.

Three-tier materiality drives every consumer danger filter, watch-out
calibration, and topic signal score. This module is the single source of
truth — do not duplicate pattern lists elsewhere.

Tiers (checked in order):
  MATERIAL_RISK   — genuine consumer harm (data sale, AI training, broad
                    indemnification, hidden billing, retention without opt-out)
  STANDARD_INDUSTRY — routine boilerplate (DMCA, assignment, governing law)
  NOTABLE         — dispute-resolution terms worth a medium note (arbitration,
                    class-action waiver) but not headline dangers

Heuristic limits: classification is regex-based on free text. Novel phrasing
or combined clauses may misclassify until patterns are updated. Unknown text
defaults to MATERIAL_RISK (conservative — prefer surfacing over hiding).
"""

from __future__ import annotations

import re
from enum import StrEnum

from src.models.document import ConsumerSeverity, InsightCategory


class TermMateriality(StrEnum):
    STANDARD_INDUSTRY = "standard_industry"
    NOTABLE = "notable"
    MATERIAL_RISK = "material_risk"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


_STANDARD_INDUSTRY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"repeat\s+infring",
        r"repeat\s+offender",
        r"\bdmca\b",
        r"copyright\s+infring",
        r"terminat\w+.*infring",
        r"disabl\w+.*infring",
        r"infring\w+.*terminat",
        r"infring\w+.*disabl",
        r"not\s+assignable",
        r"non[- ]assignable",
        r"may\s+not\s+assign",
        r"cannot\s+assign",
        r"no\s+assignment",
        r"assign\w*\s+without\s+prior\s+written\s+consent",
        r"agreement\s+is\s+not\s+assignable",
        r"without\s+prior\s+written\s+consent.*assign",
        r"governing\s+law",
        r"exclusive\s+venue",
        r"entire\s+agreement",
        r"severability",
        r"force\s+majeure",
    )
)

_NOTABLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"binding\s+arbitration",
        r"mandatory\s+arbitration",
        r"class\s+action\s+waiver",
        r"class\s+action.*waiv",
        r"jury\s+trial\s+waiver",
        r"individual\s+basis\s+only",
        r"waiv\w+.*class\s+action",
        r"arbitrat\w+.*individual",
        r"waiv\w+.*jury\s+trial",
    )
)

_MATERIAL_RISK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # Data sale / monetization
        r"sell\s+(?:your|user|personal)\s+(?:data|information)",
        r"sell\s+.*personal\s+information",
        r"sale\s+of\s+(?:your|personal)\s+(?:data|information)",
        r"data\s+broker",
        r"monetiz\w*",
        # AI / model training on user content
        r"train\w*\s+(?:on|with|using)\s+(?:your|user|customer)\s+(?:data|content|prompts|messages|photos|uploads)",
        r"(?:ai|model|machine learning)\s+(?:training|train)",
        r"train\w*\s+(?:ai|models?|machine learning)",
        # Broad license grants
        r"(?:perpetual|irrevocable|sublicens(?:able|e))\s+license",
        r"perpetual.*(?:irrevocable|license)",
        r"irrevocable.*(?:perpetual|license)",
        r"sublicens(?:able|e)",
        # Indemnification / liability
        r"indemnif\w+",
        r"hold\s+harmless",
        r"unlimited\s+liability",
        r"no\s+cap\s+on\s+liability",
        # Sensitive data collection
        r"biometric",
        r"precise\s+location",
        r"gps\s+coordinates?",
        r"(?:children\s+)?(?:under|below)\s+(?:13|16)",
        # Tracking / retention / user control gaps
        r"cross[- ]site\s+track",
        r"track\w*\s+across\s+third[- ]party",
        r"indefinite(?:ly)?\s+retain",
        r"no\s+opt[- ]?out",
        r"cannot\s+(?:delete|remove|opt[- ]?out)",
        # Billing traps
        r"(?:automatic|auto[- ]?)renew(?:al)?",
        r"recurring\s+charge",
        r"hidden\s+fee",
    )
)


def classify_term_materiality(text: str) -> TermMateriality:
    """Classify how a legal term should surface to consumers."""
    normalized = _normalize(text)
    if not normalized:
        return TermMateriality.STANDARD_INDUSTRY

    if any(pattern.search(normalized) for pattern in _MATERIAL_RISK_PATTERNS):
        return TermMateriality.MATERIAL_RISK

    if any(pattern.search(normalized) for pattern in _STANDARD_INDUSTRY_PATTERNS):
        return TermMateriality.STANDARD_INDUSTRY

    if any(pattern.search(normalized) for pattern in _NOTABLE_PATTERNS):
        return TermMateriality.NOTABLE

    return TermMateriality.MATERIAL_RISK


def is_standard_industry_term(text: str) -> bool:
    return classify_term_materiality(text) == TermMateriality.STANDARD_INDUSTRY


def is_material_risk(text: str) -> bool:
    """True when a term is a genuine consumer danger, not routine boilerplate."""
    return classify_term_materiality(text) == TermMateriality.MATERIAL_RISK


def should_exclude_from_dangers(text: str) -> bool:
    """True when a term belongs in a specific topic, not consumer dangers."""
    materiality = classify_term_materiality(text)
    return materiality in {TermMateriality.STANDARD_INDUSTRY, TermMateriality.NOTABLE}


def filter_danger_strings(values: list[str]) -> list[str]:
    """Drop standard/notable boilerplate from overview danger lists."""
    return [value for value in values if value and not should_exclude_from_dangers(value)]


def topic_signal_score(text: str, *, category: InsightCategory | str) -> int:
    """Map a finding to a 0-10 risk signal for topic stance scoring."""
    materiality = classify_term_materiality(text)
    category_value = str(category)

    if category_value == "dangers":
        if materiality == TermMateriality.STANDARD_INDUSTRY:
            return 2
        if materiality == TermMateriality.NOTABLE:
            return 4
        return 8

    if category_value == "dispute_resolution":
        if materiality in {TermMateriality.STANDARD_INDUSTRY, TermMateriality.NOTABLE}:
            return 4
        return 6

    if category_value == "termination_consequences":
        if materiality == TermMateriality.STANDARD_INDUSTRY:
            return 3
        return 5

    if category_value == "content_ownership":
        if materiality == TermMateriality.STANDARD_INDUSTRY:
            return 3
        if materiality == TermMateriality.MATERIAL_RISK:
            return 7
        return 5

    if materiality == TermMateriality.STANDARD_INDUSTRY:
        return 3
    if materiality == TermMateriality.NOTABLE:
        return 5
    return 7


def calibrate_consumer_severity(severity: ConsumerSeverity | str, text: str) -> ConsumerSeverity:
    """Downgrade watch-out severity for standard or routine legal terms."""
    materiality = classify_term_materiality(text)
    current = str(severity).strip().lower()
    if materiality == TermMateriality.STANDARD_INDUSTRY:
        return "low"
    if materiality == TermMateriality.NOTABLE and current in {"critical", "high"}:
        return "medium"
    if current in {"critical", "high", "medium", "low"}:
        return current  # type: ignore[return-value]
    return "medium"


__all__ = [
    "TermMateriality",
    "calibrate_consumer_severity",
    "classify_term_materiality",
    "filter_danger_strings",
    "is_material_risk",
    "is_standard_industry_term",
    "should_exclude_from_dangers",
    "topic_signal_score",
]
