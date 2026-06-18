"""Deterministic topic stance and headline risk composition."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from src.models.document import CoverageItem, InsightCategory
from src.models.finding import AggregatedFinding, FindingConflict
from src.models.topic_report import TopicStance


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
            if "ai_training_on_user_data: yes" in normalized:
                signals[category].append(8)
            elif "ai_training_on_user_data: no" in normalized:
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

    for item in coverage or []:
        if item.status == "missing":
            base_status = "missing"
        elif item.status == "not_analyzed":
            base_status = "not_disclosed"
        else:
            base_status = "found"
        by_topic[item.category] = {
            "status": base_status,
            "stance": "not_disclosed"
            if base_status in {"missing", "not_disclosed"}
            else "moderate_risk",
            "topic_score": None if base_status in {"missing", "not_disclosed"} else 5,
            "rationale": "No evidence extracted for this topic yet."
            if base_status in {"missing", "not_disclosed"}
            else "Evidence present for this topic.",
            "finding_count": 0,
            "conflict_count": 0,
            "evidence_count": 0,
            "document_count": 0,
        }

    signal_values = _signals_from_findings(findings)
    for finding in findings:
        topic = finding.category
        if topic not in by_topic:
            by_topic[topic] = {
                "status": "found",
                "stance": "moderate_risk",
                "topic_score": 5,
                "rationale": "Evidence present for this topic.",
                "finding_count": 0,
                "conflict_count": 0,
                "evidence_count": 0,
                "document_count": 0,
            }
        row = by_topic[topic]
        row["status"] = "found"
        row["finding_count"] += 1
        row["evidence_count"] += len(finding.evidence)
        row["document_count"] += len(set(finding.documents))

    for topic, values in signal_values.items():
        if topic not in by_topic:
            by_topic[topic] = {
                "status": "found",
                "stance": "moderate_risk",
                "topic_score": 5,
                "rationale": "Evidence present for this topic.",
                "finding_count": 0,
                "conflict_count": 0,
                "evidence_count": 0,
                "document_count": 0,
            }
        score = round(sum(values) / len(values)) if values else 5
        by_topic[topic]["topic_score"] = score
        by_topic[topic]["stance"] = _score_to_stance(score)

    conflicts_by_topic: dict[InsightCategory, list[FindingConflict]] = defaultdict(list)
    for conflict in conflicts:
        conflicts_by_topic[conflict.category].append(conflict)
        if conflict.category not in by_topic:
            by_topic[conflict.category] = {
                "status": "ambiguous",
                "stance": "mixed",
                "topic_score": 6,
                "rationale": "Conflicting statements found across documents.",
                "finding_count": 0,
                "conflict_count": 0,
                "evidence_count": 0,
                "document_count": 0,
            }

        row = by_topic[conflict.category]
        row["status"] = "ambiguous"
        row["stance"] = "mixed"
        row["conflict_count"] += 1
        row["evidence_count"] += len(conflict.evidence)
        row["document_count"] += len(set(conflict.document_ids))
        current = row.get("topic_score")
        row["topic_score"] = min(10, (current if isinstance(current, int) else 6) + 1)

    for _topic, row in by_topic.items():
        if row["status"] in {"missing", "not_disclosed"}:
            row["rationale"] = "Topic is not disclosed in analyzed documents."
            continue
        if row["status"] == "ambiguous":
            row["rationale"] = (
                f"{row['conflict_count']} conflict(s) found across {row['document_count']} document(s)."
            )
            continue
        row["rationale"] = (
            f"{row['finding_count']} finding(s) across {row['document_count']} document(s) "
            f"with {row['evidence_count']} evidence span(s)."
        )

    return by_topic


_TOPIC_WEIGHT_DEFAULTS: dict[InsightCategory, float] = {
    "data_collection": 0.18,
    "data_sharing": 0.18,
    "user_rights": 0.14,
    "retention": 0.10,
    "security": 0.10,
    "cookies_tracking": 0.10,
    "data_sale": 0.12,
    "ai_training": 0.08,
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
