"""Validates that overview prose claims don't contradict privacy_signals."""

from typing import Any

# Map of strong prose phrases to the privacy_signals field that must support them
STRONG_CLAIM_SIGNAL_MAP: dict[str, str | None] = {
    "sells your": "sells_data",
    "sell your": "sells_data",
    "sale of your": "sells_data",
    "sells user": "sells_data",
    "data sale": "sells_data",
    "trains on": "ai_training_on_user_data",
    "training on": "ai_training_on_user_data",
    "train ai": "ai_training_on_user_data",
    "ai training on": "ai_training_on_user_data",
    "biometric": None,  # No signal field — requires verified citation
    "keystroke": None,
    "clipboard": None,
    "psychological profile": None,
    "psychological profiling": None,
}

# Head noun used to match a None-mapped phrase against verified citation quotes.
_CITATION_HEAD_NOUNS: dict[str, str] = {
    "biometric": "biometric",
    "keystroke": "keystroke",
    "clipboard": "clipboard",
    "psychological profile": "psychological",
    "psychological profiling": "psychological",
}

SIGNAL_YES_VALUES: frozenset[str] = frozenset({"yes"})
SIGNAL_AMBIGUOUS_VALUES: frozenset[str] = frozenset({"unclear", "not_specified"})


def _get_field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _signal_value(privacy_signals: dict[str, Any] | None, field: str) -> str | None:
    if not privacy_signals:
        return None
    raw = privacy_signals.get(field)
    if raw is None:
        return None
    return str(raw).lower()


def _verified_quote_supports(citations: list[dict[str, Any]] | None, head_noun: str) -> bool:
    if not citations:
        return False
    head_noun_lower = head_noun.lower()
    for citation in citations:
        if _get_field(citation, "verified") is not True:
            continue
        quote = _get_field(citation, "quote")
        if quote and head_noun_lower in str(quote).lower():
            return True
    return False


def find_signal_prose_contradictions(
    headline: str,
    summary: str,
    privacy_signals: dict[str, Any] | None,
    citations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Find prose claims that contradict or aren't supported by privacy_signals.

    Returns a list of contradiction dicts with:
    - phrase: the strong claim phrase found in prose
    - signal_field: the privacy_signals field it maps to (or None)
    - signal_value: the current signal value
    - issue: description of the contradiction
    """
    combined = f"{headline} {summary}".lower()
    issues: list[dict[str, Any]] = []

    for phrase, signal_field in STRONG_CLAIM_SIGNAL_MAP.items():
        if phrase not in combined:
            continue

        if signal_field is not None:
            value = _signal_value(privacy_signals, signal_field)
            if value is None or value in SIGNAL_YES_VALUES:
                continue
            if value == "no":
                issues.append(
                    {
                        "phrase": phrase,
                        "signal_field": signal_field,
                        "signal_value": value,
                        "issue": (
                            f"Prose claims '{phrase}' but privacy_signals.{signal_field} is 'no'."
                        ),
                    }
                )
            elif value in SIGNAL_AMBIGUOUS_VALUES:
                issues.append(
                    {
                        "phrase": phrase,
                        "signal_field": signal_field,
                        "signal_value": value,
                        "issue": (
                            f"Prose asserts '{phrase}' but "
                            f"privacy_signals.{signal_field} is '{value}' — "
                            "prose is more confident than the signal supports."
                        ),
                    }
                )
        else:
            head_noun = _CITATION_HEAD_NOUNS[phrase]
            if _verified_quote_supports(citations, head_noun):
                continue
            issues.append(
                {
                    "phrase": phrase,
                    "signal_field": None,
                    "signal_value": None,
                    "issue": (
                        f"Prose claims '{phrase}' but no verified citation "
                        f"supports the term '{head_noun}'."
                    ),
                }
            )

    return issues
