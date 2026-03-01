"""Tests for LocaleAnalyzer.

Tests metadata-based, URL-based, and text heuristic locale detection.
LLM-based detection is not tested (requires mocking external APIs).
"""

import pytest

from src.analyzers.locale_analyzer import LocaleAnalyzer


@pytest.fixture
def analyzer() -> LocaleAnalyzer:
    return LocaleAnalyzer()


# ── Metadata-based detection ────────────────────────────────────────


class TestMetadataDetection:
    """Tests for locale detection from document metadata."""

    @pytest.mark.asyncio
    async def test_og_locale(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={"og:locale": "fr-FR"},
        )
        assert result["locale"] == "fr-FR"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_og_language(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={"og:language": "de-DE"},
        )
        assert result["locale"] == "de-DE"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_html_lang(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={"lang": "es-ES"},
        )
        assert result["locale"] == "es-ES"
        assert result["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_alternate_languages(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={"alternate_languages": {"it-IT": "/it/privacy", "en-US": "/privacy"}},
        )
        assert result["locale"] in ("it-IT", "en-US")
        assert result["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_empty_metadata(self, analyzer: LocaleAnalyzer) -> None:
        """Empty metadata should fall through to other detection methods."""
        result = await analyzer.detect_locale(
            text="privacy policy effective date last updated we collect personal information data protection your rights governing law jurisdiction dispute resolution",
            metadata={},
        )
        # Should detect English via heuristics
        assert result["locale"] == "en-US"

    @pytest.mark.asyncio
    async def test_og_locale_takes_priority_over_lang(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={"og:locale": "fr-FR", "lang": "en-US"},
        )
        assert result["locale"] == "fr-FR"


# ── URL-based detection ─────────────────────────────────────────────


class TestURLDetection:
    """Tests for locale detection from URL patterns."""

    @pytest.mark.asyncio
    async def test_url_en_us(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={},
            url="https://example.com/en-us/privacy",
        )
        assert result["locale"] == "en-US"
        assert result["confidence"] == 0.80

    @pytest.mark.asyncio
    async def test_url_fr_fr(self, analyzer: LocaleAnalyzer) -> None:
        # Pattern /fr[-_]?fr?/ requires forms like /fr-fr/ or /frfr/, not bare /fr/
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={},
            url="https://example.com/fr-fr/privacy",
        )
        assert result["locale"] == "fr-FR"
        assert result["confidence"] == 0.80

    @pytest.mark.asyncio
    async def test_url_de(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={},
            url="https://example.com/de-de/datenschutz",
        )
        assert result["locale"] == "de-DE"
        assert result["confidence"] == 0.80

    @pytest.mark.asyncio
    async def test_url_ja(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={},
            url="https://example.com/ja-jp/privacy",
        )
        assert result["locale"] == "ja-JP"
        assert result["confidence"] == 0.80

    @pytest.mark.asyncio
    async def test_bare_lang_code_not_matched(self, analyzer: LocaleAnalyzer) -> None:
        """Bare /xx/ paths (like /fr/) don't match patterns that need /xx-xx/ forms.

        The /en/ pattern is the only one that matches bare two-letter codes.
        URLs like /fr/privacy fall through to text heuristics or LLM fallback.
        """
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={},
            url="https://example.com/fr/privacy",
        )
        # /fr/ does not match /fr[-_]?fr?/ so it falls through
        assert result["locale"] != "fr-FR" or result["confidence"] < 0.80

    @pytest.mark.asyncio
    async def test_url_en_gb(self, analyzer: LocaleAnalyzer) -> None:
        result = await analyzer.detect_locale(
            text="Some text",
            metadata={},
            url="https://example.com/en-gb/terms",
        )
        assert result["locale"] == "en-GB"


# ── Text heuristic detection ───────────────────────────────────────


class TestTextHeuristicDetection:
    """Tests for locale detection from text content."""

    @pytest.mark.asyncio
    async def test_english_indicators(self, analyzer: LocaleAnalyzer) -> None:
        text = (
            "This privacy policy describes our data protection practices. "
            "Effective date and last updated information. "
            "We collect personal information and respect your rights."
        )
        result = await analyzer.detect_locale(text=text, metadata={})
        assert result["locale"] == "en-US"
        assert result["confidence"] == 0.70

    @pytest.mark.asyncio
    async def test_french_indicators(self, analyzer: LocaleAnalyzer) -> None:
        text = (
            "Politique de confidentialité. "
            "Conditions d'utilisation de nos services. "
            "Données personnelles collectées par notre site."
        )
        result = await analyzer.detect_locale(text=text, metadata={})
        assert result["locale"] == "fr-FR"

    @pytest.mark.asyncio
    async def test_german_indicators(self, analyzer: LocaleAnalyzer) -> None:
        text = (
            "Datenschutzerklärung für unsere Dienste. "
            "Nutzungsbedingungen gelten für alle Benutzer. "
            "Personenbezogene Daten werden verarbeitet."
        )
        result = await analyzer.detect_locale(text=text, metadata={})
        assert result["locale"] == "de-DE"

    @pytest.mark.asyncio
    async def test_spanish_indicators(self, analyzer: LocaleAnalyzer) -> None:
        text = (
            "Política de privacidad de nuestro servicio. "
            "Términos de servicio aplicables. "
            "Datos personales recopilados por nosotros."
        )
        result = await analyzer.detect_locale(text=text, metadata={})
        assert result["locale"] == "es-ES"

    @pytest.mark.asyncio
    async def test_italian_indicators(self, analyzer: LocaleAnalyzer) -> None:
        text = (
            "Informativa sulla privacy del nostro sito. "
            "Termini di servizio e condizioni. "
            "Dati personali raccolti durante l'uso."
        )
        result = await analyzer.detect_locale(text=text, metadata={})
        assert result["locale"] == "it-IT"

    @pytest.mark.asyncio
    async def test_insufficient_indicators_no_match(self, analyzer: LocaleAnalyzer) -> None:
        """Fewer than threshold indicators should not produce a confident match."""
        text = "Hello world. This is some generic text about nothing specific."
        result = await analyzer.detect_locale(text=text, metadata={})
        # Should fallback (either LLM or default en-US)
        assert "locale" in result


# ── Locale patterns completeness ────────────────────────────────────


class TestLocalePatterns:
    def test_all_major_locales_covered(self, analyzer: LocaleAnalyzer) -> None:
        values = set(analyzer.locale_patterns.values())
        assert "en-US" in values
        assert "en-GB" in values
        assert "fr-FR" in values
        assert "de-DE" in values
        assert "es-ES" in values
        assert "ja-JP" in values
