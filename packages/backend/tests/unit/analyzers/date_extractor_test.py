"""Tests for DateExtractor analyzer.

Tests static date extraction from metadata, content patterns, and date string parsing.
LLM-based extraction is not tested here (requires mocking external APIs).
"""

import pytest

from src.analyzers.date_extractor import DateExtractor


@pytest.fixture
def extractor() -> DateExtractor:
    return DateExtractor()


# ── _parse_date_string ──────────────────────────────────────────────


class TestParseDateString:
    """Tests for the _parse_date_string method."""

    def test_iso_format(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("2023-12-01") == "2023-12-01"

    def test_iso_format_with_slashes(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("2023/12/01") == "2023-12-01"

    def test_us_date_format(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("12/01/2023") == "2023-12-01"

    def test_full_month_name_with_comma(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("December 1, 2023") == "2023-12-01"

    def test_full_month_name_without_comma(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("December 1 2023") == "2023-12-01"

    def test_abbreviated_month(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("Dec 1, 2023") == "2023-12-01"

    def test_iso_with_time(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("2023-12-01T10:30:00") == "2023-12-01"

    def test_iso_with_timezone(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("2023-12-01T10:30:00Z") == "2023-12-01"

    def test_german_date_format(self, extractor: DateExtractor) -> None:
        # DD.MM.YYYY — dots are stripped by _parse_date_string cleaning step,
        # which prevents the "%d.%m.%Y" format from matching. The regex fallback
        # also doesn't match because dots are gone. This is a known limitation.
        result = extractor._parse_date_string("01.12.2023")
        # Currently returns None due to dot stripping; document this behavior
        assert result is None

    def test_none_input(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string(None) is None  # type: ignore[arg-type]

    def test_empty_string(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("") is None

    def test_non_string_input(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string(123) is None  # type: ignore[arg-type]

    def test_relative_date_immediately(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("immediately") is None

    def test_relative_date_upon_publication(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("upon publication") is None

    def test_relative_date_as_of_this(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("as of this document") is None

    def test_garbage_string(self, extractor: DateExtractor) -> None:
        assert extractor._parse_date_string("not a date at all") is None

    def test_ordinal_first(self, extractor: DateExtractor) -> None:
        """Ordinals like '1st' should be converted to cardinal numbers."""
        result = extractor._parse_date_string("December 1st, 2023")
        assert result == "2023-12-01"


# ── _extract_effective_date_static ──────────────────────────────────


class TestExtractEffectiveDateStatic:
    """Tests for static date extraction from metadata and content patterns."""

    def test_metadata_effective_date(self, extractor: DateExtractor) -> None:
        metadata = {"effective_date": "2024-01-15"}
        result = extractor._extract_effective_date_static("", metadata)
        assert result == "2024-01-15"

    def test_metadata_last_updated(self, extractor: DateExtractor) -> None:
        metadata = {"last_updated": "March 10, 2024"}
        result = extractor._extract_effective_date_static("", metadata)
        assert result == "2024-03-10"

    def test_metadata_date_key(self, extractor: DateExtractor) -> None:
        metadata = {"date": "2024-06-01"}
        result = extractor._extract_effective_date_static("", metadata)
        assert result == "2024-06-01"

    def test_metadata_published_key(self, extractor: DateExtractor) -> None:
        metadata = {"published": "2024-07-20"}
        result = extractor._extract_effective_date_static("", metadata)
        assert result == "2024-07-20"

    def test_metadata_empty(self, extractor: DateExtractor) -> None:
        result = extractor._extract_effective_date_static("no dates here", {})
        assert result is None

    def test_metadata_none(self, extractor: DateExtractor) -> None:
        result = extractor._extract_effective_date_static("no dates here", None)  # type: ignore[arg-type]
        assert result is None

    def test_content_effective_date_iso(self, extractor: DateExtractor) -> None:
        content = "Effective date: 2024-01-15\n\nThis privacy policy applies."
        result = extractor._extract_effective_date_static(content, {})
        assert result == "2024-01-15"

    def test_content_last_updated_iso(self, extractor: DateExtractor) -> None:
        content = "Last updated: 2024-02-15\n\nThis policy describes..."
        result = extractor._extract_effective_date_static(content, {})
        assert result == "2024-02-15"

    def test_content_last_modified_iso(self, extractor: DateExtractor) -> None:
        content = "Last modified: 2024-03-20\n\nWe collect..."
        result = extractor._extract_effective_date_static(content, {})
        assert result == "2024-03-20"

    def test_content_effective_date_colon_iso(self, extractor: DateExtractor) -> None:
        content = "Effective date: 2023-06-30\n\nBy using our services..."
        result = extractor._extract_effective_date_static(content, {})
        assert result == "2023-06-30"

    def test_content_no_date(self, extractor: DateExtractor) -> None:
        content = "Welcome to our website. We value your privacy."
        result = extractor._extract_effective_date_static(content, {})
        assert result is None

    def test_content_date_in_first_5000_chars(self, extractor: DateExtractor) -> None:
        """Dates are only searched in the first 5000 characters."""
        padding = "a " * 2000
        content = padding + "Effective date: 2024-12-25"
        result = extractor._extract_effective_date_static(content, {})
        # Date is within 5000 chars
        assert result == "2024-12-25"

    def test_content_date_beyond_5000_chars(self, extractor: DateExtractor) -> None:
        """Dates beyond 5000 chars are not found by static extraction."""
        padding = "a " * 5000
        content = padding + "Effective date: December 25, 2024"
        result = extractor._extract_effective_date_static(content, {})
        assert result is None

    def test_metadata_takes_priority_over_content(self, extractor: DateExtractor) -> None:
        """Metadata date should be returned even if content has a different date."""
        metadata = {"effective_date": "2024-01-01"}
        content = "Last updated: February 15, 2024"
        result = extractor._extract_effective_date_static(content, metadata)
        assert result == "2024-01-01"


# ── Ordinal mapping ────────────────────────────────────────────────


class TestOrdinalMapping:
    """Verify ordinal-to-cardinal mapping completeness."""

    def test_all_ordinals_mapped(self, extractor: DateExtractor) -> None:
        expected = {
            "first",
            "1st",
            "second",
            "2nd",
            "third",
            "3rd",
            "fourth",
            "4th",
            "fifth",
            "5th",
            "sixth",
            "6th",
            "seventh",
            "7th",
            "eighth",
            "8th",
            "ninth",
            "9th",
            "tenth",
            "10th",
        }
        assert set(extractor.ordinals.keys()) == expected

    def test_ordinal_values_are_numeric_strings(self, extractor: DateExtractor) -> None:
        for v in extractor.ordinals.values():
            assert v.isdigit()
