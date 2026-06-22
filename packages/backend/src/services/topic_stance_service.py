"""Deterministic topic stance and headline risk composition."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from src.models.document import CoverageItem, InsightCategory
from src.models.finding import AggregatedFinding, FindingConflict
from src.models.topic_report import TopicStance
from src.services.evidence_relevance import (
    MIN_SUBSTANTIVE_CITATIONS_FOR_ELEVATED_RISK,
    count_substantive_evidence,
)
from src.utils.standard_terms import (
    finding_materiality_label,
    should_exclude_from_dangers,
    topic_signal_score,
)

_YES_TOKENS = {"yes", "true", "1"}
_NO_TOKENS = {"no", "false", "0"}
_UNCLEAR_TOKENS = {"unclear", "unknown", "null", "none", ""}


def _coerce_yes_no_unclear(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _YES_TOKENS:
        return "yes"
    if normalized in _NO_TOKENS:
        return "no"
    if normalized in _UNCLEAR_TOKENS:
        return "unclear"
    return None


def _ai_training_signal_from_value(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("ai_training_on_user_data", "training_on_user_data", "AI_TRAINING_ON_USER_DATA"):
        parsed = _coerce_yes_no_unclear(payload.get(key))
        if parsed in {"yes", "no"}:
            return parsed
    return None


def _ai_training_signal_from_attributes(attributes: list[dict[str, Any]]) -> str | None:
    for attr in attributes:
        direct = _coerce_yes_no_unclear(attr.get("ai_training_on_user_data"))
        if direct in {"yes", "no"}:
            return direct

        alias = _coerce_yes_no_unclear(attr.get("training_on_user_data"))
        if alias in {"yes", "no"}:
            return alias

        usage_type = str(attr.get("usage_type") or "").strip().lower()
        if usage_type == "training_on_user_data":
            return "yes"

    return None


def _resolve_ai_training_signal(*, value: str, attributes: list[dict[str, Any]]) -> str | None:
    from_attributes = _ai_training_signal_from_attributes(attributes)
    if from_attributes is not None:
        return from_attributes
    return _ai_training_signal_from_value(value)


def _render_rationale(rationale_key: str, params: dict[str, int | str | None] | None = None) -> str:
    data = params or {}
    if rationale_key == "topic.not_disclosed":
        return "Topic is not disclosed in analyzed documents."
    if rationale_key == "topic.conflicts_found":
        return (
            f"{data.get('conflict_count', 0)} conflict(s) found across "
            f"{data.get('document_count', 0)} document(s)."
        )
    if rationale_key == "topic.findings_summary":
        return (
            f"{data.get('finding_count', 0)} finding(s) across "
            f"{data.get('document_count', 0)} document(s) with "
            f"{data.get('evidence_count', 0)} evidence span(s)."
        )
    if rationale_key == "topic.thin_evidence":
        return (
            "Only "
            f"{data.get('substantive_evidence_count', 0)} substantive citation(s) "
            "support this topic, so risk is treated as low until more evidence appears."
        )
    if rationale_key == "topic.positive_practice":
        return "Documents describe clear protective practices for this topic."
    # fallback to generic deterministic sentence
    return "Evidence present for this topic."


def _topic_row(
    *,
    status: str,
    stance: str,
    topic_score: int | None,
    rationale_key: str,
    rationale_params: dict[str, int | str | None] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "stance": stance,
        "topic_score": topic_score,
        "rationale_key": rationale_key,
        "rationale_params": rationale_params,
        "rationale": _render_rationale(rationale_key, rationale_params),
        "finding_count": 0,
        "conflict_count": 0,
        "evidence_count": 0,
        "document_count": 0,
    }


def _map_sensitivity_to_risk(value: str | None) -> int:
    mapping = {
        "low": 2,
        "medium": 5,
        "high": 7,
        "sensitive": 8,
    }
    return mapping.get((value or "").strip().lower(), 5)


def _map_sharing_risk_level(value: str | None) -> int:
    mapping = {"low": 3, "medium": 6, "high": 8}
    return mapping.get((value or "").strip().lower(), 6)


def _parse_duration_risk(text: str) -> int:
    """Conservative default when retention duration is not structured in attributes."""
    _ = text
    return 5


def _signals_from_findings(findings: list[AggregatedFinding]) -> dict[InsightCategory, list[int]]:
    """Map aggregated findings to deterministic per-topic signal values."""
    signals: dict[InsightCategory, list[int]] = defaultdict(list)

    for finding in findings:
        category = finding.category
        normalized = finding.value.lower()
        attrs = finding.attributes or []

        if category == "data_sale":
            if "sells_data: yes" in normalized:
                signals[category].append(9)
            elif "sells_data: no" in normalized:
                signals[category].append(2)
            else:
                signals[category].append(6)
            continue

        if category == "ai_training":
            training_signal = _resolve_ai_training_signal(value=finding.value, attributes=attrs)
            if training_signal == "yes":
                signals[category].append(8)
            elif training_signal == "no":
                signals[category].append(3)
            else:
                signals[category].append(6)
            continue

        if category == "breach_notification":
            if "breach_notification: yes" in normalized:
                signals[category].append(3)
            elif "breach_notification: no" in normalized:
                signals[category].append(7)
            else:
                signals[category].append(5)
            continue

        if category == "children":
            if "children_data_collection: yes" in normalized:
                signals[category].append(8)
            elif "children_data_collection: no" in normalized:
                signals[category].append(3)
            else:
                # Children-policy findings can be either protective or risky; keep conservative.
                signals[category].append(6)
            continue

        if category == "data_collection":
            if not attrs:
                signals[category].append(5)
                continue
            for attr in attrs:
                sensitivity = _map_sensitivity_to_risk(str(attr.get("sensitivity")))
                required_boost = 1 if str(attr.get("required", "")).lower() == "required" else 0
                signals[category].append(min(10, sensitivity + required_boost))
            continue

        if category == "data_sharing":
            if not attrs:
                signals[category].append(6)
                continue
            for attr in attrs:
                signals[category].append(_map_sharing_risk_level(str(attr.get("risk_level"))))
            continue

        if category == "cookies_tracking":
            if not attrs:
                signals[category].append(6)
                continue
            for attr in attrs:
                third_party = bool(attr.get("third_party"))
                category_value = str(attr.get("category", "")).lower()
                score = 7 if third_party else 5
                if category_value == "advertising":
                    score = max(score, 8)
                signals[category].append(score)
            continue

        if category == "retention":
            if not attrs:
                signals[category].append(_parse_duration_risk(finding.value))
                continue
            for attr in attrs:
                duration = str(attr.get("duration") or finding.value)
                signals[category].append(_parse_duration_risk(duration))
            continue

        if category == "security":
            # Presence of concrete security measures lowers risk.
            security_signal = 3 if len(finding.documents) >= 2 else 4
            signals[category].append(security_signal)
            continue

        if category == "user_rights":
            # Rights disclosures are generally protective.
            rights_signal = 3 if len(finding.documents) >= 2 else 4
            signals[category].append(rights_signal)
            continue

        if category in {"government_access", "liability", "scope_expansion"}:
            signals[category].append(7)
            continue

        label = finding_materiality_label(finding.attributes)

        if category == "indemnification":
            signals[category].append(
                topic_signal_score(finding.value, category=category, materiality=label)
            )
            continue

        if category in {"international_transfers", "dispute_resolution"}:
            signals[category].append(
                topic_signal_score(finding.value, category=category, materiality=label)
            )
            continue

        if category in {"termination_consequences", "content_ownership"}:
            signals[category].append(
                topic_signal_score(finding.value, category=category, materiality=label)
            )
            continue

        if category == "dangers":
            if should_exclude_from_dangers(finding.value, materiality=label):
                continue
            signals[category].append(
                topic_signal_score(finding.value, category=category, materiality=label)
            )
            continue

        if category == "benefits":
            signals[category].append(3)
            continue

        # Default conservative neutral signal for less-sensitive categories.
        signals[category].append(5)

    return signals


def _score_to_stance(score: int) -> TopicStance:
    if score <= 3:
        return "low_risk"
    if score <= 6:
        return "moderate_risk"
    return "high_risk"


_PROTECTIVE_TOPICS: frozenset[InsightCategory] = frozenset(
    {"benefits", "security", "user_rights", "breach_notification"}
)


def _count_topic_substantive_evidence(
    *,
    topic: InsightCategory,
    findings: list[AggregatedFinding],
    conflicts: list[FindingConflict],
) -> int:
    total = 0
    for finding in findings:
        if finding.category != topic:
            continue
        total += count_substantive_evidence(
            finding.evidence,
            category=finding.category,
            finding_value=finding.value,
        )
    for conflict in conflicts:
        if conflict.category != topic:
            continue
        total += count_substantive_evidence(
            conflict.evidence,
            category=conflict.category,
            finding_value=conflict.description,
        )
    return total


def _apply_evidence_sufficiency_cap(row: dict[str, Any], substantive_count: int) -> None:
    """Downgrade topics with fewer than three substantive citations to low risk."""
    if row["status"] in {"missing", "not_disclosed"}:
        return
    if row["stance"] == "mixed":
        return
    if substantive_count >= MIN_SUBSTANTIVE_CITATIONS_FOR_ELEVATED_RISK:
        return

    current_score = row.get("topic_score")
    row["topic_score"] = min(current_score if isinstance(current_score, int) else 5, 3)
    row["stance"] = "low_risk"
    row["rationale_key"] = "topic.thin_evidence"
    row["rationale_params"] = {
        "finding_count": row.get("finding_count", 0),
        "document_count": row.get("document_count", 0),
        "evidence_count": row.get("evidence_count", 0),
        "substantive_evidence_count": substantive_count,
    }
    row["rationale"] = _render_rationale(row["rationale_key"], row["rationale_params"])


def _apply_positive_practice_rationale(topic: InsightCategory, row: dict[str, Any]) -> None:
    """Surface low-risk protective topics with a positive rationale when evidence is solid."""
    if row["status"] != "found" or row["stance"] != "low_risk":
        return
    if row.get("rationale_key") == "topic.thin_evidence":
        return
    if topic not in _PROTECTIVE_TOPICS:
        return
    row["rationale_key"] = "topic.positive_practice"
    row["rationale_params"] = {
        "finding_count": row.get("finding_count", 0),
        "document_count": row.get("document_count", 0),
        "evidence_count": row.get("evidence_count", 0),
    }
    row["rationale"] = _render_rationale(row["rationale_key"], row["rationale_params"])


def evaluate_topic_stances(
    *,
    findings: list[AggregatedFinding],
    conflicts: list[FindingConflict],
    coverage: list[CoverageItem] | None,
) -> dict[InsightCategory, dict[str, Any]]:
    """Return deterministic stance/status/score per topic.

    Each output item contains:
    - status: found | missing | not_disclosed | ambiguous
    - stance: low_risk | moderate_risk | high_risk | not_disclosed | mixed
    - topic_score: 0-10 risk (None when undisclosed)
    - rationale: concise deterministic explanation
    """
    by_topic: dict[InsightCategory, dict[str, Any]] = {}
    topic_document_ids: defaultdict[InsightCategory, set[str]] = defaultdict(set)

    for item in coverage or []:
        if item.status == "missing":
            base_status = "missing"
        elif item.status == "not_analyzed":
            base_status = "not_disclosed"
        else:
            base_status = "found"
        if base_status in {"missing", "not_disclosed"}:
            by_topic[item.category] = _topic_row(
                status=base_status,
                stance="not_disclosed",
                topic_score=None,
                rationale_key="topic.not_disclosed",
            )
        else:
            by_topic[item.category] = _topic_row(
                status=base_status,
                stance="moderate_risk",
                topic_score=5,
                rationale_key="topic.found_generic",
            )

    signal_values = _signals_from_findings(findings)
    for finding in findings:
        topic = finding.category
        if topic not in by_topic:
            by_topic[topic] = _topic_row(
                status="found",
                stance="moderate_risk",
                topic_score=5,
                rationale_key="topic.found_generic",
            )
        row = by_topic[topic]
        row["status"] = "found"
        row["finding_count"] += 1
        row["evidence_count"] += len(finding.evidence)
        topic_document_ids[topic].update(finding.documents)

    for topic, values in signal_values.items():
        if topic not in by_topic:
            by_topic[topic] = _topic_row(
                status="found",
                stance="moderate_risk",
                topic_score=5,
                rationale_key="topic.found_generic",
            )
        score = round(sum(values) / len(values)) if values else 5
        by_topic[topic]["topic_score"] = score
        by_topic[topic]["stance"] = _score_to_stance(score)

    for conflict in conflicts:
        if conflict.category not in by_topic:
            by_topic[conflict.category] = _topic_row(
                status="ambiguous",
                stance="mixed",
                topic_score=6,
                rationale_key="topic.conflicts_found",
                rationale_params={"conflict_count": 1, "document_count": 0},
            )

        row = by_topic[conflict.category]
        row["status"] = "ambiguous"
        row["stance"] = "mixed"
        row["conflict_count"] += 1
        row["evidence_count"] += len(conflict.evidence)
        topic_document_ids[conflict.category].update(conflict.document_ids)
        current = row.get("topic_score")
        row["topic_score"] = min(10, (current if isinstance(current, int) else 6) + 1)

    for topic, row in by_topic.items():
        row["document_count"] = len(topic_document_ids[topic])
        substantive_count = _count_topic_substantive_evidence(
            topic=topic,
            findings=findings,
            conflicts=conflicts,
        )
        _apply_evidence_sufficiency_cap(row, substantive_count)
        if row["status"] in {"missing", "not_disclosed"}:
            row["rationale_key"] = "topic.not_disclosed"
            row["rationale_params"] = None
            row["rationale"] = _render_rationale(row["rationale_key"], row["rationale_params"])
            continue
        if row["status"] == "ambiguous":
            row["rationale_key"] = "topic.conflicts_found"
            row["rationale_params"] = {
                "conflict_count": row["conflict_count"],
                "document_count": row["document_count"],
            }
            row["rationale"] = _render_rationale(row["rationale_key"], row["rationale_params"])
            continue
        if row.get("rationale_key") != "topic.thin_evidence":
            row["rationale_key"] = "topic.findings_summary"
            row["rationale_params"] = {
                "finding_count": row["finding_count"],
                "document_count": row["document_count"],
                "evidence_count": row["evidence_count"],
            }
            row["rationale"] = _render_rationale(row["rationale_key"], row["rationale_params"])
        _apply_positive_practice_rationale(topic, row)

    return by_topic


_TOPIC_WEIGHT_DEFAULTS: dict[InsightCategory, float] = {
    # High-impact privacy posture drivers.
    "data_collection": 0.16,
    "data_sharing": 0.16,
    "ai_training": 0.16,
    "data_sale": 0.14,
    # Secondary but still meaningful controls.
    "user_rights": 0.12,
    "retention": 0.10,
    "security": 0.09,
    "cookies_tracking": 0.07,
}


def compose_product_risk_from_topics(topic_rows: dict[InsightCategory, dict[str, Any]]) -> int:
    """Compose product headline risk from per-topic deterministic scores.

    Topics with status ``not_disclosed`` are intentionally excluded from weighting so silence
    is not auto-scored as worst-case.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    for topic, row in topic_rows.items():
        score = row.get("topic_score")
        status = row.get("status")
        if not isinstance(score, int):
            continue
        if status in {"not_disclosed", "missing"}:
            continue
        weight = _TOPIC_WEIGHT_DEFAULTS.get(topic, 0.05)
        weighted_sum += score * weight
        weight_total += weight

    if weight_total <= 0:
        return 5
    return max(0, min(10, round(weighted_sum / weight_total)))
