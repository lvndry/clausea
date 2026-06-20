"""Calibrate consumer explainer watch-out severity and filter standard legal boilerplate."""

from __future__ import annotations

import re

from src.models.document import ConsumerCase, ConsumerExplainer
from src.utils.standard_terms import (
    TermMateriality,
    calibrate_consumer_severity,
    classify_term_materiality,
    should_exclude_from_dangers,
)

_REAL_WATCH_OUT_SIGNALS: tuple[str, ...] = (
    "sell your",
    "sell personal",
    "sale of personal",
    "data broker",
    "monetiz",
    "train ai",
    "ai training",
    "model training",
    "machine learning",
    "train models",
    "indemnif",
    "hold harmless",
    "hidden fee",
    "automatic renewal",
    "auto-renew",
    "recurring charge",
    "biometric",
    "precise location",
    "gps coordinates",
    "children under",
    "under 13",
    "under 16",
    "perpetual license",
    "irrevocable license",
    "sublicensable",
    "cross-site tracking",
    "across third-party",
    "indefinitely retain",
    "no opt-out",
    "cannot delete",
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _case_text(case: ConsumerCase) -> str:
    parts = [case.title, case.means_for_you, case.quote or ""]
    if case.what_they_get:
        parts.append(case.what_they_get)
    return _normalized(" ".join(part for part in parts if part))


def _has_real_watch_out_signal(text: str) -> bool:
    return any(signal in text for signal in _REAL_WATCH_OUT_SIGNALS)


def is_standard_legal_mechanic(case: ConsumerCase) -> bool:
    """True when a watch-out is routine legal boilerplate, not a consumer danger."""
    text = _case_text(case)
    if not text or _has_real_watch_out_signal(text):
        return False
    return classify_term_materiality(text) == TermMateriality.STANDARD_INDUSTRY


def is_informational_dispute_term(case: ConsumerCase) -> bool:
    """True for arbitration / class-action style terms that warrant a medium note."""
    text = _case_text(case)
    if not text or _has_real_watch_out_signal(text):
        return False
    return classify_term_materiality(text) == TermMateriality.NOTABLE


def calibrate_watch_out_case(case: ConsumerCase) -> ConsumerCase | None:
    """Return a calibrated case, or None when it should be removed from watch_out_for."""
    text = _case_text(case)
    if should_exclude_from_dangers(text) and not _has_real_watch_out_signal(text):
        if classify_term_materiality(text) == TermMateriality.NOTABLE:
            case.severity = calibrate_consumer_severity(case.severity, text)
            if (case.classification or "").strip().lower() in {"blocker", "critical"}:
                case.classification = "informational"
            elif not case.classification:
                case.classification = "informational"
            return case
        return None

    return case


def calibrate_consumer_explainer(explainer: ConsumerExplainer) -> ConsumerExplainer:
    """Filter boilerplate and downgrade informational dispute terms in watch_out_for."""
    calibrated: list[ConsumerCase] = []
    for case in explainer.watch_out_for:
        adjusted = calibrate_watch_out_case(case)
        if adjusted is not None:
            calibrated.append(adjusted)
    explainer.watch_out_for = calibrated
    return explainer
