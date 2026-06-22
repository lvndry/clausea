"""Classify legal/policy terms for consumer-facing risk surfacing.

Three-tier materiality drives every consumer danger filter, watch-out
calibration, and topic signal score. This module is the single source of
truth — do not duplicate pattern lists elsewhere.

Tiers:
  MATERIAL_RISK   — genuine consumer harm (data sale, AI training, broad
                    indemnification, hidden billing, retention without opt-out)
  STANDARD_INDUSTRY — routine boilerplate (DMCA, assignment, governing law)
  NOTABLE         — dispute-resolution terms worth a medium note (arbitration,
                    class-action waiver) but not headline dangers

Classification:
  1. Explicit LLM label (``materiality`` on extraction, consumer explainer, or
     batch classifier via ``term_materiality_classifier``)
  2. Conservative default when no label: MATERIAL_RISK (prefer surfacing over
     hiding). Empty text defaults to STANDARD_INDUSTRY.

No regex pattern matching — context-aware labels are required for accurate
filtering. Extraction and overview pipelines run batch LLM classification when
labels are missing.
"""

from __future__ import annotations

from enum import StrEnum

from src.models.document import ConsumerSeverity, InsightCategory


class TermMateriality(StrEnum):
    STANDARD_INDUSTRY = "standard_industry"
    NOTABLE = "notable"
    MATERIAL_RISK = "material_risk"


def coerce_term_materiality(value: object) -> TermMateriality | None:
    """Parse an LLM or stored materiality label."""
    if value is None:
        return None
    if isinstance(value, TermMateriality):
        return value
    normalized = str(value).strip().lower()
    for tier in TermMateriality:
        if normalized == tier.value:
            return tier
    return None


def _default_without_label(text: str) -> TermMateriality:
    """Conservative tier when no LLM label is available."""
    if not (text or "").strip():
        return TermMateriality.STANDARD_INDUSTRY
    return TermMateriality.MATERIAL_RISK


def classify_term_materiality(
    text: str,
    *,
    label: TermMateriality | str | None = None,
) -> TermMateriality:
    """Classify how a legal term should surface to consumers."""
    coerced = coerce_term_materiality(label)
    if coerced is not None:
        return coerced
    return _default_without_label(text)


def is_standard_industry_term(
    text: str,
    *,
    label: TermMateriality | str | None = None,
) -> bool:
    return classify_term_materiality(text, label=label) == TermMateriality.STANDARD_INDUSTRY


def is_material_risk(
    text: str,
    *,
    label: TermMateriality | str | None = None,
) -> bool:
    """True when a term is a genuine consumer danger, not routine boilerplate."""
    return classify_term_materiality(text, label=label) == TermMateriality.MATERIAL_RISK


def should_exclude_from_dangers(
    text: str,
    *,
    materiality: TermMateriality | str | None = None,
) -> bool:
    """True when a term belongs in a specific topic, not consumer dangers."""
    tier = classify_term_materiality(text, label=materiality)
    return tier in {TermMateriality.STANDARD_INDUSTRY, TermMateriality.NOTABLE}


def filter_danger_strings(
    values: list[str],
    *,
    labels: dict[str, TermMateriality | str] | None = None,
) -> list[str]:
    """Drop standard/notable boilerplate from overview danger lists."""
    label_map = labels or {}
    return [
        value
        for value in values
        if value and not should_exclude_from_dangers(value, materiality=label_map.get(value))
    ]


def topic_signal_score(
    text: str,
    *,
    category: InsightCategory | str,
    materiality: TermMateriality | str | None = None,
) -> int:
    """Map a finding to a 0-10 risk signal for topic stance scoring."""
    tier = classify_term_materiality(text, label=materiality)
    category_value = str(category)

    if category_value == "dangers":
        if tier == TermMateriality.STANDARD_INDUSTRY:
            return 2
        if tier == TermMateriality.NOTABLE:
            return 4
        return 8

    if category_value == "dispute_resolution":
        if tier in {TermMateriality.STANDARD_INDUSTRY, TermMateriality.NOTABLE}:
            return 4
        return 6

    if category_value == "termination_consequences":
        if tier == TermMateriality.STANDARD_INDUSTRY:
            return 3
        return 5

    if category_value == "content_ownership":
        if tier == TermMateriality.STANDARD_INDUSTRY:
            return 3
        if tier == TermMateriality.MATERIAL_RISK:
            return 7
        return 5

    if tier == TermMateriality.STANDARD_INDUSTRY:
        return 3
    if tier == TermMateriality.NOTABLE:
        return 5
    return 7


def calibrate_consumer_severity(
    severity: ConsumerSeverity | str,
    text: str,
    *,
    materiality: TermMateriality | str | None = None,
) -> ConsumerSeverity:
    """Downgrade watch-out severity for standard or routine legal terms."""
    tier = classify_term_materiality(text, label=materiality)
    current = str(severity).strip().lower()
    if tier == TermMateriality.STANDARD_INDUSTRY:
        return "low"
    if tier == TermMateriality.NOTABLE and current in {"critical", "high"}:
        return "medium"
    if current in {"critical", "high", "medium", "low"}:
        return current  # type: ignore[return-value]
    return "medium"


def finding_materiality_label(attributes: object) -> TermMateriality | None:
    """Extract materiality from a Finding.attributes dict or AggregatedFinding.attributes list."""
    if isinstance(attributes, dict):
        return coerce_term_materiality(attributes.get("materiality"))
    if isinstance(attributes, list):
        for entry in attributes:
            if isinstance(entry, dict):
                label = coerce_term_materiality(entry.get("materiality"))
                if label is not None:
                    return label
    return None


__all__ = [
    "TermMateriality",
    "calibrate_consumer_severity",
    "classify_term_materiality",
    "coerce_term_materiality",
    "filter_danger_strings",
    "finding_materiality_label",
    "is_material_risk",
    "is_standard_industry_term",
    "should_exclude_from_dangers",
    "topic_signal_score",
]
