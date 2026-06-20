"""Batch LLM classification of legal-term consumer materiality.

Primary path: extraction and consumer-explainer prompts label ``materiality`` on
each danger/finding. This module fills gaps when labels are missing — one cheap
LLM call per document batches all unlabeled danger strings.

Tradeoffs (see also ``standard_terms``):
- Latency: +1 completion (~1–3s) when any danger lacks a label.
- Cost: small JSON batch on a fast/cheap model; skipped when extraction labels all items.
- Accuracy: context-aware vs regex; unlabeled text defaults to material_risk (conservative).
"""

from __future__ import annotations

import json
from typing import Any

from src.core.logging import get_logger
from src.llm import MODEL_PRIORITY, acompletion_with_fallback
from src.utils.standard_terms import TermMateriality, coerce_term_materiality

logger = get_logger(__name__)

_CLASSIFY_SYSTEM_PROMPT = """You classify legal/policy terms for consumer-facing risk surfacing.

For each input string, assign exactly one materiality tier:

- standard_industry — routine boilerplate most users expect (DMCA/repeat-infringer
  termination, non-assignable clauses, governing law, venue, severability, entire
  agreement, force majeure, standard warranty/limitation disclaimers).
- notable — dispute-resolution terms worth a medium informational note but not a
  headline danger (binding arbitration, class-action waiver, jury-trial waiver).
- material_risk — genuine consumer harm or meaningful loss of control (data sale,
  AI training on private content without opt-out, broad indemnification, hidden or
  auto-renewal billing, perpetual/irrevocable license to user content, sensitive
  data without limits, no deletion/opt-out, cross-site tracking, indefinite retention).

Judge full context and intent, not keywords alone. Combined clauses: if any part is
material_risk, classify material_risk. When genuinely uncertain, prefer material_risk.

Return JSON only:
{"items": [{"text": "<exact input string>", "materiality": "standard_industry|notable|material_risk"}]}
"""

_CLASSIFY_MODEL_PRIORITY = MODEL_PRIORITY[-3:]  # cheap/fast tail


async def classify_materiality_batch(texts: list[str]) -> dict[str, TermMateriality]:
    """Classify a batch of term strings; returns mapping text -> materiality."""
    unique = [t.strip() for t in texts if (t or "").strip()]
    unique = list(dict.fromkeys(unique))
    if not unique:
        return {}

    user_payload = json.dumps({"terms": unique}, ensure_ascii=False)
    try:
        response = await acompletion_with_fallback(
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            model_priority=_CLASSIFY_MODEL_PRIORITY,
            response_format={"type": "json_object"},
        )
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message else None
        if not content:
            logger.warning("Empty materiality classification response")
            return {}
        parsed = json.loads(content)
    except Exception as exc:
        logger.warning("Materiality batch classification failed: %s", exc)
        return {}

    return _parse_classification_response(parsed, expected=unique)


def _parse_classification_response(
    parsed: Any,
    *,
    expected: list[str],
) -> dict[str, TermMateriality]:
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return {}

    by_normalized: dict[str, TermMateriality] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        label = coerce_term_materiality(entry.get("materiality"))
        if text and label is not None:
            by_normalized[_norm_key(text)] = label

    result: dict[str, TermMateriality] = {}
    for text in expected:
        label = by_normalized.get(_norm_key(text))
        if label is not None:
            result[text] = label
    return result


def _norm_key(text: str) -> str:
    return " ".join(text.split()).lower()


async def filter_danger_strings_llm(values: list[str]) -> list[str]:
    """Classify overview danger strings via LLM, then drop boilerplate."""
    from src.utils.standard_terms import filter_danger_strings

    if not values:
        return []
    labels = await classify_materiality_batch(values)
    label_map: dict[str, TermMateriality | str] = dict(labels)
    return filter_danger_strings(values, labels=label_map)


async def enrich_extraction_materiality(extraction: Any) -> None:
    """Fill missing ``materiality`` on danger items in place."""
    dangers = getattr(extraction, "dangers", None) or []
    unlabeled = [item for item in dangers if not getattr(item, "materiality", None)]
    if not unlabeled:
        return

    labels = await classify_materiality_batch([item.value for item in unlabeled])
    if not labels:
        return

    for item in unlabeled:
        label = labels.get(item.value.strip())
        if label is not None:
            item.materiality = label


__all__ = [
    "classify_materiality_batch",
    "enrich_extraction_materiality",
    "filter_danger_strings_llm",
]
