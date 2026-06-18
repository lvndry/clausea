from src.models.document import CoverageItem, DocumentSummary, EvidenceSpan
from src.models.finding import AggregatedFinding, Aggregation, FindingConflict
from src.services.topic_report_service import build_product_topic_report


def _documents() -> list[DocumentSummary]:
    return [
        DocumentSummary(
            id="doc_1",
            title="Privacy Policy",
            doc_type="privacy_policy",
            url="https://example.com/privacy",
        ),
        DocumentSummary(
            id="doc_2",
            title="Security Policy",
            doc_type="security_policy",
            url="https://example.com/security",
        ),
    ]


def test_build_product_topic_report_includes_cross_document_citations() -> None:
    aggregation = Aggregation(
        product_id="product_1",
        product_slug="example",
        coverage=[
            CoverageItem(category="data_collection", status="missing"),
            CoverageItem(category="security", status="missing"),
        ],
        findings=[
            AggregatedFinding(
                category="data_collection",
                value="Email address",
                documents=["doc_1", "doc_2"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We collect your email address.",
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://example.com/security",
                        quote="We process account email for alerts.",
                    ),
                ],
            )
        ],
    )

    report = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )

    data_collection = next(topic for topic in report.topics if topic.topic == "data_collection")
    assert data_collection.coverage_status == "found"
    assert data_collection.status == "found"
    assert len(data_collection.findings) == 1
    assert data_collection.findings[0].document_ids == ["doc_1", "doc_2"]
    assert len(data_collection.findings[0].citations) == 2
    assert {citation.document_title for citation in data_collection.findings[0].citations} == {
        "Privacy Policy",
        "Security Policy",
    }


def test_build_product_topic_report_keeps_silent_topics_as_missing() -> None:
    aggregation = Aggregation(
        product_id="product_1",
        product_slug="example",
        coverage=[
            CoverageItem(category="data_sale", status="missing"),
        ],
        findings=[],
    )

    report = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )

    assert len(report.topics) == 1
    assert report.topics[0].topic == "data_sale"
    assert report.topics[0].coverage_status == "missing"
    assert report.topics[0].status == "missing"
    assert report.topics[0].topic_score is None
    assert report.topics[0].findings == []


def test_build_product_topic_report_attaches_conflicts() -> None:
    aggregation = Aggregation(
        product_id="product_1",
        product_slug="example",
        findings=[],
        conflicts=[
            FindingConflict(
                category="ai_training",
                description="Conflicting statements for ai_training",
                document_ids=["doc_1", "doc_2"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We do not use user data for model training.",
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://example.com/security",
                        quote="User data may be used to train models.",
                    ),
                ],
            )
        ],
    )

    report = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )

    assert len(report.topics) == 1
    ai_training = report.topics[0]
    assert ai_training.topic == "ai_training"
    assert ai_training.coverage_status == "ambiguous"
    assert ai_training.status == "ambiguous"
    assert ai_training.stance == "mixed"
    assert len(ai_training.conflicts) == 1
    assert ai_training.conflicts[0].document_ids == ["doc_1", "doc_2"]
    assert len(ai_training.conflicts[0].citations) == 2


def test_build_product_topic_report_is_deterministic() -> None:
    aggregation = Aggregation(
        product_id="product_1",
        product_slug="example",
        coverage=[CoverageItem(category="security", status="missing")],
        findings=[
            AggregatedFinding(
                category="security",
                value="SOC 2 controls",
                documents=["doc_2", "doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://example.com/security",
                        quote="We are SOC 2 compliant.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="Security controls are documented.",
                    ),
                ],
            )
        ],
    )
    report_one = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )
    report_two = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )
    assert report_one.model_dump(mode="json") == report_two.model_dump(mode="json")
