"""Tests for DocumentClassifier analyzer.

Tests URL pattern matching, metadata keyword matching, and content heuristics.
LLM fallback classification is not tested (requires mocking external APIs).
"""

import pytest

from src.analyzers.document_classifier import DocumentClassifier


@pytest.fixture
def classifier() -> DocumentClassifier:
    return DocumentClassifier()


# ── URL pattern matching ────────────────────────────────────────────


class TestURLPatternClassification:
    """Tests for URL-based document type detection."""

    @pytest.mark.asyncio
    async def test_privacy_policy_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/privacy-policy",
            text="We collect personal data. Effective date: 2024-01-01. " * 20,
            metadata={},
        )
        assert result["classification"] == "privacy_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_privacy_url_short_path(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/privacy",
            text="We collect personal data. Effective date: 2024-01-01. " * 20,
            metadata={},
        )
        assert result["classification"] == "privacy_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_terms_of_service_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/terms-of-service",
            text="By using our service you agree to these terms. Governing law applies. " * 15,
            metadata={},
        )
        assert result["classification"] == "terms_of_service"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_tos_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/tos",
            text="By using our service you agree. Effective date: 2024. " * 20,
            metadata={},
        )
        assert result["classification"] == "terms_of_service"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_cookie_policy_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/cookie-policy",
            text="We use cookies to improve your experience. Effective date applies. " * 15,
            metadata={},
        )
        assert result["classification"] == "cookie_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_copyright_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/copyright",
            text="Copyright infringement policy. DMCA notices. Governing law applies. " * 15,
            metadata={},
        )
        assert result["classification"] == "copyright_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_dmca_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/dmca",
            text="DMCA takedown procedure. Copyright claims and dispute resolution. " * 15,
            metadata={},
        )
        assert result["classification"] == "copyright_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_dpa_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/data-processing-agreement",
            text="Data processing agreement between controller and processor. Liability limits. "
            * 15,
            metadata={},
        )
        assert result["classification"] == "data_processing_agreement"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_gdpr_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/gdpr",
            text="This GDPR policy applies to EU residents. Effective date of compliance. " * 15,
            metadata={},
        )
        assert result["classification"] == "gdpr_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_community_guidelines_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/community-guidelines",
            text="Our community guidelines protect users. Governing law and liability apply. " * 15,
            metadata={},
        )
        assert result["classification"] == "community_guidelines"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_international_privacy_url_german(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/datenschutz",
            text="Personenbezogene Daten werden verarbeitet. Effective date: 2024. " * 20,
            metadata={},
        )
        assert result["classification"] == "privacy_policy"

    @pytest.mark.asyncio
    async def test_legal_nested_url(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/legal/privacy",
            text="We process your data responsibly. Last updated. Effective date. " * 20,
            metadata={},
        )
        assert result["classification"] == "privacy_policy"


# ── URL pattern with insufficient content ───────────────────────────


class TestURLPatternWithInsufficientContent:
    """URL pattern matches but content is too short / not legal."""

    @pytest.mark.asyncio
    async def test_privacy_url_with_short_non_legal_content(
        self, classifier: DocumentClassifier
    ) -> None:
        """Short content without legal indicators should still classify if > 500 chars."""
        result = await classifier.classify_document(
            url="https://example.com/privacy-policy",
            text="Click here. " * 5,  # < 500 chars, no legal indicators
            metadata={},
        )
        # URL match requires either legal content or > 500 chars
        assert result["classification"] != "privacy_policy" or len("Click here. " * 5) > 500


# ── Metadata classification ─────────────────────────────────────────


class TestMetadataClassification:
    """Tests for metadata-based document type detection."""

    @pytest.mark.asyncio
    async def test_metadata_privacy_policy_title(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/legal/doc123",
            text="We collect your data for various purposes. " * 20,
            metadata={"title": "Privacy Policy - Example Corp"},
        )
        assert result["classification"] == "privacy_policy"
        assert result["is_legal_document"] is True

    @pytest.mark.asyncio
    async def test_metadata_terms_title(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/legal/doc456",
            text="By using our services you agree. " * 20,
            metadata={"title": "Terms of Service"},
        )
        assert result["classification"] == "terms_of_service"

    @pytest.mark.asyncio
    async def test_metadata_cookie_policy_description(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/legal/cookies",
            text="We use cookies to enhance your experience. " * 20,
            metadata={"description": "Our cookie policy explains how we use cookies"},
        )
        assert result["classification"] == "cookie_policy"

    @pytest.mark.asyncio
    async def test_metadata_short_content_rejected(self, classifier: DocumentClassifier) -> None:
        """Metadata match should be rejected if content is < 300 chars."""
        result = await classifier.classify_document(
            url="https://example.com/page",
            text="Short",
            metadata={"title": "Privacy Policy"},
        )
        # Should NOT classify as privacy_policy due to short content
        assert result["classification"] != "privacy_policy" or len("Short") > 300


# ── Content heuristics ──────────────────────────────────────────────


class TestContentHeuristics:
    """Tests for content keyword-based classification."""

    @pytest.mark.asyncio
    async def test_privacy_keywords_strong(self, classifier: DocumentClassifier) -> None:
        content = (
            "Effective date: 2024-01-01. "
            "We collect personal information, personal data, and data collection practices. "
            "Data sharing with third parties. Data retention policy. "
            "We process your data protection requests and privacy rights. "
        ) * 5
        result = await classifier.classify_document(
            url="https://example.com/document",
            text=content,
            metadata={},
        )
        assert result["classification"] == "privacy_policy"

    @pytest.mark.asyncio
    async def test_terms_keywords_strong(self, classifier: DocumentClassifier) -> None:
        content = (
            "Last updated: 2024. "
            "Terms of service. Acceptance of terms. "
            "Governing law and jurisdiction apply. "
            "Limitation of liability. Indemnification clause. "
            "Dispute resolution through arbitration. "
        ) * 5
        result = await classifier.classify_document(
            url="https://example.com/document",
            text=content,
            metadata={},
        )
        assert result["classification"] == "terms_of_service"


# ── Quick rejection ─────────────────────────────────────────────────


class TestQuickRejection:
    """Tests for non-legal document rejection."""

    @pytest.mark.asyncio
    async def test_very_short_content_rejected(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/page",
            text="Hello",
            metadata={},
        )
        assert result["classification"] == "other"
        assert result["is_legal_document"] is False

    @pytest.mark.asyncio
    async def test_navigation_page_rejected(self, classifier: DocumentClassifier) -> None:
        result = await classifier.classify_document(
            url="https://example.com/page",
            text="home about contact search navigation menu sidebar",
            metadata={},
        )
        assert result["classification"] == "other"
        assert result["is_legal_document"] is False


# ── Category list completeness ──────────────────────────────────────


class TestCategoryCompleteness:
    def test_categories_includes_other(self, classifier: DocumentClassifier) -> None:
        assert "other" in classifier.categories

    def test_categories_includes_all_expected(self, classifier: DocumentClassifier) -> None:
        expected = {
            "privacy_policy",
            "terms_of_service",
            "cookie_policy",
            "terms_and_conditions",
            "data_processing_agreement",
            "gdpr_policy",
            "copyright_policy",
            "community_guidelines",
            "children_privacy_policy",
            "other",
        }
        assert set(classifier.categories) == expected
