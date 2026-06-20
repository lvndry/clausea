"""Calibrate consumer explainer watch-out severity and filter standard legal boilerplate.

Materiality tiers live in ``standard_terms``. This module applies those rules to
``ConsumerCase`` objects in ``watch_out_for``, preferring LLM ``materiality``
labels on each case over regex fallback.
"""

from __future__ import annotations

import re

from src.models.document import ConsumerCase, ConsumerExplainer
from src.utils.standard_terms import (
    TermMateriality,
    calibrate_consumer_severity,
    classify_term_materiality,
    should_exclude_from_dangers,
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _case_text(case: ConsumerCase) -> str:
    parts = [case.title, case.means_for_you, case.quote or ""]
    if case.what_they_get:
        parts.append(case.what_they_get)
    return _normalized(" ".join(part for part in parts if part))


def _case_materiality(case: ConsumerCase) -> TermMateriality:
    return classify_term_materiality(_case_text(case), label=case.materiality)


def is_standard_legal_mechanic(case: ConsumerCase) -> bool:
    """True when a watch-out is routine legal boilerplate, not a consumer danger."""
    return _case_materiality(case) == TermMateriality.STANDARD_INDUSTRY


def is_informational_dispute_term(case: ConsumerCase) -> bool:
    """True for arbitration / class-action style terms that warrant a medium note."""
    return _case_materiality(case) == TermMateriality.NOTABLE


def calibrate_watch_out_case(case: ConsumerCase) -> ConsumerCase | None:
    """Return a calibrated case, or None when it should be removed from watch_out_for."""
    text = _case_text(case)
    tier = _case_materiality(case)
    if not should_exclude_from_dangers(text, materiality=tier):
        return case

    if tier == TermMateriality.NOTABLE:
        case.severity = calibrate_consumer_severity(case.severity, text, materiality=tier)
        if (case.classification or "").strip().lower() in {"blocker", "critical"}:
            case.classification = "informational"
        elif not case.classification:
            case.classification = "informational"
        return case

    return None


def calibrate_consumer_explainer(explainer: ConsumerExplainer) -> ConsumerExplainer:
    """Filter boilerplate and downgrade informational dispute terms in watch_out_for."""
    calibrated: list[ConsumerCase] = []
    for case in explainer.watch_out_for:
        adjusted = calibrate_watch_out_case(case)
        if adjusted is not None:
            calibrated.append(adjusted)
    explainer.watch_out_for = calibrated
    return explainer
