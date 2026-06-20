"""Calibrate privacy dimension scores when LLM text contradicts the numeric grade.

Dimension scores are 0-10 where higher is better for the user. The LLM sometimes
assigns C-range scores while the justification lists multiple real user controls.
This module raises scores to evidence-based floors without ignoring genuine gaps.

Note: score floors still use lightweight regex on LLM-written justifications — a
different problem from term materiality (see ``standard_terms`` / batch classifier).
Migrating these signal lists to LLM would add latency on every overview; kept as
heuristic calibration until justified by accuracy gaps.
"""

from __future__ import annotations

import re
from typing import Literal

from src.models.document import (
    DocumentAnalysisScores,
    MetaSummary,
    MetaSummaryScore,
    MetaSummaryScores,
)

DimensionKey = Literal[
    "transparency",
    "data_collection_scope",
    "user_control",
    "third_party_sharing",
    "data_retention_score",
    "security_score",
]

_OVERVIEW_DIMENSIONS: tuple[str, ...] = (
    "transparency",
    "data_collection_scope",
    "user_control",
    "third_party_sharing",
)

_POSITIVE_TONE = re.compile(
    r"\b("
    r"provides?|offers?|allows?|includes?|users can|you can|self[- ]service|"
    r"granular|robust|strong|multiple|several|comprehensive|genuine|clear controls?"
    r")\b",
    re.I,
)

_CAVEAT = re.compile(
    r"\b(however|although|caveat|limitation|except|only on|not available on|"
    r"mobile|org[- ]level|organization|enterprise|admin|all[- ]or[- ]nothing)\b",
    re.I,
)

_USER_CONTROL_POSITIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"cookie consent",
        r"cookie (?:banner|preferences|settings|tool|manager)",
        r"manage cookies",
        r"global privacy control",
        r"\bgpc\b",
        r"do not sell",
        r"do not track",
        r"opt[- ]?out.*(?:ai|training|model|machine learning|content)",
        r"(?:ai|training|model|content).*(?:opt[- ]?out|toggle|switch|disable|control)",
        r"unsubscribe",
        r"marketing (?:preferences|opt[- ]?out|emails?|communications?)",
        r"(?:self[- ]service|in[- ]app).*(?:delet|remov)",
        r"delete (?:your )?account",
        r"account deletion",
        r"data portability",
        r"download (?:your )?data",
        r"export (?:your )?data",
        r"privacy (?:settings|controls|dashboard|center)",
        r"access (?:to )?(?:your )?data",
    )
)

_USER_CONTROL_NEGATIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"no (?:opt[- ]?out|control|choice|self[- ]service)",
        r"cannot (?:delete|opt[- ]?out|remove|disable)",
        r"no way to",
        r"request (?:required|by email|in writing)",
        r"contact us to delete",
        r"none (?:provided|available|offered)",
        r"cannot be deleted",
    )
)

_TRANSPARENCY_POSITIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"clear(?:ly)? (?:explain(?:s)?|state(?:s)?|describe(?:s)?|disclos(?:es)?)",
        r"plain (?:english|language)",
        r"specific(?:ally)? (?:name(?:s)?|list(?:s)?|identif(?:y|ies))",
        r"named (?:third|recipient|partner|vendor)",
        r"transparent",
        r"detailed disclosure",
        r"crystal clear",
        r"names (?:specific|third|recipient|partner)",
    )
)

_TRANSPARENCY_NEGATIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"vague|opaque|unclear|boilerplate|not specified|does not explain",
        r"deliberately (?:vague|opaque|hidden)",
    )
)

_COLLECTION_POSITIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"minimal (?:collection|data)",
        r"only (?:necessary|required|what is needed)",
        r"limited (?:collection|to)",
        r"does not collect (?:biometric|health|precise location)",
        r"necessary (?:for|to provide)",
    )
)

_COLLECTION_NEGATIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"extensive|broad(?:ly)?|sweeping|all (?:data|information)",
        r"biometric|precise location|gps|browsing history",
        r"across (?:devices|sites|apps)",
        r"advertising (?:ecosystem|partners)",
    )
)

_SHARING_POSITIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"does not (?:sell|share)",
        r"no (?:sale|selling) (?:of )?(?:personal )?data",
        r"not sold",
        r"limited (?:sharing|partners|recipients)",
        r"service providers only",
    )
)

_SHARING_NEGATIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"sell(?:s|ing)? (?:personal )?data",
        r"data broker",
        r"unrestricted|wide(?:ly)? shared",
        r"many (?:third|advertising) (?:parties|partners)",
        r"monetiz",
    )
)

_RETENTION_POSITIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\d+ (?:day|month|year)s? (?:after|retention|period)",
        r"delete(?:s|d)? (?:after|within)",
        r"short (?:retention|period)",
        r"specific (?:retention|period|timeframe)",
    )
)

_RETENTION_NEGATIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"indefinite|in perpetuity|as long as",
        r"no (?:specific )?(?:retention|deletion) (?:period|timeframe)",
    )
)

_SECURITY_POSITIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\be2ee\b|end[- ]to[- ]end encrypt",
        r"soc 2|iso 27001|penetration test",
        r"encrypt(?:ion|ed)? (?:at rest|in transit)",
    )
)

_SECURITY_NEGATIVE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.I) for pattern in (r"no encrypt|weak security|not encrypt",)
)

_DIMENSION_SIGNALS: dict[str, tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]] = {
    "user_control": (_USER_CONTROL_POSITIVE, _USER_CONTROL_NEGATIVE),
    "transparency": (_TRANSPARENCY_POSITIVE, _TRANSPARENCY_NEGATIVE),
    "data_collection_scope": (_COLLECTION_POSITIVE, _COLLECTION_NEGATIVE),
    "third_party_sharing": (_SHARING_POSITIVE, _SHARING_NEGATIVE),
    "data_retention_score": (_RETENTION_POSITIVE, _RETENTION_NEGATIVE),
    "security_score": (_SECURITY_POSITIVE, _SECURITY_NEGATIVE),
}


def _count_matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def _user_control_floor(positive: int, negative: int, text: str) -> int | None:
    """Return minimum fair score for user_control, or None if no adjustment."""
    if negative >= 2:
        return None
    has_caveats = bool(_CAVEAT.search(text))
    has_positive_tone = bool(_POSITIVE_TONE.search(text))

    if positive >= 4:
        # Multiple documented controls (GPC, consent, AI toggle, delete, etc.)
        return 8 if not negative else 7
    if positive >= 3 and (has_positive_tone or not has_caveats):
        return 7
    if positive >= 2 and has_positive_tone and negative == 0:
        return 6
    if positive >= 1 and has_positive_tone and negative == 0 and has_caveats:
        return 6
    return None


def _generic_floor(positive: int, negative: int, text: str) -> int | None:
    if negative >= 2:
        return None
    has_positive_tone = bool(_POSITIVE_TONE.search(text))
    if positive >= 2 and negative == 0 and (has_positive_tone or positive >= 2):
        return 7
    if positive >= 1 and negative == 0 and (has_positive_tone or positive >= 2):
        return 6
    return None


def calibrate_dimension_score(
    dimension: str,
    score: int,
    justification: str,
) -> int:
    """Raise a dimension score when justification evidence supports a higher floor."""
    text = justification or ""
    positive_patterns, negative_patterns = _DIMENSION_SIGNALS.get(dimension, ((), ()))
    positive = _count_matches(text, positive_patterns)
    negative = _count_matches(text, negative_patterns)

    if dimension == "user_control":
        floor = _user_control_floor(positive, negative, text)
    else:
        floor = _generic_floor(positive, negative, text)

    if floor is None:
        return score
    return max(score, min(10, floor))


def calibrate_document_scores(
    scores: dict[str, DocumentAnalysisScores],
) -> dict[str, DocumentAnalysisScores]:
    """Return calibrated copy of document analysis dimension scores."""
    calibrated: dict[str, DocumentAnalysisScores] = {}
    for key, entry in scores.items():
        adjusted = calibrate_dimension_score(key, entry.score, entry.justification)
        if adjusted != entry.score:
            calibrated[key] = DocumentAnalysisScores(
                score=adjusted,
                justification=entry.justification,
            )
        else:
            calibrated[key] = entry
    return calibrated


def calibrate_meta_summary_scores(scores: MetaSummaryScores) -> MetaSummaryScores:
    """Return calibrated overview dimension scores."""
    updates: dict[str, MetaSummaryScore] = {}
    for key in _OVERVIEW_DIMENSIONS:
        entry: MetaSummaryScore = getattr(scores, key)
        adjusted = calibrate_dimension_score(key, entry.score, entry.justification)
        if adjusted != entry.score:
            updates[key] = MetaSummaryScore(score=adjusted, justification=entry.justification)
    if not updates:
        return scores
    data = scores.model_dump()
    data.update({k: v.model_dump() for k, v in updates.items()})
    return MetaSummaryScores.model_validate(data)


def calibrate_meta_summary(meta_summary: MetaSummary) -> None:
    """Calibrate overview dimension scores in place."""
    meta_summary.scores = calibrate_meta_summary_scores(meta_summary.scores)
