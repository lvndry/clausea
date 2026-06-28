"""A–E letter grade helpers for privacy assessments."""

from __future__ import annotations

from typing import Literal

from src.core.logging import get_logger

logger = get_logger(__name__)

GradeLetter = Literal["A", "B", "C", "D", "E"]

_VALID_GRADES: frozenset[str] = frozenset({"A", "B", "C", "D", "E"})

# User-friendliness proxy on 0–10 (higher = better for the user).
_GRADE_USER_SCORE: dict[str, int] = {"A": 9, "B": 7, "C": 5, "D": 3, "E": 1}

# Risk score on 0–10 (higher = worse). Inverse of user-friendliness bands.
_GRADE_RISK_SCORE: dict[str, int] = {"A": 1, "B": 3, "C": 5, "D": 7, "E": 9}

_DIMENSION_WEIGHTS: dict[str, float] = {
    "transparency": 0.14,
    "data_collection_scope": 0.26,
    "user_control": 0.18,
    "third_party_sharing": 0.24,
    "data_retention_score": 0.10,
    "security_score": 0.08,
}

_OVERVIEW_DIMENSIONS: tuple[str, ...] = (
    "transparency",
    "data_collection_scope",
    "user_control",
    "third_party_sharing",
)


def coerce_grade(value: object, *, default: GradeLetter = "C") -> GradeLetter:
    if not isinstance(value, str):
        return default
    candidate = value.strip().upper()[:1]
    if candidate in _VALID_GRADES:
        return candidate  # ty: ignore[invalid-return-type]
    return default


def score_to_grade(score: int) -> GradeLetter:
    """Map legacy 0–10 user-friendliness score to A–E."""
    clamped = max(0, min(10, score))
    if clamped >= 8:
        return "A"
    if clamped >= 6:
        return "B"
    if clamped >= 4:
        return "C"
    if clamped >= 2:
        return "D"
    return "E"


def grade_to_user_score(grade: GradeLetter) -> int:
    return _GRADE_USER_SCORE.get(grade, 5)


def grade_to_risk_score(grade: GradeLetter) -> int:
    return _GRADE_RISK_SCORE.get(grade, 5)


def user_score_to_grade(user_score: float) -> GradeLetter:
    return score_to_grade(round(user_score))


def aggregate_dimension_grades(
    grades: dict[str, GradeLetter],
    *,
    dimensions: tuple[str, ...] | None = None,
) -> GradeLetter | None:
    """Weighted average of dimension grades → overall letter grade."""
    keys = dimensions or tuple(grades.keys())
    present = [key for key in keys if key in grades and key in _DIMENSION_WEIGHTS]
    if not present:
        return None

    weighted_sum = 0.0
    weight_total = 0.0
    for key in present:
        weight = _DIMENSION_WEIGHTS[key]
        weighted_sum += grade_to_user_score(grades[key]) * weight
        weight_total += weight
    if weight_total <= 0:
        return None
    return user_score_to_grade(weighted_sum / weight_total)


def risk_score_to_grade(risk_score: int) -> GradeLetter:
    clamped = max(0, min(10, risk_score))
    if clamped <= 2:
        return "A"
    if clamped <= 4:
        return "B"
    if clamped <= 6:
        return "C"
    if clamped <= 8:
        return "D"
    return "E"


def risk_score_to_verdict(
    risk_score: int,
) -> Literal[
    "very_user_friendly",
    "user_friendly",
    "moderate",
    "pervasive",
    "very_pervasive",
]:
    if risk_score <= 2:
        return "very_user_friendly"
    if risk_score <= 4:
        return "user_friendly"
    if risk_score <= 6:
        return "moderate"
    if risk_score <= 8:
        return "pervasive"
    return "very_pervasive"


_GradeLetter = Literal["A", "B", "C", "D", "E"]

_VERDICT_FROM_GRADE: dict[
    str,
    Literal[
        "very_user_friendly",
        "user_friendly",
        "moderate",
        "pervasive",
        "very_pervasive",
    ],
] = {
    "A": "very_user_friendly",
    "B": "user_friendly",
    "C": "moderate",
    "D": "pervasive",
    "E": "very_pervasive",
}


GRADE_LABELS: dict[str, str] = {
    "A": "very protective",
    "B": "mostly fair",
    "C": "mixed",
    "D": "user-hostile in one important way",
    "E": "user-hostile in several ways",
}

GRADE_FALLBACK_REASONS: dict[str, str] = {
    "A": "Very user-friendly: minimal data collection, strong user controls, no major concerns.",
    "B": "Generally user-friendly: some concerns but good transparency and user rights overall.",
    "C": "Moderate risk: notable concerns around data sharing, limited user controls, or vague language.",
    "D": "Pervasive risk: significant issues with data practices, limited user rights, or broad data sharing.",
    "E": "Very pervasive risk: critical concerns such as forced arbitration, broad data selling, or severe opacity.",
}


def grade_to_verdict(
    grade: str,
) -> Literal[
    "very_user_friendly",
    "user_friendly",
    "moderate",
    "pervasive",
    "very_pervasive",
]:
    """Derive the verdict label directly from the A-E grade.

    This is the canonical derivation — verdict always tracks grade, never a
    separately-adjusted risk_score.  Keeping them in lockstep eliminates the
    grade/verdict contradictions that 38% of production overviews exhibited.
    """
    return _VERDICT_FROM_GRADE.get(grade, "moderate")


def clamp_grade(
    llm_grade: str,
    derived_grade: str,
    max_delta: int = 1,
) -> GradeLetter:
    """Constrain the LLM overall grade to within ``max_delta`` letters of the
    dimension-derived grade.

    The LLM exhibits a strong negativity bias — 44/45 disagreements with its
    own dimensions were *more* negative.  Clamping to ±1 letter keeps the
    LLM's holistic judgment while preventing it from diverging arbitrarily
    from the evidence-backed per-dimension grades.
    """
    order: dict[str, int] = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
    llm_idx = order.get(llm_grade)
    derived_idx = order.get(derived_grade)
    if llm_idx is None or derived_idx is None:
        logger.warning(
            "Invalid grade(s) in clamp_grade: llm=%r, derived=%r — falling back to derived",
            llm_grade,
            derived_grade,
        )
        return coerce_grade(derived_grade)
    delta = llm_idx - derived_idx
    if abs(delta) <= max_delta:
        return coerce_grade(llm_grade)
    if delta > max_delta:
        clamped_idx = derived_idx + max_delta
    else:
        clamped_idx = derived_idx - max_delta
    reverse: dict[int, str] = {v: k for k, v in order.items()}
    return coerce_grade(reverse.get(clamped_idx, derived_grade))
