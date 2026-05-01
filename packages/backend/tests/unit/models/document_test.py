"""Tests for document models.

Tests Pydantic model validation, field validators, and factory methods
for core document-related models.
"""

from typing import Literal

import pytest
from pydantic import ValidationError

from src.models.document import (
    ComplianceBreakdown,
    CoverageItem,
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    DocumentExtraction,
    DocumentRiskBreakdown,
    DocumentSummary,
    EvidenceSpan,
    ExtractedDataItem,
    ExtractedThirdPartyRecipient,
    MetaSummary,
    MetaSummaryScore,
    MetaSummaryScores,
    PrivacySignals,
    ProductOverview,
    coerce_doc_type_from_classifier,
)

# ── DocumentAnalysis validators ─────────────────────────────────────


class TestDocumentAnalysisCleanSummary:
    """Tests for the clean_summary field validator."""

    def test_plain_string(self) -> None:
        analysis = DocumentAnalysis(
            summary="This is a summary.",
            scores={"transparency": DocumentAnalysisScores(score=8, justification="good")},
        )
        assert analysis.summary == "This is a summary."

    def test_none_becomes_empty(self) -> None:
        analysis = DocumentAnalysis(
            summary=None,  # type: ignore[arg-type]
            scores={"transparency": DocumentAnalysisScores(score=5, justification="ok")},
        )
        assert analysis.summary == ""

    def test_json_encoded_summary_extracted(self) -> None:
        import json

        json_str = json.dumps({"summary": "Extracted summary", "extra": "data"})
        analysis = DocumentAnalysis(
            summary=json_str,
            scores={"transparency": DocumentAnalysisScores(score=5, justification="ok")},
        )
        assert analysis.summary == "Extracted summary"

    def test_json_without_summary_key(self) -> None:
        import json

        json_str = json.dumps({"other_key": "value"})
        analysis = DocumentAnalysis(
            summary=json_str,
            scores={"transparency": DocumentAnalysisScores(score=5, justification="ok")},
        )
        # Should return the raw JSON string since no "summary" key
        assert analysis.summary == json_str

    def test_whitespace_stripped(self) -> None:
        analysis = DocumentAnalysis(
            summary="  padded  ",
            scores={"transparency": DocumentAnalysisScores(score=5, justification="ok")},
        )
        assert analysis.summary == "padded"


class TestDocumentAnalysisCleanComplianceStatus:
    """Tests for the clean_compliance_status field validator."""

    def test_valid_compliance_status(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            compliance_status={"GDPR": 8, "CCPA": 7},
        )
        assert analysis.compliance_status == {"GDPR": 8, "CCPA": 7}

    def test_none_compliance(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            compliance_status=None,
        )
        assert analysis.compliance_status is None

    def test_empty_dict_becomes_none(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            compliance_status={},
        )
        assert analysis.compliance_status is None

    def test_non_dict_becomes_none(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            compliance_status="invalid",  # type: ignore[arg-type]
        )
        assert analysis.compliance_status is None

    def test_mixed_types_cleaned(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            compliance_status={"GDPR": "8", "CCPA": 7, "bad": "not_a_number", "none_val": None},  # type: ignore[dict-item]
        )
        assert analysis.compliance_status == {"GDPR": 8, "CCPA": 7}


class TestDocumentAnalysisApplicabilityAlias:
    """Legacy JSON used `scope`; LLM output and new code use `applicability`."""

    def test_legacy_scope_key_in_model_validate(self) -> None:
        analysis = DocumentAnalysis.model_validate(
            {
                "summary": "S",
                "scores": {"transparency": {"score": 5, "justification": "x"}},
                "scope": "EU-specific",
            }
        )
        assert analysis.applicability == "EU-specific"

    def test_applicability_key(self) -> None:
        analysis = DocumentAnalysis.model_validate(
            {
                "summary": "S",
                "scores": {"transparency": {"score": 5, "justification": "x"}},
                "applicability": "Global",
            }
        )
        assert analysis.applicability == "Global"

    def test_document_risk_breakdown_scope_alias(self) -> None:
        br = DocumentRiskBreakdown.model_validate(
            {
                "overall_risk": 5,
                "scope": "US-only",
            }
        )
        assert br.applicability == "US-only"


# ── DocumentAnalysis risk_score bounds ──────────────────────────────


class TestDocumentAnalysisRiskScore:
    def test_default_risk_score(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
        )
        assert analysis.risk_score == 5

    def test_risk_score_min_valid(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            risk_score=0,
        )
        assert analysis.risk_score == 0

    def test_risk_score_max_valid(self) -> None:
        analysis = DocumentAnalysis(
            summary="Test",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            risk_score=10,
        )
        assert analysis.risk_score == 10

    def test_risk_score_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DocumentAnalysis(
                summary="Test",
                scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
                risk_score=-1,
            )

    def test_risk_score_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DocumentAnalysis(
                summary="Test",
                scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
                risk_score=11,
            )


# ── Verdict literals ────────────────────────────────────────────────


VerdictLiteral = Literal[
    "very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"
]


class TestVerdict:
    def test_valid_verdicts(self) -> None:
        verdicts: list[VerdictLiteral] = [
            "very_user_friendly",
            "user_friendly",
            "moderate",
            "pervasive",
            "very_pervasive",
        ]
        for verdict in verdicts:
            analysis = DocumentAnalysis(
                summary="Test",
                scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
                verdict=verdict,
            )
            assert analysis.verdict == verdict

    def test_invalid_verdict_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DocumentAnalysis(
                summary="Test",
                scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
                verdict="invalid",  # type: ignore[arg-type]
            )


# ── PrivacySignals ──────────────────────────────────────────────────


class TestPrivacySignals:
    def test_default_values(self) -> None:
        signals = PrivacySignals()
        assert signals.sells_data == "unclear"
        assert signals.cross_site_tracking == "unclear"
        assert signals.account_deletion == "not_specified"
        assert signals.consent_model == "not_specified"
        assert signals.data_retention_summary is None

    def test_custom_values(self) -> None:
        signals = PrivacySignals(
            sells_data="no",
            cross_site_tracking="yes",
            account_deletion="self_service",
            consent_model="opt_in",
            data_retention_summary="30 days",
        )
        assert signals.sells_data == "no"
        assert signals.data_retention_summary == "30 days"

    def test_invalid_sells_data(self) -> None:
        with pytest.raises(ValidationError):
            PrivacySignals(sells_data="maybe")  # type: ignore[arg-type]


# ── EvidenceSpan ────────────────────────────────────────────────────


class TestEvidenceSpan:
    def test_minimal(self) -> None:
        span = EvidenceSpan(document_id="doc1", url="https://example.com", quote="Some text")
        assert span.document_id == "doc1"
        assert span.start_char is None
        assert span.content_hash is None

    def test_full(self) -> None:
        span = EvidenceSpan(
            document_id="doc1",
            url="https://example.com",
            quote="Evidence text",
            content_hash="abc123",
            start_char=100,
            end_char=200,
            section_title="Section 3",
        )
        assert span.start_char == 100
        assert span.end_char == 200


# ── ExtractedThirdPartyRecipient ────────────────────────────────────


class TestExtractedThirdPartyRecipient:
    def test_default_risk_level(self) -> None:
        recipient = ExtractedThirdPartyRecipient(recipient="Google Analytics")
        assert recipient.risk_level == "medium"

    def test_invalid_risk_level(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedThirdPartyRecipient(
                recipient="Test",
                risk_level="extreme",  # type: ignore[arg-type]
            )


# ── CoverageItem ────────────────────────────────────────────────────


class TestCoverageItem:
    def test_valid_coverage(self) -> None:
        item = CoverageItem(category="data_collection", status="found")
        assert item.category == "data_collection"

    def test_invalid_category(self) -> None:
        with pytest.raises(ValidationError):
            CoverageItem(category="invalid_category", status="found")  # type: ignore[arg-type]

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            CoverageItem(category="data_collection", status="invalid")  # type: ignore[arg-type]


# ── DocumentExtraction ──────────────────────────────────────────────


class TestDocumentExtraction:
    def test_defaults(self) -> None:
        extraction = DocumentExtraction(source_content_hash="hash123")
        assert extraction.version == "v4"
        assert extraction.data_collected == []
        assert extraction.privacy_signals is None

    def test_with_data(self) -> None:
        extraction = DocumentExtraction(
            source_content_hash="hash123",
            data_collected=[ExtractedDataItem(data_type="Email address")],
            privacy_signals=PrivacySignals(sells_data="no"),
        )
        assert len(extraction.data_collected) == 1
        assert extraction.privacy_signals is not None
        assert extraction.privacy_signals.sells_data == "no"


# ── ComplianceBreakdown ─────────────────────────────────────────────


class TestComplianceBreakdown:
    def test_valid(self) -> None:
        breakdown = ComplianceBreakdown(
            score=8,
            status="Compliant",
            strengths=["Good encryption"],
            gaps=["Missing DPO info"],
        )
        assert breakdown.score == 8

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ComplianceBreakdown(score=11, status="Compliant", strengths=[], gaps=[])


# ── Document model ──────────────────────────────────────────────────


class TestDocument:
    def test_minimal_document(self) -> None:
        doc = Document(
            url="https://example.com/privacy",
            product_id="prod1",
            doc_type="privacy_policy",
            markdown="# Privacy Policy",
            text="Privacy Policy content",
        )
        assert doc.id  # auto-generated
        assert doc.url == "https://example.com/privacy"
        assert doc.doc_type == "privacy_policy"
        assert doc.analysis is None
        assert doc.regions == []

    def test_invalid_doc_type(self) -> None:
        with pytest.raises(ValidationError):
            Document(
                url="https://example.com",
                product_id="prod1",
                doc_type="invalid_type",  # type: ignore[arg-type]
                markdown="md",
                text="text",
            )

    def test_unclassified_is_not_a_valid_doc_type(self) -> None:
        with pytest.raises(ValidationError):
            Document(
                url="https://example.com",
                product_id="p1",
                doc_type="unclassified",  # type: ignore[arg-type]
                markdown="",
                text="",
            )

    def test_valid_regions(self) -> None:
        doc = Document(
            url="https://example.com",
            product_id="prod1",
            doc_type="privacy_policy",
            markdown="md",
            text="text",
            regions=["US", "EU"],
        )
        assert doc.regions == ["US", "EU"]


# ── DocumentSummary.from_document ───────────────────────────────────


class TestDocumentSummaryFromDocument:
    def test_from_document_without_analysis(self) -> None:
        doc = Document(
            url="https://example.com/privacy",
            product_id="prod1",
            doc_type="privacy_policy",
            markdown="md",
            text="text",
            title="Privacy Policy",
        )
        summary = DocumentSummary.from_document(doc)
        assert summary.title == "Privacy Policy"
        assert summary.doc_type == "privacy_policy"
        assert summary.summary is None
        assert summary.verdict is None
        assert summary.risk_score is None

    def test_from_document_with_analysis(self) -> None:
        analysis = DocumentAnalysis(
            summary="This policy is moderate.",
            scores={"t": DocumentAnalysisScores(score=5, justification="ok")},
            risk_score=6,
            verdict="moderate",
            keypoints=["Collects email", "Shares with partners"],
        )
        doc = Document(
            url="https://example.com/privacy",
            product_id="prod1",
            doc_type="privacy_policy",
            markdown="md",
            text="text",
            analysis=analysis,
        )
        summary = DocumentSummary.from_document(doc)
        assert summary.summary == "This policy is moderate."
        assert summary.verdict == "moderate"
        assert summary.risk_score == 6
        assert summary.keypoints == ["Collects email", "Shares with partners"]


# ── MetaSummary compliance_status validator ─────────────────────────


class TestMetaSummaryComplianceStatus:
    def _make_scores(self) -> MetaSummaryScores:
        return MetaSummaryScores(
            transparency=MetaSummaryScore(score=5, justification="ok"),
            data_collection_scope=MetaSummaryScore(score=5, justification="ok"),
            user_control=MetaSummaryScore(score=5, justification="ok"),
            third_party_sharing=MetaSummaryScore(score=5, justification="ok"),
        )

    def test_valid_compliance(self) -> None:
        ms = MetaSummary(
            summary="Test",
            scores=self._make_scores(),
            risk_score=5,
            verdict="moderate",
            keypoints=["a"],
            compliance_status={"GDPR": 8},
        )
        assert ms.compliance_status == {"GDPR": 8}

    def test_string_values_coerced(self) -> None:
        ms = MetaSummary(
            summary="Test",
            scores=self._make_scores(),
            risk_score=5,
            verdict="moderate",
            keypoints=["a"],
            compliance_status={"GDPR": "9"},  # type: ignore[dict-item]
        )
        assert ms.compliance_status == {"GDPR": 9}

    def test_none_values_filtered(self) -> None:
        ms = MetaSummary(
            summary="Test",
            scores=self._make_scores(),
            risk_score=5,
            verdict="moderate",
            keypoints=["a"],
            compliance_status={"GDPR": None, "CCPA": 7},  # type: ignore[dict-item]
        )
        assert ms.compliance_status == {"CCPA": 7}


# ── ProductOverview compliance_status validator ─────────────────────


class TestProductOverviewComplianceStatus:
    def test_product_overview_compliance_cleaned(self) -> None:
        overview = ProductOverview(
            product_name="Test",
            product_slug="test",
            verdict="moderate",
            risk_score=5,
            one_line_summary="Test product",
            compliance_status={"GDPR": "8", "bad": "no"},  # type: ignore[dict-item]
        )
        assert overview.compliance_status == {"GDPR": 8}


# ── coerce_doc_type_from_classifier ─────────────────────────────────


class TestCoerceDocTypeFromClassifier:
    def test_known_classifier_labels_preserved(self) -> None:
        assert coerce_doc_type_from_classifier("security_policy") == "security_policy"
        assert coerce_doc_type_from_classifier("privacy_policy") == "privacy_policy"

    def test_unknown_label_becomes_other(self) -> None:
        assert coerce_doc_type_from_classifier("hipaa_policy") == "other"
        assert coerce_doc_type_from_classifier("not_a_real_type") == "other"

    def test_empty_or_none_defaults_to_other(self) -> None:
        assert coerce_doc_type_from_classifier(None) == "other"
        assert coerce_doc_type_from_classifier("") == "other"

    def test_whitespace_stripped(self) -> None:
        assert coerce_doc_type_from_classifier("  privacy_policy  ") == "privacy_policy"
