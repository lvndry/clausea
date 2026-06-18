from src.models.document import CoverageItem, EvidenceSpan
from src.models.finding import AggregatedFinding, FindingConflict
from src.services.topic_stance_service import (
    compose_product_risk_from_topics,
    evaluate_topic_stances,
)


def test_evaluate_topic_stances_marks_missing_as_not_disclosed() -> None:
    rows = evaluate_topic_stances(
        findings=[],
        conflicts=[],
        coverage=[CoverageItem(category="data_sale", status="missing")],
    )
    assert rows["data_sale"]["status"] == "missing"
    assert rows["data_sale"]["stance"] == "not_disclosed"
    assert rows["data_sale"]["topic_score"] is None
    assert rows["data_sale"]["rationale_key"] == "topic.not_disclosed"


def test_evaluate_topic_stances_detects_yes_no_signals() -> None:
    findings = [
        AggregatedFinding(
            category="data_sale",
            value="sells_data: yes",
            documents=["doc_1"],
            evidence=[
                EvidenceSpan(document_id="doc_1", url="https://x", quote="We may sell data.")
            ],
        ),
        AggregatedFinding(
            category="security",
            value="Encryption at rest",
            documents=["doc_1", "doc_2"],
            evidence=[
                EvidenceSpan(document_id="doc_1", url="https://x", quote="We encrypt data at rest.")
            ],
        ),
    ]
    rows = evaluate_topic_stances(findings=findings, conflicts=[], coverage=None)
    assert rows["data_sale"]["status"] == "found"
    assert rows["data_sale"]["topic_score"] == 9
    assert rows["data_sale"]["stance"] == "high_risk"
    assert rows["data_sale"]["rationale_key"] == "topic.findings_summary"
    assert rows["data_sale"]["rationale_params"]["finding_count"] == 1
    assert rows["security"]["stance"] == "low_risk"


def test_evaluate_topic_stances_marks_conflicts_as_mixed() -> None:
    rows = evaluate_topic_stances(
        findings=[],
        conflicts=[
            FindingConflict(
                category="ai_training",
                description="Conflicting statements",
                document_ids=["doc_1", "doc_2"],
                evidence=[],
            )
        ],
        coverage=None,
    )
    assert rows["ai_training"]["status"] == "ambiguous"
    assert rows["ai_training"]["stance"] == "mixed"
    assert rows["ai_training"]["topic_score"] == 7
    assert rows["ai_training"]["rationale_key"] == "topic.conflicts_found"
    assert rows["ai_training"]["rationale_params"]["conflict_count"] == 1


def test_compose_product_risk_excludes_not_disclosed_topics() -> None:
    score = compose_product_risk_from_topics(
        {
            "data_collection": {"status": "found", "topic_score": 8},
            "data_sharing": {"status": "not_disclosed", "topic_score": 10},
            "security": {"status": "found", "topic_score": 2},
        }
    )
    # Must not be dragged toward 10 by undisclosed data_sharing.
    assert 3 <= score <= 6
