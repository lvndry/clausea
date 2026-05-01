"""Tests for _attach_deep_fields nested backfills and professional-grade deep analysis models."""

from src.analyser import _attach_deep_fields
from src.models.document import (
    ArticleComplianceCheck,
    CrossDocumentAnalysis,
    DocumentAnalysis,
    DocumentAnalysisScores,
    InformationGap,
    ProcurementDecision,
    RegulationArticleBreakdown,
    RiskRegisterItem,
    WorkforceDataAssessment,
)


def _minimal_scores() -> dict[str, DocumentAnalysisScores]:
    z = DocumentAnalysisScores(score=5, justification="x")
    return {
        "transparency": z,
        "data_collection_scope": z,
        "user_control": z,
        "third_party_sharing": z,
        "data_retention_score": z,
        "security_score": z,
    }


def test_attach_deep_fields_backfills_nested_applicability_and_missing_information() -> None:
    analysis = DocumentAnalysis(
        summary="S",
        scores=_minimal_scores(),
        applicability="EU users",
        coverage_gaps=["No retention table"],
    )
    data = {
        "document_risk_breakdown": {
            "overall_risk": 5,
            "risk_by_category": {},
            "top_concerns": [],
            "positive_protections": [],
            "missing_information": [],
        },
        "coverage_gaps": ["No retention table"],
    }
    _attach_deep_fields(analysis, data)

    assert analysis.document_risk_breakdown is not None
    assert analysis.document_risk_breakdown.applicability == "EU users"
    assert analysis.document_risk_breakdown.missing_information == ["No retention table"]


def test_attach_deep_fields_preserves_llm_nested_applicability() -> None:
    analysis = DocumentAnalysis(
        summary="S",
        scores=_minimal_scores(),
        applicability="Global",
        coverage_gaps=[],
    )
    data = {
        "document_risk_breakdown": {
            "overall_risk": 4,
            "applicability": "California only",
            "risk_by_category": {},
            "top_concerns": [],
            "positive_protections": [],
            "missing_information": [],
        },
        "coverage_gaps": [],
    }
    _attach_deep_fields(analysis, data)

    assert analysis.document_risk_breakdown is not None
    assert analysis.document_risk_breakdown.applicability == "California only"


# ── Professional-grade model tests ──────────────────────────────────────────


def test_procurement_decision_validates() -> None:
    pd = ProcurementDecision(
        decision="conditionally_approved",
        overall_risk_rating="high",
        conditions=["Sign DPA before processing EU personal data"],
        executive_brief="Vendor collects extensive telemetry; DPA required.",
        blocking_issues=[],
    )
    assert pd.decision == "conditionally_approved"
    assert len(pd.conditions) == 1


def test_risk_register_item_validates() -> None:
    item = RiskRegisterItem(
        id="R001",
        title="Broad AI training license",
        description="ToS grants perpetual license to use content for AI training.",
        source_document="terms_of_service",
        verbatim_quote="You grant us a perpetual, irrevocable license...",
        severity="critical",
        likelihood="high",
        regulatory_exposure=["GDPR Art. 22", "CCPA"],
        blocking=True,
        remediation_type="contractual_negotiation",
        recommended_action="Require opt-out clause for AI training in enterprise agreement.",
        suggested_owner="Legal",
    )
    assert item.blocking is True
    assert item.severity == "critical"


def test_regulation_article_breakdown_validates() -> None:
    breakdown = RegulationArticleBreakdown(
        regulation="GDPR",
        score=4,
        status="Partially Compliant",
        article_checks=[
            ArticleComplianceCheck(
                article="Art. 17",
                requirement="Right to erasure",
                status="missing",
                evidence=None,
                gap="No deletion mechanism described.",
            )
        ],
        critical_gaps=["No DPA available (Art. 28)"],
        strengths=["Breach notification mentioned"],
        detailed_analysis="Overall GDPR posture is weak.",
    )
    assert breakdown.score == 4
    assert breakdown.article_checks[0].status == "missing"


def test_workforce_data_assessment_not_applicable() -> None:
    wda = WorkforceDataAssessment(
        applicable=False,
        recommendation=None,
    )
    assert wda.applicable is False
    assert wda.risk_level is None


def test_cross_document_analysis_coerces_legacy_string_information_gaps() -> None:
    """Legacy cached data with list[str] gaps should be coerced to list[InformationGap]."""
    cda = CrossDocumentAnalysis(
        information_gaps=["No retention policy for biometric data"],  # type: ignore[arg-type]
    )
    assert len(cda.information_gaps) == 1
    assert isinstance(cda.information_gaps[0], InformationGap)
    assert cda.information_gaps[0].topic == "No retention policy for biometric data"
    assert cda.information_gaps[0].severity == "medium"


def test_cross_document_analysis_accepts_structured_information_gaps() -> None:
    cda = CrossDocumentAnalysis(
        information_gaps=[
            InformationGap(
                topic="Data breach notification timeline",
                severity="high",
                regulatory_consequence="GDPR Art. 33 requires 72h notification.",
                recommendation="Request written SLA from vendor.",
            )
        ],
    )
    assert cda.information_gaps[0].severity == "high"
    assert cda.information_gaps[0].regulatory_consequence is not None
