"""Tests for RegionDetector analyzer.

Tests URL-based, metadata-based, and content-based region detection,
plus the region name → code mapping.
"""

import pytest

from src.analyzers.region_detector import RegionDetector


@pytest.fixture
def detector() -> RegionDetector:
    return RegionDetector()


# ── _map_region_name_to_code ────────────────────────────────────────


class TestMapRegionNameToCode:
    """Tests for region name to Region literal mapping."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("US", "US"),
            ("usa", "US"),
            ("united states", "US"),
            ("america", "US"),
            ("california", "US"),
            ("EU", "EU"),
            ("european union", "EU"),
            ("europe", "EU"),
            ("germany", "EU"),
            ("france", "EU"),
            ("UK", "UK"),
            ("united kingdom", "UK"),
            ("england", "UK"),
            ("Canada", "Canada"),
            ("Australia", "Australia"),
            ("Brazil", "Brazil"),
            ("South Korea", "South Korea"),
            ("Asia", "Asia"),
            ("japan", "Asia"),
            ("china", "Asia"),
            ("india", "Asia"),
            ("global", "global"),
            ("mexico", "Other"),
            ("argentina", "Other"),
        ],
    )
    def test_known_region(self, detector: RegionDetector, name: str, expected: str) -> None:
        assert detector._map_region_name_to_code(name) == expected

    def test_unknown_region_returns_none(self, detector: RegionDetector) -> None:
        assert detector._map_region_name_to_code("mars") is None

    def test_case_insensitive(self, detector: RegionDetector) -> None:
        assert detector._map_region_name_to_code("UNITED STATES") == "US"
        assert detector._map_region_name_to_code("European Union") == "EU"


# ── URL-based region detection ──────────────────────────────────────


class TestURLRegionDetection:
    """Tests for region detection from URL patterns."""

    @pytest.mark.asyncio
    async def test_eu_url(self, detector: RegionDetector) -> None:
        result = await detector.detect_regions(
            text="Some legal text", metadata={}, url="https://example.com/eu/privacy"
        )
        assert "EU" in result["regions"]

    @pytest.mark.asyncio
    async def test_us_url(self, detector: RegionDetector) -> None:
        result = await detector.detect_regions(
            text="Some legal text", metadata={}, url="https://example.com/us/terms"
        )
        assert "US" in result["regions"]

    @pytest.mark.asyncio
    async def test_uk_url(self, detector: RegionDetector) -> None:
        result = await detector.detect_regions(
            text="Some legal text", metadata={}, url="https://example.com/uk/privacy"
        )
        assert "UK" in result["regions"]

    @pytest.mark.asyncio
    async def test_canada_url(self, detector: RegionDetector) -> None:
        result = await detector.detect_regions(
            text="Some legal text", metadata={}, url="https://example.com/ca/privacy"
        )
        assert "Canada" in result["regions"]

    @pytest.mark.asyncio
    async def test_australia_url(self, detector: RegionDetector) -> None:
        result = await detector.detect_regions(
            text="Some legal text", metadata={}, url="https://example.com/au/privacy"
        )
        assert "Australia" in result["regions"]


# ── Metadata-based region detection ─────────────────────────────────


class TestMetadataRegionDetection:
    @pytest.mark.asyncio
    async def test_gdpr_in_metadata(self, detector: RegionDetector) -> None:
        result = await detector.detect_regions(
            text="Some text",
            metadata={"compliance": "GDPR"},
            url="https://example.com/privacy",
        )
        assert "EU" in result["regions"]


# ── Content-based region detection ──────────────────────────────────


class TestContentRegionDetection:
    @pytest.mark.asyncio
    async def test_gdpr_in_content(self, detector: RegionDetector) -> None:
        text = "This policy complies with GDPR requirements for data protection."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        assert "EU" in result["regions"]

    @pytest.mark.asyncio
    async def test_ccpa_in_content(self, detector: RegionDetector) -> None:
        text = "Under CCPA, California residents have the right to know what data we collect."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        assert "US" in result["regions"]

    @pytest.mark.asyncio
    async def test_pipeda_in_content(self, detector: RegionDetector) -> None:
        text = "We comply with PIPEDA for the protection of personal information in Canada."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        assert "Canada" in result["regions"]

    @pytest.mark.asyncio
    async def test_lgpd_in_content(self, detector: RegionDetector) -> None:
        text = "In accordance with LGPD, we process personal data of Brazilian users."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        assert "Brazil" in result["regions"]

    @pytest.mark.asyncio
    async def test_explicit_region_phrase(self, detector: RegionDetector) -> None:
        text = "For california residents: You have the right to request data deletion."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        assert "US" in result["regions"]

    @pytest.mark.asyncio
    async def test_explicit_eu_phrase(self, detector: RegionDetector) -> None:
        text = "For users in the eu, additional rights apply under data protection law."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        assert "EU" in result["regions"]

    @pytest.mark.asyncio
    async def test_multiple_regions(self, detector: RegionDetector) -> None:
        text = (
            "We comply with GDPR for European users and CCPA for California residents. "
            "PIPEDA also applies to Canadian users."
        )
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/privacy"
        )
        regions = result["regions"]
        assert "EU" in regions
        assert "US" in regions
        assert "Canada" in regions

    @pytest.mark.asyncio
    async def test_no_regions_defaults_to_global(self, detector: RegionDetector) -> None:
        text = "Welcome to our website. We offer great products and services."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/about"
        )
        assert result["regions"] == ["global"]

    @pytest.mark.asyncio
    async def test_jurisdiction_clause(self, detector: RegionDetector) -> None:
        text = "This agreement is governed by the laws of the State of California, United States."
        result = await detector.detect_regions(
            text=text, metadata={}, url="https://example.com/terms"
        )
        assert "US" in result["regions"]


# ── Compliance frameworks completeness ──────────────────────────────


class TestComplianceFrameworks:
    def test_major_frameworks_covered(self, detector: RegionDetector) -> None:
        frameworks = detector.compliance_frameworks
        assert "GDPR" in frameworks
        assert "CCPA" in frameworks
        assert "PIPEDA" in frameworks
        assert "LGPD" in frameworks
        assert "HIPAA" in frameworks

    def test_all_framework_values_are_lists(self, detector: RegionDetector) -> None:
        for regions in detector.compliance_frameworks.values():
            assert isinstance(regions, list)
            assert len(regions) > 0
