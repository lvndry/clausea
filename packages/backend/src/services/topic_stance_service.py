"""Deterministic topic stance and headline risk composition."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from src.models.document import CoverageItem, InsightCategory
from src.models.finding import AggregatedFinding, FindingConflict
from src.models.topic_report import TopicStance

_YES_TOKENS = {"yes", "true", "1"}
_NO_TOKENS = {"no", "false", "0"}
_UNCLEAR_TOKENS = {"unclear", "unknown", "null", "none", ""}

_AI_TRAINING_FLAG_PATTERN = re.compile(
    r"""
    ["']?(?:ai_training_on_user_data|training_on_user_data|ai-training-on-user-data)["']?
    \s*[:=]\s*
    ["']?(yes|no|true|false|1|0|unclear|null|unknown|none)["']?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _coerce_yes_no_unclear(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _YES_TOKENS:
        return "yes"
    if normalized in _NO_TOKENS:
        return "no"
    if normalized in _UNCLEAR_TOKENS:
        return "unclear"
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


def _ai_training_signal_from_value(value: str) -> str | None:
    match = _AI_TRAINING_FLAG_PATTERN.search(value or "")
    if not match:
        return None
    parsed = _coerce_yes_no_unclear(match.group(1))
    if parsed in {"yes", "no"}:
        return parsed
    return "unclear"


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
    lower = text.lower()
    if any(term in lower for term in ("indefinite", "forever", "permanent", "as long as")):
        return 8
    if any(term in lower for term in ("delete", "deletion", "remove")) and any(
        term in lower for term in ("30 day", "60 day", "90 day", "month")
    ):
        return 3
    year_match = re.search(r"(\d+)\s*year", lower)
    if year_match:
        years = int(year_match.group(1))
        if years >= 5:
            return 8
        if years >= 2:
            return 6
        return 5
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

        if category in {"international_transfers", "dispute_resolution", "indemnification"}:
            signals[category].append(6)
            continue

        if category == "dangers":
            signals[category].append(8)
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
        row["rationale_key"] = "topic.findings_summary"
        row["rationale_params"] = {
            "finding_count": row["finding_count"],
            "document_count": row["document_count"],
            "evidence_count": row["evidence_count"],
        }
        row["rationale"] = _render_rationale(row["rationale_key"], row["rationale_params"])

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
