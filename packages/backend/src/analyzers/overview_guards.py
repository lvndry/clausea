"""Post-generation validators for product overviews.

Two tiers of validation:

1. **Deterministic checks** (this file) — fast, reliable, no LLM needed.
   Length caps, empty-headline detection, E-grade-on-silence, dangers/benefits
   count balance, rights-paths regex, actions-actionability regex, citation
   coverage, long-sentence detection.

2. **Semantic checks** (``llm_review.py``) — one cheap LLM call that replaces
   hardcoded lexicons for: unsupported strong claims, signal/prose
   contradictions, legal jargon, generic headline openers, internal-state
   language, jargon in rights/actions. The LLM understands paraphrase and
   context that regex lists always miss.

The top-level entry point is :func:`validate_overview`, which runs deterministic
checks synchronously and optionally merges LLM review results. Individual
validators are exposed for targeted testing.
"""

import re
from typing import Any

from pydantic import BaseModel

_SUMMARY_MAX_WORDS = 20
_HEADLINE_MAX_WORDS = 25
_SENTENCE_DEFAULT_MAX_WORDS = 35

_SILENCE_STATUSES: frozenset[str] = frozenset({"missing", "not_disclosed"})

_PATH_INDICATOR = re.compile(
    r"https?://|@|(?:settings?|account|profile|dashboard|in-app|preference)",
    re.IGNORECASE,
)

_ACTION_VERBS = re.compile(
    r"disable|delete|opt[\s-]?out|request|revoke|contact|email|"
    r"turn[\s-]?off|uncheck|unsubscribe|review|check",
    re.IGNORECASE,
)


class OverviewValidationResult(BaseModel):
    """Outcome of running all overview guards against a parsed overview."""

    should_re_roll: bool
    re_roll_reasons: list[str]
    warnings: list[str]
    checks_passed: dict[str, bool]


def _get_field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


# ── Deterministic validators ──────────────────────────────────────────────────


def validate_summary_length(summary: str) -> bool:
    if not summary:
        return True
    return _word_count(summary) <= _SUMMARY_MAX_WORDS


def validate_headline_length(headline: str | None) -> bool:
    if not headline or not headline.strip():
        return True
    return _word_count(headline) <= _HEADLINE_MAX_WORDS


def validate_headline_not_empty(headline: str | None, has_adequate_evidence: bool) -> bool:
    if not has_adequate_evidence:
        return True
    return bool(headline and headline.strip())


def find_long_sentences(text: str, max_words: int = _SENTENCE_DEFAULT_MAX_WORDS) -> list[int]:
    if not text:
        return []
    counts: list[int] = []
    for sentence in re.split(r"[.!?]+", text):
        count = _word_count(sentence)
        if count > max_words:
            counts.append(count)
    return counts


def check_e_grade_on_silence(grade: str | None, topic_stances: list[Any]) -> bool:
    if not topic_stances:
        return False
    if grade is None or grade.strip().upper() != "E":
        return False
    total = len(topic_stances)
    silent = 0
    total_evidence = 0
    for stance in topic_stances:
        status = _get_field(stance, "status")
        if status in _SILENCE_STATUSES:
            silent += 1
        evidence = _get_field(stance, "evidence_count")
        if isinstance(evidence, int):
            total_evidence += evidence
    return silent / total > 0.7 and total_evidence == 0


def check_dangers_benefits_balance(
    dangers: list[str], benefits: list[str], grade_justification: str
) -> bool:
    if len(dangers) < 5:
        return True
    return len(benefits) >= 2


def check_rights_have_paths(your_rights: list[str]) -> tuple[bool, float]:
    if not your_rights:
        return True, 1.0
    with_paths = 0
    pathless = 0
    contact_pathless = 0
    for right in your_rights:
        text = right or ""
        if _PATH_INDICATOR.search(text):
            with_paths += 1
        else:
            pathless += 1
            lowered = text.lower()
            if "contact" in lowered or "email the company" in lowered:
                contact_pathless += 1
    ratio = with_paths / len(your_rights)
    acceptable = ratio >= 0.7 or contact_pathless == pathless
    return acceptable, ratio


def check_actions_actionable(recommended_actions: list[str]) -> tuple[bool, float]:
    if not recommended_actions:
        return True, 1.0
    actionable = 0
    for action in recommended_actions:
        text = action or ""
        if _ACTION_VERBS.search(text) or _PATH_INDICATOR.search(text):
            actionable += 1
    ratio = actionable / len(recommended_actions)
    return ratio >= 0.7, ratio


def _collect_citations(topic_stances: list[Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for stance in topic_stances:
        supporting = _get_field(stance, "supporting_citations")
        if isinstance(supporting, list):
            for citation in supporting:
                if isinstance(citation, dict):
                    citations.append(citation)
                elif hasattr(citation, "model_dump"):
                    citations.append(citation.model_dump())
    return citations


# ── Top-level validator ───────────────────────────────────────────────────────


def validate_overview(
    overview: dict[str, Any], has_adequate_evidence: bool
) -> OverviewValidationResult:
    """Run all deterministic checks. LLM review is merged separately by the caller."""
    summary = str(overview.get("summary") or "")
    headline = overview.get("headline_claim")
    headline = str(headline) if headline is not None else None
    grade = overview.get("grade")
    grade = str(grade) if grade is not None else None
    grade_justification = overview.get("grade_justification")
    grade_justification = str(grade_justification) if grade_justification is not None else None

    your_rights = _as_str_list(overview.get("your_rights"))
    dangers = _as_str_list(overview.get("dangers"))
    benefits = _as_str_list(overview.get("benefits"))
    recommended_actions = _as_str_list(overview.get("recommended_actions"))
    topic_stances = overview.get("topic_stances") or []

    checks: dict[str, bool] = {}
    re_roll_reasons: list[str] = []
    warnings: list[str] = []

    # ── High-severity deterministic checks ────────────────────────────────────

    headline_ok = validate_headline_not_empty(headline, has_adequate_evidence)
    checks["headline_not_empty"] = headline_ok
    if not headline_ok:
        re_roll_reasons.append("Headline is empty despite adequate evidence.")

    e_on_silence = check_e_grade_on_silence(grade, topic_stances)
    checks["no_e_grade_on_silence"] = not e_on_silence
    if e_on_silence:
        re_roll_reasons.append("Grade E assigned for silence rather than evidence.")

    # ── Medium-severity deterministic checks (warnings) ───────────────────────

    summary_len_ok = validate_summary_length(summary)
    checks["summary_length"] = summary_len_ok
    if not summary_len_ok:
        warnings.append("Summary exceeds 20 words.")

    headline_len_ok = validate_headline_length(headline)
    checks["headline_length"] = headline_len_ok
    if not headline_len_ok:
        warnings.append("Headline exceeds 25 words.")

    long_sentences = (
        find_long_sentences(grade_justification or "")
        + find_long_sentences(" ".join(dangers))
        + find_long_sentences(" ".join(benefits))
    )
    checks["no_long_sentences"] = not long_sentences
    if long_sentences:
        warnings.append(f"Sentences exceed 35 words: {len(long_sentences)} found.")

    balance_ok = check_dangers_benefits_balance(dangers, benefits, grade_justification or "")
    checks["dangers_benefits_balance"] = balance_ok
    if not balance_ok:
        warnings.append("Dangers/benefits imbalance not acknowledged in grade justification.")

    rights_ok, rights_ratio = check_rights_have_paths(your_rights)
    checks["rights_have_paths"] = rights_ok
    if not rights_ok:
        warnings.append(f"Your rights lack exercise paths (ratio {rights_ratio:.0%}).")

    actions_ok, actions_ratio = check_actions_actionable(recommended_actions)
    checks["actions_actionable"] = actions_ok
    if not actions_ok:
        warnings.append(f"Recommended actions not actionable (ratio {actions_ratio:.0%}).")

    return OverviewValidationResult(
        should_re_roll=bool(re_roll_reasons),
        re_roll_reasons=re_roll_reasons,
        warnings=warnings,
        checks_passed=checks,
    )


def merge_llm_review(
    deterministic: OverviewValidationResult,
    llm_result: Any,
) -> OverviewValidationResult:
    """Merge LLM semantic review results into the deterministic result.

    ``llm_result`` is an ``LLMReviewResult`` (from ``llm_review.py``) or None.
    High-severity LLM failures are added to ``re_roll_reasons``; medium-severity
    failures are added to ``warnings``. The merged result's ``should_re_roll`` is
    True if either the deterministic or LLM checks warrant a re-roll.
    """
    if llm_result is None:
        return deterministic

    re_roll_reasons = list(deterministic.re_roll_reasons)
    warnings = list(deterministic.warnings)
    checks = dict(deterministic.checks_passed)

    for check in llm_result.checks:
        check_key = f"llm_{check.check.lower()}"
        checks[check_key] = check.passed
        if check.passed:
            continue
        desc = check.description or check.check
        if check.severity == "high":
            re_roll_reasons.append(f"[LLM] {check.check}: {desc}")
        else:
            warnings.append(f"[LLM] {check.check}: {desc}")

    return OverviewValidationResult(
        should_re_roll=bool(re_roll_reasons),
        re_roll_reasons=re_roll_reasons,
        warnings=warnings,
        checks_passed=checks,
    )
