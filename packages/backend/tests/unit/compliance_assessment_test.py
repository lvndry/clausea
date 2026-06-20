"""Tests for product-level compliance assessment generation and rationale validation."""

from src.analyser import _normalize_compliance_regime_payload
from src.models.document import ComplianceBreakdown


class TestNormalizeComplianceRegimePayload:
    def test_coerces_string_lists(self) -> None:
        payload = _normalize_compliance_regime_payload(
            {
                "score": 7,
                "status": "Partially Compliant",
                "strengths": "Privacy Policy lists lawful bases",
                "gaps": "No retention periods",
                "assessment_notes": "Based on Privacy Policy only.",
            }
        )
        assert payload["strengths"] == ["Privacy Policy lists lawful bases"]
        assert payload["gaps"] == ["No retention periods"]
        assert payload["assessment_notes"] == "Based on Privacy Policy only."

    def test_maps_rationale_alias(self) -> None:
        payload = _normalize_compliance_regime_payload(
            {
                "score": 6,
                "status": "Partially Compliant",
                "rationale": "DPA covers SCC transfers.",
                "strengths": ["SCC mentioned"],
                "gaps": ["DPO missing"],
            }
        )
        assert payload["assessment_notes"] == "DPA covers SCC transfers."


class TestComplianceBreakdownRationale:
    def test_has_rationale_with_strengths_or_gaps(self) -> None:
        with_notes = ComplianceBreakdown(
            score=8,
            status="Compliant",
            strengths=["Lawful basis stated"],
            gaps=[],
        )
        assert with_notes.has_rationale() is True

        with_assessment_notes = ComplianceBreakdown(
            score=7,
            status="Partially Compliant",
            strengths=[],
            gaps=[],
            assessment_notes="Privacy Policy describes EU rights.",
        )
        assert with_assessment_notes.has_rationale() is True

    def test_missing_rationale(self) -> None:
        empty = ComplianceBreakdown(
            score=7,
            status="Partially Compliant",
            strengths=[],
            gaps=[],
        )
        assert empty.has_rationale() is False
