from src.models.document import CoverageItem, DocumentSummary, EvidenceSpan
from src.models.finding import AggregatedFinding, FindingConflict, HydratedRollup
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


def test_build_product_topic_report_keeps_all_non_empty_citations() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="data_sharing",
                value="Advertising partners",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="Cookies are small text files placed in device browsers.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="Please note that cookie-based opt-outs are not effective on mobile applications.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We share personal information with advertising partners for targeted advertising.",
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

    data_sharing = next(topic for topic in report.topics if topic.topic == "data_sharing")
    assert len(data_sharing.findings) == 1
    assert len(data_sharing.findings[0].citations) == 3


def test_build_product_topic_report_keeps_off_topic_quotes_without_pattern_filter() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="figma",
        findings=[
            AggregatedFinding(
                category="data_sharing",
                value="Advertising partners",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/live-events",
                        quote=(
                            "Live Events disputes will be resolved through binding "
                            "arbitration rather than in court."
                        ),
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/creator",
                        quote=(
                            "Under the Creator Agreement, you hereby assign all "
                            "intellectual property rights in your content to Figma."
                        ),
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We share personal information with advertising partners.",
                    ),
                ],
            )
        ],
    )

    report = build_product_topic_report(
        product_slug="figma",
        aggregation=aggregation,
        documents=_documents(),
    )

    data_sharing = next(topic for topic in report.topics if topic.topic == "data_sharing")
    assert len(data_sharing.findings) == 1
    assert len(data_sharing.findings[0].citations) == 3


def test_build_product_topic_report_drops_finding_when_only_empty_evidence() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="retention",
                value="Account data",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="",
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

    retention = next(topic for topic in report.topics if topic.topic == "retention")
    assert retention.findings == []
    assert retention.status == "not_disclosed"


def test_build_product_topic_report_includes_cross_document_citations() -> None:
    aggregation = HydratedRollup(
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
                        quote="We collect names and email addresses to create your account profile.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We collect your email address.",
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://example.com/security",
                        quote="We collect email addresses for account alerts and notifications.",
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://example.com/security",
                        quote="Account email addresses are processed to deliver security alerts.",
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
    assert data_collection.rationale_key == "topic.findings_summary"
    assert len(data_collection.findings) == 1
    assert data_collection.findings[0].document_ids == ["doc_1", "doc_2"]
    assert len(data_collection.findings[0].citations) == 4
    assert {citation.document_title for citation in data_collection.findings[0].citations} == {
        "Privacy Policy",
        "Security Policy",
    }


def test_build_product_topic_report_keeps_silent_topics_as_missing() -> None:
    aggregation = HydratedRollup(
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
    assert report.topics[0].rationale_key == "topic.not_disclosed"
    assert report.topics[0].findings == []


def test_build_product_topic_report_attaches_conflicts() -> None:
    aggregation = HydratedRollup(
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
    assert ai_training.rationale_key == "topic.conflicts_found"
    assert len(ai_training.conflicts) == 1
    assert ai_training.conflicts[0].document_ids == ["doc_1", "doc_2"]
    assert len(ai_training.conflicts[0].citations) == 2


def test_build_product_topic_report_keeps_all_linked_citations() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="retention",
                value="Account data: 30 days",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/terms",
                        quote="Repeat infringer accounts may be terminated without notice.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We retain account data for 30 days after account deletion.",
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

    retention = next(topic for topic in report.topics if topic.topic == "retention")
    assert len(retention.findings) == 1
    assert len(retention.findings[0].citations) == 2


def test_build_product_topic_report_filters_standard_danger_findings() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="dangers",
                value="Accounts may be disabled for repeated infringement",
                documents=["doc_1"],
                attributes=[{"materiality": "standard_industry"}],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/terms",
                        quote="We may terminate repeat infringers under our DMCA policy.",
                    )
                ],
            ),
            AggregatedFinding(
                category="dangers",
                value="We may sell your personal information to advertising partners",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We may sell your personal information to advertising partners.",
                    )
                ],
            ),
        ],
    )

    report = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )

    dangers = next(topic for topic in report.topics if topic.topic == "dangers")
    assert len(dangers.findings) == 1
    assert "sell your personal information" in dangers.findings[0].value.lower()


def test_build_product_topic_report_is_deterministic() -> None:
    aggregation = HydratedRollup(
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


def test_build_product_topic_report_conflict_for_existing_topic_sets_ambiguous_coverage() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="example",
        coverage=[CoverageItem(category="data_collection", status="found")],
        findings=[
            AggregatedFinding(
                category="data_collection",
                value="Email address",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We collect your email address.",
                    )
                ],
            )
        ],
        conflicts=[
            FindingConflict(
                category="data_collection",
                description="Conflicting statements for data_collection",
                document_ids=["doc_1", "doc_2"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://example.com/security",
                        quote="We do not collect user email.",
                    )
                ],
            )
        ],
    )

    report = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )
    topic = next(item for item in report.topics if item.topic == "data_collection")
    assert topic.coverage_status == "ambiguous"
    assert topic.status == "ambiguous"


def test_build_product_topic_report_filters_dangers_via_materiality_labels() -> None:
    aggregation = HydratedRollup(
        product_id="product_1",
        product_slug="example",
        findings=[
            AggregatedFinding(
                category="dangers",
                value="Binding arbitration / class action waiver",
                documents=["doc_1"],
                attributes=[{"materiality": "notable"}],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/terms",
                        quote="Disputes will be resolved by binding arbitration on an individual basis.",
                    )
                ],
            ),
            AggregatedFinding(
                category="dangers",
                value="Company may sell your personal information",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://example.com/privacy",
                        quote="We may sell your personal information to advertising partners.",
                    )
                ],
            ),
        ],
    )

    report = build_product_topic_report(
        product_slug="example",
        aggregation=aggregation,
        documents=_documents(),
    )

    dangers = next(topic for topic in report.topics if topic.topic == "dangers")
    assert len(dangers.findings) == 1
    assert "sell your personal information" in dangers.findings[0].value.lower()
    assert all("arbitration" not in finding.value.lower() for finding in dangers.findings)
