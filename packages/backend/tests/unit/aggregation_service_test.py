import json
from pathlib import Path
from typing import cast

from src.models.document import (
    DocumentExtraction,
    ExtractedChildrenPolicy,
    ExtractedCookieTracker,
    ExtractedDataItem,
    ExtractedRetentionRule,
    ExtractedTextItem,
    PrivacySignals,
)
from src.models.finding import Finding
from src.repositories.aggregation_repository import AggregationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.finding_repository import FindingRepository
from src.services.aggregation_service import AggregationService


class _DummyRepo:
    async def find_by_product_id_full(self, *_args, **_kwargs):
        return []


def _service() -> AggregationService:
    return AggregationService(
        cast(DocumentRepository, _DummyRepo()),
        cast(FindingRepository, _DummyRepo()),
        cast(AggregationRepository, _DummyRepo()),
    )


def test_aggregate_findings_dedupes_by_category_and_value() -> None:
    service = _service()
    findings = [
        Finding(
            product_id="p1",
            document_id="d1",
            category="data_collection",
            value="Email address",
            normalized_value="email address",
        ),
        Finding(
            product_id="p1",
            document_id="d2",
            category="data_collection",
            value="Email address",
            normalized_value="email address",
        ),
    ]

    aggregated = service._aggregate_findings(findings)
    assert len(aggregated) == 1
    assert aggregated[0].category == "data_collection"
    assert sorted(aggregated[0].documents) == ["d1", "d2"]


def test_build_coverage_marks_missing_when_not_found() -> None:
    service = _service()
    findings = [
        Finding(
            product_id="p1",
            document_id="d1",
            category="user_rights",
            value="Access your data via settings",
        )
    ]

    coverage = service._build_coverage(findings, analyzed_docs=1)
    status_by_category = {item.category: item.status for item in coverage}
    assert status_by_category["user_rights"] == "found"
    assert status_by_category["data_collection"] == "missing"


def test_aggregation_fixture_shape() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures/aggregation_fixture.json"
    payload = json.loads(fixture_path.read_text())
    assert "coverage" in payload
    assert "findings" in payload
    assert isinstance(payload["findings"], list)


# ── _findings_from_retention_rules ──────────────────────────────────


class TestFindingsFromRetentionRules:
    def test_produces_retention_category(self) -> None:
        service = _service()
        rules = [ExtractedRetentionRule(data_scope="Account data", duration="30 days")]
        findings = service._findings_from_retention_rules(
            product_id="p1", document_id="d1", items=rules
        )
        assert len(findings) == 1
        assert findings[0].category == "retention"
        assert "Account data" in findings[0].value
        assert "30 days" in findings[0].value
        assert findings[0].attributes["duration"] == "30 days"

    def test_skips_empty_scope(self) -> None:
        service = _service()
        rules = [ExtractedRetentionRule(data_scope="", duration="30 days")]
        findings = service._findings_from_retention_rules(
            product_id="p1", document_id="d1", items=rules
        )
        assert len(findings) == 0

    def test_scope_only_when_no_duration(self) -> None:
        service = _service()
        rules = [ExtractedRetentionRule(data_scope="Logs", duration="")]
        findings = service._findings_from_retention_rules(
            product_id="p1", document_id="d1", items=rules
        )
        assert len(findings) == 1
        assert findings[0].value == "Logs"


# ── _findings_from_cookie_trackers ──────────────────────────────────


class TestFindingsFromCookieTrackers:
    def test_produces_cookies_tracking_category(self) -> None:
        service = _service()
        cookies = [
            ExtractedCookieTracker(
                name_or_type="Google Analytics",
                category="analytics",
                third_party=True,
            )
        ]
        findings = service._findings_from_cookie_trackers(
            product_id="p1", document_id="d1", items=cookies
        )
        assert len(findings) == 1
        assert findings[0].category == "cookies_tracking"
        assert findings[0].value == "Google Analytics"
        assert findings[0].attributes["third_party"] is True

    def test_skips_empty_name(self) -> None:
        service = _service()
        cookies = [ExtractedCookieTracker(name_or_type="")]
        findings = service._findings_from_cookie_trackers(
            product_id="p1", document_id="d1", items=cookies
        )
        assert len(findings) == 0


# ── _findings_from_children_policy ──────────────────────────────────


class TestFindingsFromChildrenPolicy:
    def test_produces_children_category(self) -> None:
        service = _service()
        policy = ExtractedChildrenPolicy(
            minimum_age=13,
            parental_consent_required=True,
            special_protections="Limited data for under-16s",
        )
        findings = service._findings_from_children_policy(
            product_id="p1", document_id="d1", children_policy=policy
        )
        assert len(findings) == 1
        assert findings[0].category == "children"
        assert "13" in findings[0].value
        assert findings[0].attributes["minimum_age"] == 13
        assert findings[0].attributes["parental_consent_required"] is True

    def test_returns_empty_for_none(self) -> None:
        service = _service()
        findings = service._findings_from_children_policy(
            product_id="p1", document_id="d1", children_policy=None
        )
        assert len(findings) == 0

    def test_returns_empty_when_all_defaults(self) -> None:
        service = _service()
        policy = ExtractedChildrenPolicy()
        findings = service._findings_from_children_policy(
            product_id="p1", document_id="d1", children_policy=policy
        )
        assert len(findings) == 0


# ── _extraction_to_findings full integration ────────────────────────


class TestExtractionToFindings:
    def test_retention_and_cookies_not_dropped(self) -> None:
        """Regression: retention_policies and cookies_and_trackers must produce findings."""
        service = _service()
        extraction = DocumentExtraction(
            source_content_hash="abc",
            retention_policies=[
                ExtractedRetentionRule(data_scope="User data", duration="1 year"),
            ],
            cookies_and_trackers=[
                ExtractedCookieTracker(
                    name_or_type="Facebook Pixel", category="advertising", third_party=True
                ),
            ],
        )
        findings = service._extraction_to_findings(
            product_id="p1", document_id="d1", extraction=extraction
        )
        categories = {f.category for f in findings}
        assert "retention" in categories
        assert "cookies_tracking" in categories

    def test_children_policy_produces_finding(self) -> None:
        """Regression: children_policy must produce a finding."""
        service = _service()
        extraction = DocumentExtraction(
            source_content_hash="abc",
            children_policy=ExtractedChildrenPolicy(minimum_age=13, parental_consent_required=True),
        )
        findings = service._extraction_to_findings(
            product_id="p1", document_id="d1", extraction=extraction
        )
        children_findings = [f for f in findings if f.category == "children"]
        assert len(children_findings) >= 1

    def test_all_clusters_produce_findings(self) -> None:
        """Smoke test: a fully populated extraction produces findings for every cluster."""
        service = _service()
        from src.models.document import (
            ExtractedAIUsage,
            ExtractedContentOwnership,
            ExtractedCorporateFamilySharing,
            ExtractedDataPurposeLink,
            ExtractedDisputeResolution,
            ExtractedGovernmentAccess,
            ExtractedInternationalTransfer,
            ExtractedLiability,
            ExtractedScopeExpansion,
            ExtractedThirdPartyRecipient,
            ExtractedUserRight,
        )

        extraction = DocumentExtraction(
            source_content_hash="abc",
            data_collected=[ExtractedDataItem(data_type="Email")],
            data_purposes=[ExtractedDataPurposeLink(data_type="Email", purposes=["Marketing"])],
            retention_policies=[ExtractedRetentionRule(data_scope="All", duration="1y")],
            security_measures=[ExtractedTextItem(value="TLS")],
            cookies_and_trackers=[ExtractedCookieTracker(name_or_type="GA")],
            third_party_details=[ExtractedThirdPartyRecipient(recipient="Ads Inc")],
            international_transfers=[ExtractedInternationalTransfer(destination="US")],
            government_access=[
                ExtractedGovernmentAccess(authority_type="FBI", conditions="Subpoena")
            ],
            corporate_family_sharing=[ExtractedCorporateFamilySharing(entities=["SubCo"])],
            user_rights=[ExtractedUserRight(right_type="Access", description="Access your data")],
            consent_mechanisms=[ExtractedTextItem(value="Opt-out link")],
            account_lifecycle=[ExtractedTextItem(value="Data deleted on closure")],
            ai_usage=[
                ExtractedAIUsage(usage_type="training_on_user_data", description="Trains models")
            ],
            children_policy=ExtractedChildrenPolicy(minimum_age=13),
            liability=[
                ExtractedLiability(scope="Service", limitation_type="cap", description="$100 cap")
            ],
            dispute_resolution=[
                ExtractedDisputeResolution(mechanism="arbitration", description="Binding arb")
            ],
            content_ownership=[
                ExtractedContentOwnership(
                    ownership_type="license_to_company",
                    scope="Worldwide",
                    description="Perpetual license",
                )
            ],
            scope_expansion=[
                ExtractedScopeExpansion(
                    scope_type="cross_entity", description="Binds to all subsidiaries"
                )
            ],
            indemnification=[ExtractedTextItem(value="User indemnifies company")],
            termination_consequences=[ExtractedTextItem(value="Content deleted in 30 days")],
            dangers=[ExtractedTextItem(value="No cap on liability")],
            benefits=[ExtractedTextItem(value="30-day opt-out window")],
            recommended_actions=[ExtractedTextItem(value="Send opt-out notice")],
            privacy_signals=PrivacySignals(sells_data="no"),
        )
        findings = service._extraction_to_findings(
            product_id="p1", document_id="d1", extraction=extraction
        )
        categories = {f.category for f in findings}
        expected = {
            "data_collection",
            "data_purposes",
            "retention",
            "security",
            "cookies_tracking",
            "data_sharing",
            "international_transfers",
            "government_access",
            "corporate_family_sharing",
            "user_rights",
            "consent_mechanisms",
            "account_lifecycle",
            "ai_training",
            "children",
            "liability",
            "dispute_resolution",
            "content_ownership",
            "scope_expansion",
            "indemnification",
            "termination_consequences",
            "dangers",
            "benefits",
            "recommended_actions",
            "data_sale",
        }
        assert expected.issubset(categories), f"Missing: {expected - categories}"


# ── _build_coverage no false "missing" ──────────────────────────────


class TestBuildCoverageNoLegacyGaps:
    def test_no_advertising_or_profiling_ai_in_coverage(self) -> None:
        """Regression: removed legacy categories should not appear in coverage."""
        service = _service()
        coverage = service._build_coverage([], analyzed_docs=1)
        coverage_categories = {item.category for item in coverage}
        assert "advertising" not in coverage_categories
        assert "profiling_ai" not in coverage_categories
