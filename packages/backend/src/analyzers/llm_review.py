"""LLM-based semantic quality review for product overviews.

Replaces hardcoded lexicon checks (jargon, generic openers, strong-claim
validation, signal/prose contradictions, internal-state language) with a
single cheap-model LLM call that understands context and paraphrase.

Deterministic checks (length, emptiness, counts, citation coverage) stay in
``overview_guards.py`` — only semantic checks are delegated here.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from src.core.logging import get_logger
from src.llm import MODEL_PRIORITY, acompletion_with_fallback

logger = get_logger(__name__)

_REVIEW_MODEL_PRIORITY = MODEL_PRIORITY[-3:]

_REVIEW_SYSTEM_PROMPT = """You review a privacy-policy product overview for quality issues.

You will receive the overview's customer-facing fields and the privacy_signals.
Check for these specific problems:

1. UNSUPPORTED_CLAIMS: Does the headline or summary assert a strong claim (data sale,
   biometric collection, AI training, indefinite retention, psychological profiling)
   that is NOT supported by the privacy_signals or the evidence provided? A claim is
   supported when the corresponding signal is "yes" OR verified citations contain
   evidence for it. "Shares for advertising" is NOT the same as "sells" — flag
   overstated wording.

2. SIGNAL_CONTRADICTIONS: Does the prose say something that contradicts privacy_signals?
   E.g. prose says "sells your data" but sells_data is "no". Or prose says "trains AI
   on your data" but ai_training_on_user_data is "no".

3. LEGAL_JARGON: Are there legal terms a non-lawyer wouldn't understand in the summary,
   headline, grade_justification, dangers, or benefits? Terms like "notwithstanding",
   "hereunder", "sub-processor", "data controller", "standard contractual clauses"
   should be flagged. Common tech terms (encryption, GDPR, opt-out) are fine.

4. GENERIC_HEADLINE: Is the headline a generic opener that could apply to any product?
   E.g. "X collects extensive personal and behavioral data" is generic. "Spotify sells
   your listening history to advertisers" is specific.

5. INTERNAL_STATE_LANGUAGE: Does any customer-facing text expose pipeline internals?
   Phrases like "the analyzed document", "the extraction shows", "the policy bundle",
   "core documents", "source documents" should NOT appear in customer-facing text.

6. JARGON_IN_RIGHTS_OR_ACTIONS: Are your_rights or recommended_actions written in
   legal language instead of plain English a person can follow?

For each check, set `failure` to null when the check passes. When the check fails,
set `failure` to a specific description of the defect. Do not use a separate
pass boolean — pass/fail is determined solely by whether `failure` is null.

Return JSON only:
{
  "checks": [
    {"check": "UNSUPPORTED_CLAIMS", "severity": "high|medium", "failure": null | "specific issue"},
    {"check": "SIGNAL_CONTRADICTIONS", "severity": "high|medium", "failure": null | "..."},
    {"check": "LEGAL_JARGON", "severity": "medium", "failure": null | "..."},
    {"check": "GENERIC_HEADLINE", "severity": "medium", "failure": null | "..."},
    {"check": "INTERNAL_STATE_LANGUAGE", "severity": "high", "failure": null | "..."},
    {"check": "JARGON_IN_RIGHTS_OR_ACTIONS", "severity": "medium", "failure": null | "..."}
  ]
}
"""


def _parse_check_passed(raw: dict[str, Any]) -> bool:
    """Pass when failure is absent or empty; legacy responses may still use pass=true."""
    if "failure" in raw:
        failure = raw.get("failure")
        if failure is None:
            return True
        if isinstance(failure, str) and not failure.strip():
            return True
        return False
    return bool(raw.get("pass", False))


class LLMReviewCheck(BaseModel):
    check: str
    passed: bool
    severity: str = "medium"
    description: str = ""


class LLMReviewResult(BaseModel):
    checks: list[LLMReviewCheck]
    raw_response: str | None = None

    @property
    def high_severity_failures(self) -> list[LLMReviewCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "high"]

    @property
    def medium_severity_failures(self) -> list[LLMReviewCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "medium"]


def _build_review_payload(overview: dict[str, Any], citations: list[dict[str, Any]]) -> str:
    """Extract customer-facing fields + signals + evidence for the review prompt."""
    privacy_signals = overview.get("privacy_signals") or {}

    verified_quotes: list[str] = []
    for citation in citations:
        quote = (
            citation.get("quote")
            if isinstance(citation, dict)
            else getattr(citation, "quote", None)
        )
        verified = (
            citation.get("verified")
            if isinstance(citation, dict)
            else getattr(citation, "verified", None)
        )
        if verified is True and quote:
            verified_quotes.append(str(quote)[:300])

    payload = {
        "headline_claim": overview.get("headline_claim"),
        "summary": overview.get("summary"),
        "grade": overview.get("grade"),
        "grade_justification": overview.get("grade_justification"),
        "privacy_signals": privacy_signals,
        "dangers": overview.get("dangers") or [],
        "benefits": overview.get("benefits") or [],
        "your_rights": overview.get("your_rights") or [],
        "recommended_actions": overview.get("recommended_actions") or [],
        "evidence_quotes": verified_quotes[:20],
    }
    return json.dumps(payload, ensure_ascii=False)


async def llm_review_overview(
    overview: dict[str, Any],
    citations: list[dict[str, Any]],
) -> LLMReviewResult | None:
    """Run a single LLM quality-review call on the overview.

    Returns None if the LLM call fails (fail-open — deterministic checks still run).
    """
    payload = _build_review_payload(overview, citations)

    try:
        response = await acompletion_with_fallback(
            messages=[
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
            model_priority=_REVIEW_MODEL_PRIORITY,
            response_format={"type": "json_object"},
        )
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message else None
        if not content:
            logger.warning("Empty LLM review response")
            return None

        parsed = json.loads(content)
        raw_checks = parsed.get("checks") or []
        checks = [
            LLMReviewCheck(
                check=str(c.get("check", "unknown")),
                passed=_parse_check_passed(c),
                severity=str(c.get("severity", "medium")),
                description=str(c.get("failure") or c.get("description") or ""),
            )
            for c in raw_checks
            if isinstance(c, dict)
        ]
        return LLMReviewResult(checks=checks, raw_response=content)
    except Exception as exc:
        logger.warning("LLM overview review failed: %s", exc)
        return None
