"""Post-generation validators for product overviews.

Server-side quality guards run after the LLM produces a product overview and it
is parsed into the ``MetaSummary`` shape. They surface two severity tiers:

- high severity -> the overview should be re-rolled (e.g. empty headline with
  adequate evidence, an E grade assigned for silence, strong claims with no
  supporting evidence, pipeline-internal language leaking into customer text).
- medium severity -> warnings only (length overages, long sentences, jargon,
  dangers/benefits imbalance, non-actionable rights/actions, generic openers).

The top-level entry point is :func:`validate_overview`, which returns an
:class:`OverviewValidationResult`. Individual validators are exposed so callers
can run targeted checks during partial re-generation.
"""

import re
from typing import Any

from pydantic import BaseModel

from src.analyzers.signal_consistency import find_signal_prose_contradictions

_SUMMARY_MAX_WORDS = 20
_HEADLINE_MAX_WORDS = 25
_SENTENCE_DEFAULT_MAX_WORDS = 35

_INTERNAL_STATE_PHRASES: tuple[str, ...] = (
    "analyzed document",
    "the document",
    "the extraction",
    "the policy bundle",
    "core documents",
    "the provided documents",
    "source documents",
)

_SILENCE_STATUSES: frozenset[str] = frozenset({"missing", "not_disclosed"})

_BALANCE_ACK_PHRASES: tuple[str, ...] = (
    "few protections",
    "documents describe few",
    "limited protections",
    "no documented protections",
)

_GENERIC_OPENERS: tuple[str, ...] = (
    "collects extensive",
    "collects a wide",
    "collects broad",
    "shares your data with",
    "collects personal and behavioral",
)

_JARGON_LEXICON: tuple[str, ...] = (
    "notwithstanding",
    "hereunder",
    "herein",
    "therein",
    "hereto",
    "thereunder",
    "inter alia",
    "ipso facto",
    "force majeure",
    "indemnifi",
    "sub-processor",
    "subprocessor",
    "data controller",
    "data processor",
    "standard contractual clauses",
    "adequacy decision",
)

_STRONG_CLAIM_LEXICON: tuple[tuple[str, str, str | None, str | None], ...] = (
    (r"sells your", "sell", "sells_data", "yes"),
    (r"sale of your", "sale", "sells_data", "yes"),
    (r"data sale", "sale", "sells_data", "yes"),
    (r"sells user", "sell", "sells_data", "yes"),
    (r"sell your", "sell", "sells_data", "yes"),
    (r"biometric", "biometric", None, None),
    (r"keystroke", "keystroke", None, None),
    (r"clipboard", "clipboard", None, None),
    (r"psychological profile", "psychological", None, None),
    (r"psychological profiling", "psychological", None, None),
    (r"trains on", "train", "ai_training_on_user_data", "yes"),
    (r"training on", "training", "ai_training_on_user_data", "yes"),
    (r"train ai", "train", "ai_training_on_user_data", "yes"),
    (r"ai training on", "training", "ai_training_on_user_data", "yes"),
    (r"indefinitely after", "indefinitely", None, None),
    (r"retains.*indefinitely", "indefinitely", None, None),
    (r"perpetual.*license", "license", None, None),
)

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


def find_internal_state_language(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    return [phrase for phrase in _INTERNAL_STATE_PHRASES if phrase in lowered]


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
    if total == 0:
        return False
    return silent / total > 0.7 and total_evidence == 0


def find_unsupported_strong_claims(
    headline: str,
    summary: str,
    citations: list[dict[str, Any]],
    privacy_signals: dict[str, Any] | None,
) -> list[str]:
    combined = f"{headline} {summary}".lower()
    verified_quotes: list[str] = []
    for citation in citations:
        quote = _get_field(citation, "quote")
        if _get_field(citation, "verified") is True and quote:
            verified_quotes.append(str(quote).lower())
    signals = privacy_signals or {}

    unsupported: list[str] = []
    for pattern, head_noun, signal_field, signal_value in _STRONG_CLAIM_LEXICON:
        if not re.search(pattern, combined, re.IGNORECASE):
            continue
        citation_supports = any(head_noun in quote for quote in verified_quotes)
        signal_supports = (
            signal_field is not None and _get_field(signals, signal_field) == signal_value
        )
        if not citation_supports and not signal_supports:
            unsupported.append(pattern)
    return unsupported


def check_dangers_benefits_balance(
    dangers: list[str], benefits: list[str], grade_justification: str
) -> bool:
    if len(dangers) < 5:
        return True
    if len(benefits) >= 2:
        return True
    if not grade_justification:
        return False
    lowered = grade_justification.lower()
    return any(phrase in lowered for phrase in _BALANCE_ACK_PHRASES)


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


def check_jargon(text: str, max_hits: int = 3) -> bool:
    if not text:
        return True
    lowered = text.lower()
    hits = sum(1 for term in _JARGON_LEXICON if term in lowered)
    return hits <= max_hits


def check_generic_headline_opener(headline: str) -> bool:
    if not headline or not headline.strip():
        return True
    words = re.findall(r"\b\w+\b", headline.lower())
    opener = " ".join(words[:6])
    return not any(pattern in opener for pattern in _GENERIC_OPENERS)


def _collect_citations(topic_stances: list[Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for stance in topic_stances:
        supporting = _get_field(stance, "supporting_citations")
        if isinstance(supporting, list):
            for citation in supporting:
                if isinstance(citation, dict):
                    citations.append(citation)
    return citations


def validate_overview(
    overview: dict[str, Any], has_adequate_evidence: bool
) -> OverviewValidationResult:
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
    privacy_signals = overview.get("privacy_signals")
    topic_stances = overview.get("topic_stances") or []
    citations = _collect_citations(topic_stances)

    checks: dict[str, bool] = {}
    re_roll_reasons: list[str] = []
    warnings: list[str] = []

    headline_ok = validate_headline_not_empty(headline, has_adequate_evidence)
    checks["headline_not_empty"] = headline_ok
    if not headline_ok:
        re_roll_reasons.append("Headline is empty despite adequate evidence.")

    e_on_silence = check_e_grade_on_silence(grade, topic_stances)
    checks["no_e_grade_on_silence"] = not e_on_silence
    if e_on_silence:
        re_roll_reasons.append("Grade E assigned for silence rather than evidence.")

    unsupported = find_unsupported_strong_claims(
        headline or "", summary, citations, privacy_signals
    )
    checks["no_unsupported_strong_claims"] = not unsupported
    if unsupported:
        re_roll_reasons.append("Strong claims lack supporting evidence: " + ", ".join(unsupported))

    signal_contradictions = find_signal_prose_contradictions(
        headline or "", summary, privacy_signals, citations
    )
    checks["no_signal_prose_contradictions"] = not signal_contradictions
    if signal_contradictions:
        contradiction_descs = "; ".join(c.get("issue", "unknown") for c in signal_contradictions)
        re_roll_reasons.append(f"Signal/prose contradictions: {contradiction_descs}")

    internal_state_hits = {
        "summary": find_internal_state_language(summary),
        "headline": find_internal_state_language(headline or ""),
        "grade_justification": find_internal_state_language(grade_justification or ""),
    }
    no_internal_state = all(not hits for hits in internal_state_hits.values())
    checks["no_internal_state_language"] = no_internal_state
    if not no_internal_state:
        locations = ", ".join(
            f"{loc}: {', '.join(hits)}" for loc, hits in internal_state_hits.items() if hits
        )
        re_roll_reasons.append(f"Customer-facing text exposes pipeline internals ({locations}).")

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

    opener_ok = check_generic_headline_opener(headline or "")
    checks["headline_opener_specific"] = opener_ok
    if not opener_ok:
        warnings.append("Headline opener is generic.")

    jargon_text = f"{summary} {headline or ''} {grade_justification or ''}"
    jargon_ok = check_jargon(jargon_text)
    checks["no_jargon"] = jargon_ok
    if not jargon_ok:
        warnings.append("Customer-facing text contains legal jargon.")

    return OverviewValidationResult(
        should_re_roll=bool(re_roll_reasons),
        re_roll_reasons=re_roll_reasons,
        warnings=warnings,
        checks_passed=checks,
    )
