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
    assert rows["data_sale"]["rationale_key"] == "topic.not_disclosed"


def test_evaluate_topic_stances_detects_yes_no_signals() -> None:
    findings = [
        AggregatedFinding(
            category="data_sale",
            value="sells_data: yes",
            documents=["doc_1"],
            evidence=[
                EvidenceSpan(document_id="doc_1", url="https://x", quote="We may sell data."),
                EvidenceSpan(
                    document_id="doc_1",
                    url="https://x",
                    quote="We may sell personal information to advertising partners.",
                ),
                EvidenceSpan(
                    document_id="doc_1",
                    url="https://x",
                    quote="Sale of personal data may occur as described in this policy.",
                ),
            ],
        ),
        AggregatedFinding(
            category="security",
            value="Encryption at rest",
            documents=["doc_1", "doc_2"],
            evidence=[
                EvidenceSpan(
                    document_id="doc_1", url="https://x", quote="We encrypt data at rest."
                ),
                EvidenceSpan(
                    document_id="doc_2",
                    url="https://x",
                    quote="All stored user data is encrypted at rest using industry standards.",
                ),
                EvidenceSpan(
                    document_id="doc_2",
                    url="https://x",
                    quote="We use encryption to protect data at rest across our systems.",
                ),
            ],
        ),
    ]
    rows = evaluate_topic_stances(findings=findings, conflicts=[], coverage=None)
    assert rows["data_sale"]["status"] == "found"
    assert rows["data_sale"]["stance"] == "harmful"
    assert rows["data_sale"]["rationale_key"] == "topic.findings_summary"
    assert rows["data_sale"]["rationale_params"]["finding_count"] == 1
    assert rows["data_sale"]["rationale_params"]["document_count"] == 1
    assert rows["security"]["stance"] == "fair"


def test_evaluate_topic_stances_ai_training_uses_structured_attributes() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="ai_training",
                value="Model improvement language without explicit yes/no token.",
                documents=["doc_1"],
                attributes=[{"usage_type": "training_on_user_data", "opt_out_available": "yes"}],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We use customer prompts to improve our models.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="Customer prompts may be used to improve and train our AI models.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We may use user content to train and improve machine learning models.",
                    ),
                ],
            )
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["ai_training"]["stance"] == "harmful"


def test_evaluate_topic_stances_ai_training_parses_flexible_signal_format() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="ai_training",
                value='{"AI_TRAINING_ON_USER_DATA":"NO"}',
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We do not use user data for model training.",
                    )
                ],
            )
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["ai_training"]["stance"] == "fair"


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
    assert rows["ai_training"]["stance"] == "conflicting"
    assert rows["ai_training"]["rationale_key"] == "topic.conflicts_found"
    assert rows["ai_training"]["rationale_params"]["conflict_count"] == 1
    assert rows["ai_training"]["rationale_params"]["document_count"] == 2


def test_evaluate_topic_stances_counts_unique_documents_across_findings() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="data_collection",
                value="Email",
                documents=["doc_1", "doc_2"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We collect your email address for account communication.",
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://x",
                        quote="Email addresses are collected to deliver account notifications.",
                    ),
                ],
            ),
            AggregatedFinding(
                category="data_collection",
                value="Name",
                documents=["doc_1", "doc_3"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_3",
                        url="https://x",
                        quote="We collect your name to personalize your profile.",
                    )
                ],
            ),
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["data_collection"]["rationale_key"] == "topic.findings_summary"
    # doc_1 appears in both findings but must be counted once.
    assert rows["data_collection"]["rationale_params"]["document_count"] == 3


def test_compose_product_risk_excludes_not_disclosed_topics() -> None:
    score = compose_product_risk_from_topics(
        {
            "data_collection": {"status": "found", "stance": "harmful"},
            "data_sharing": {"status": "not_disclosed", "stance": "harmful"},
            "security": {"status": "found", "stance": "fair"},
        }
    )
    # Must not be dragged toward 10 by undisclosed data_sharing.
    assert 3 <= score <= 6


def test_compose_product_risk_prioritizes_ai_training_signal() -> None:
    score = compose_product_risk_from_topics(
        {
            "ai_training": {"status": "found", "stance": "harmful"},
            "cookies_tracking": {"status": "found", "stance": "fair"},
        }
    )
    # AI training must carry clearly stronger influence than tracking-only noise.
    assert score >= 6


def test_evaluate_topic_stances_downgrades_standard_dangers() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="dangers",
                value="Accounts may be disabled or terminated for repeated infringement",
                documents=["doc_1"],
                attributes=[{"materiality": "standard_industry"}],
                evidence=[],
            ),
            AggregatedFinding(
                category="dangers",
                value="We may sell your personal information to partners",
                documents=["doc_1"],
                attributes=[{"materiality": "material_risk"}],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We may sell your personal information to advertising partners.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We may sell personal information to third-party partners.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="Sale of personal information may occur as described here.",
                    ),
                ],
            ),
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["dangers"]["stance"] == "harmful"


def test_evaluate_topic_stances_omits_boilerplate_from_dangers_score() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="dangers",
                value="Agreement is not assignable without prior written consent",
                documents=["doc_1"],
                attributes=[{"materiality": "standard_industry"}],
                evidence=[],
            ),
            AggregatedFinding(
                category="dangers",
                value="Binding arbitration with class action and jury trial waivers",
                documents=["doc_1"],
                attributes=[{"materiality": "notable"}],
                evidence=[],
            ),
        ],
        conflicts=[],
        coverage=None,
    )
    # Both findings are excluded from dangers scoring — topic falls back to generic,
    # then the thin-evidence cap reduces it to fair.
    assert rows["dangers"]["stance"] == "fair"


def test_evaluate_topic_stances_dispute_resolution_moderate_for_arbitration() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="dispute_resolution",
                value="Binding arbitration with class action waiver",
                documents=["doc_1"],
                attributes=[{"materiality": "notable"}],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="Disputes will be resolved through binding arbitration on an individual basis.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="You agree to resolve disputes individually through binding arbitration.",
                    ),
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="Class action and jury trial rights are waived in favor of arbitration.",
                    ),
                ],
            )
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["dispute_resolution"]["stance"] == "concerning"


def test_evaluate_topic_stances_downgrades_thin_evidence_to_low_risk() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="data_sale",
                value="sells_data: yes",
                documents=["doc_1"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1",
                        url="https://x",
                        quote="We may sell personal information to advertising partners.",
                    )
                ],
            )
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["data_sale"]["stance"] == "fair"
    assert rows["data_sale"]["rationale_key"] == "topic.thin_evidence"


def test_evaluate_topic_stances_marks_protective_security_as_positive_practice() -> None:
    rows = evaluate_topic_stances(
        findings=[
            AggregatedFinding(
                category="security",
                value="Encryption at rest",
                documents=["doc_1", "doc_2"],
                evidence=[
                    EvidenceSpan(
                        document_id="doc_1", url="https://x", quote="We encrypt data at rest."
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://x",
                        quote="Stored user data is encrypted at rest using industry standards.",
                    ),
                    EvidenceSpan(
                        document_id="doc_2",
                        url="https://x",
                        quote="We use encryption to protect data at rest across our systems.",
                    ),
                ],
            )
        ],
        conflicts=[],
        coverage=None,
    )
    assert rows["security"]["stance"] == "fair"
    assert rows["security"]["rationale_key"] == "topic.positive_practice"
