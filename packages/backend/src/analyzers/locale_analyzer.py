"""
Locale Detection Analyzer

Specialized analyzer for detecting document locale/language through multiple methods:
metadata analysis, URL patterns, text heuristics, and LLM fallback.
"""

import json
import re
from typing import Any, cast

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.utils.llm_usage import usage_tracking
from src.utils.llm_usage_tracking_mixin import LLMUsageTrackingMixin

logger = get_logger(__name__, component="locale detection")


class LocaleAnalyzer(LLMUsageTrackingMixin):
    """
    AI-powered locale detector for determining document language and region.

    Uses a multi-layered approach prioritizing speed and accuracy:
    1. Metadata analysis (most reliable)
    2. URL pattern matching
    3. Text heuristics
    4. LLM analysis (fallback)
    """

    def __init__(self):
        super().__init__()

        # URL locale patterns for common website structures
        self.locale_patterns = {
            r"/en[-_]?us?/": "en-US",
            r"/en[-_]?gb?/": "en-GB",
            r"/en[-_]?ca?/": "en-CA",
            r"/en/": "en-US",  # Default English to US
            r"/fr[-_]?fr?/": "fr-FR",
            r"/de[-_]?de?/": "de-DE",
            r"/es[-_]?es?/": "es-ES",
            r"/it[-_]?it?/": "it-IT",
            r"/pt[-_]?br?/": "pt-BR",
            r"/ja[-_]?jp?/": "ja-JP",
            r"/zh[-_]?cn?/": "zh-CN",
            r"/ko[-_]?kr?/": "ko-KR",
        }

        # Common English words/phrases in policy documents
        self.english_indicators = [
            "privacy policy",
            "terms of service",
            "effective date",
            "last updated",
            "we collect",
            "personal information",
            "data protection",
            "your rights",
            "governing law",
            "jurisdiction",
            "dispute resolution",
        ]

        # Common non-English patterns for basic language detection
        self.non_english_patterns = {
            "fr": [
                "politique de confidentialité",
                "conditions d'utilisation",
                "données personnelles",
            ],
            "de": ["datenschutzerklärung", "nutzungsbedingungen", "personenbezogene daten"],
            "es": ["política de privacidad", "términos de servicio", "datos personales"],
            "it": ["informativa sulla privacy", "termini di servizio", "dati personali"],
        }

    async def detect_locale(
        self, text: str, metadata: dict[str, Any], url: str | None = None
    ) -> dict[str, Any]:
        """
        Detect the locale of a document.

        Priority order:
        1. Check metadata for explicit locale information
        2. Check URL patterns for locale indicators
        3. Use simple text heuristics (common words, character patterns)
        4. Use LLM analysis of text content (only if needed)
        5. Fallback to English (en-US)

        Args:
            text: Document content
            metadata: Document metadata
            url: Optional document URL for pattern analysis

        Returns:
            Dict containing locale, confidence, and language_name
        """
        # 1. Check reliable metadata sources first
        if metadata:
            # Open Graph tags are highly reliable (set for SEO/social sharing)
            for key in ["og:locale", "og:language"]:
                if key in metadata and metadata[key]:
                    locale = metadata[key]
                    logger.debug(f"found locale in metadata ({key}): {locale}")
                    return {
                        "locale": locale,
                        "confidence": 0.95,
                        "language_name": locale,
                    }

            # HTML lang attribute
            if "lang" in metadata and metadata["lang"]:
                locale = metadata["lang"]
                logger.debug(f"found locale in HTML lang attribute: {locale}")
                return {
                    "locale": locale,
                    "confidence": 0.85,
                    "language_name": locale,
                }

            # Check alternate languages from link tags
            if "alternate_languages" in metadata and isinstance(
                metadata["alternate_languages"], dict
            ):
                # If we have alternate languages, check if current page matches one
                # For now, assume primary language is first or most common
                alt_langs = cast(dict[str, Any], metadata["alternate_languages"])
                if alt_langs:
                    # Extract locale from first alternate (heuristic)
                    first_lang = list(alt_langs.keys())[0]
                    if first_lang:
                        logger.debug(f"found locale in alternate languages metadata: {first_lang}")
                        return {
                            "locale": first_lang,
                            "confidence": 0.75,
                            "language_name": first_lang,
                        }

        # 2. Check URL patterns for locale indicators
        if url:
            url_lower = url.lower()
            # Common locale patterns in URLs: /en/, /en-us/, /fr/, /de/, etc.

            for pattern, locale in self.locale_patterns.items():
                if re.search(pattern, url_lower):
                    logger.debug(f"matched locale from URL pattern '{pattern}': {locale}")
                    return {
                        "locale": locale,
                        "confidence": 0.80,
                        "language_name": locale,
                    }

        # 3. Simple text heuristics (fast, no LLM needed)
        text_lower = text.lower()[:1000]  # Check first 1000 chars

        english_count = sum(1 for indicator in self.english_indicators if indicator in text_lower)

        # If strong English indicators found, likely English
        if english_count >= 3:
            logger.debug(f"detected English from text heuristics: {english_count} indicators found")
            return {
                "locale": "en-US",
                "confidence": 0.70,
                "language_name": "English (United States)",
            }

        # Check for non-English patterns
        for lang_code, patterns in self.non_english_patterns.items():
            matches = sum(1 for pattern in patterns if pattern in text_lower)
            if matches >= 2:
                locale_map = {"fr": "fr-FR", "de": "de-DE", "es": "es-ES", "it": "it-IT"}
                detected_locale = locale_map.get(lang_code, lang_code)
                logger.debug(
                    f"detected {detected_locale} from text heuristics: {matches} patterns matched"
                )
                return {
                    "locale": detected_locale,
                    "confidence": 0.70,
                    "language_name": detected_locale,
                }

        # 4. Use LLM for text-based detection (only if pre-filtering couldn't determine)
        logger.debug("locale not determined via metadata or heuristics; invoking LLM analysis")

        # Extract representative text sample (middle portion for better language detection)
        text_length = len(text)
        if text_length > 1000:
            start_pos = text_length // 2 - 500
            text_sample = text[start_pos : start_pos + 1000]
        else:
            text_sample = text

        prompt = f"""Analyze this text sample and determine the language/locale.

Text sample:
{text_sample}

Return a JSON object with:
- locale: detected locale (format: "en-US", "fr-FR", "de-DE", etc.)
- confidence: float 0-1 indicating detection confidence
- language_name: human readable language name

Be specific with locale (include country when possible).

Example output:
{{
  "locale": "en-US",
  "confidence": 0.95,
  "language_name": "English (United States)"
}}"""

        system_prompt = """You are a language detection expert. Analyze text and determine language/locale accurately."""

        try:
            async with usage_tracking(self._create_usage_tracker("detect_locale")):
                response = await acompletion_with_fallback(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )

            choice = response.choices[0]
            if not hasattr(choice, "message"):
                raise ValueError("Unexpected response format: missing message attribute")
            message = choice.message  # type: ignore[attr-defined]
            if not message:
                raise ValueError("Unexpected response format: message is None")
            content = message.content  # type: ignore[attr-defined]
            if not content:
                raise ValueError("Empty response from LLM")

            result = json.loads(content)
            logger.debug(
                f"LLM locale detection result: {result['locale']} (confidence: {result['confidence']})"
            )
            return result  # type: ignore

        except Exception as e:
            logger.warning(f"locale detection process failed: {e}")
            return {
                "locale": "en-US",
                "confidence": 0.5,
                "language_name": "English (fallback)",
            }
