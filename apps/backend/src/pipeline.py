"""
Enterprise Legal Document Crawling Pipeline

This module provides a comprehensive crawling pipeline that integrates the ClauseaCrawler
with AI-powered document analysis for legal document discovery and processing.

Architecture Decisions:
1. **Modular Design**: Separates concerns into distinct classes for crawling, analysis,
   and storage, enabling easy testing and maintenance.

2. **Async/Await Pattern**: Uses asyncio throughout for optimal I/O performance when
   dealing with multiple network requests and database operations.

3. **Comprehensive Error Handling**: Implements graceful error handling with detailed
   logging to ensure pipeline robustness and easy debugging.

4. **Memory Management**: Includes memory monitoring and optimization strategies for
   large-scale crawling operations.

5. **Rate Limiting**: Built-in respect for robots.txt and configurable delays to be
   a good web citizen.

6. **Deduplication**: Smart URL and content deduplication to avoid processing
   duplicate documents.

7. **Incremental Processing**: Processes products sequentially to manage memory
   and respect rate limits while maintaining data consistency.

Performance Characteristics:
- Memory efficient: Processes products one at a time
- Network optimized: Concurrent requests with configurable limits
- Database efficient: Bulk operations and smart update logic
- Scalable: Can handle hundreds of products and thousands of documents

Usage:
    # Run the complete pipeline
    python -m src.pipeline

    # Or use programmatically
    from src.pipeline import LegalDocumentPipeline

    pipeline = LegalDocumentPipeline()
    results = await pipeline.run()
"""

import asyncio
import hashlib
import json
import re
import time
import tracemalloc
from datetime import datetime
from typing import Any, cast

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.core.database import get_db
from src.core.logging import get_logger
from src.crawler import ClauseaCrawler, CrawlResult
from src.llm import SupportedModel, acompletion_with_fallback
from src.models.document import Document, Region
from src.models.product import Product
from src.services.service_factory import create_document_service, create_product_service
from src.utils.llm_usage import usage_tracking
from src.utils.llm_usage_tracking_mixin import LLMUsageTrackingMixin
from src.utils.markdown import markdown_to_text
from src.utils.perf import log_memory_usage, memory_monitor_task

load_dotenv()

logger = get_logger(__name__)


class ProcessingStats(BaseModel):
    """Statistics for document processing pipeline."""

    products_processed: int = 0
    products_failed: int = 0
    failed_product_slugs: list[str] = Field(default_factory=list)
    total_urls_crawled: int = 0
    total_documents_found: int = 0
    legal_documents_processed: int = 0
    legal_documents_stored: int = 0
    english_documents: int = 0
    non_english_skipped: int = 0
    duplicates_skipped: int = 0
    processing_time_seconds: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate product processing success rate."""
        total = self.products_processed + self.products_failed
        return (self.products_processed / total * 100) if total > 0 else 0.0

    @property
    def legal_detection_rate(self) -> float:
        """Calculate legal document detection rate."""
        return (
            (self.legal_documents_processed / self.total_documents_found * 100)
            if self.total_documents_found > 0
            else 0.0
        )


class DocumentAnalyzer(LLMUsageTrackingMixin):
    """
    AI-powered document analyzer for locale detection, legal classification, and region analysis.

    This class encapsulates all AI/LLM interactions for document analysis, providing
    a clean interface for the main pipeline while handling API errors gracefully.
    """

    def __init__(
        self,
        model_name: SupportedModel | None = None,
        max_content_length: int = 5000,
    ):
        """
        Initialize the document analyzer.

        Args:
            model_name: Optional LLM model to use for analysis. If None, uses default priority list with fallback.
            max_content_length: Maximum content length to send to LLM
        """
        super().__init__()

        self.model_name = model_name
        self.max_content_length = max_content_length

        # Document type categories for classification
        self.categories = [
            "privacy_policy",
            "terms_of_service",
            "cookie_policy",
            "terms_and_conditions",
            "data_processing_agreement",
            "gdpr_policy",
            "copyright_policy",
            "safety_policy",
            "other",
        ]

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
                    logger.debug(f"Found locale in metadata ({key}): {locale}")
                    return {
                        "locale": locale,
                        "confidence": 0.95,
                        "language_name": locale,
                    }

            # HTML lang attribute
            if "lang" in metadata and metadata["lang"]:
                locale = metadata["lang"]
                logger.debug(f"Found locale in HTML lang attribute: {locale}")
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
                alt_langs = metadata["alternate_languages"]
                if alt_langs:
                    # Extract locale from first alternate (heuristic)
                    first_lang = list(alt_langs.keys())[0]
                    if first_lang:
                        logger.debug(f"Found locale from alternate languages: {first_lang}")
                        return {
                            "locale": first_lang,
                            "confidence": 0.75,
                            "language_name": first_lang,
                        }

        # 2. Check URL patterns for locale indicators
        if url:
            url_lower = url.lower()
            # Common locale patterns in URLs: /en/, /en-us/, /fr/, /de/, etc.
            locale_patterns = {
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

            for pattern, locale in locale_patterns.items():
                if re.search(pattern, url_lower):
                    logger.debug(f"Found locale from URL pattern ({pattern}): {locale}")
                    return {
                        "locale": locale,
                        "confidence": 0.80,
                        "language_name": locale,
                    }

        # 3. Simple text heuristics (fast, no LLM needed)
        text_lower = text.lower()[:1000]  # Check first 1000 chars

        # Common English words/phrases in legal documents
        english_indicators = [
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
        english_count = sum(1 for indicator in english_indicators if indicator in text_lower)

        # Common non-English patterns (basic detection)
        non_english_patterns = {
            "fr": [
                "politique de confidentialité",
                "conditions d'utilisation",
                "données personnelles",
            ],
            "de": ["datenschutzerklärung", "nutzungsbedingungen", "personenbezogene daten"],
            "es": ["política de privacidad", "términos de servicio", "datos personales"],
            "it": ["informativa sulla privacy", "termini di servizio", "dati personali"],
        }

        # If strong English indicators found, likely English
        if english_count >= 3:
            logger.debug(f"Detected English from text heuristics ({english_count} indicators)")
            return {
                "locale": "en-US",
                "confidence": 0.70,
                "language_name": "English (United States)",
            }

        # Check for non-English patterns
        for lang_code, patterns in non_english_patterns.items():
            matches = sum(1 for pattern in patterns if pattern in text_lower)
            if matches >= 2:
                locale_map = {"fr": "fr-FR", "de": "de-DE", "es": "es-ES", "it": "it-IT"}
                detected_locale = locale_map.get(lang_code, lang_code)
                logger.debug(
                    f"Detected {detected_locale} from text heuristics ({matches} patterns)"
                )
                return {
                    "locale": detected_locale,
                    "confidence": 0.70,
                    "language_name": detected_locale,
                }

        # 4. Use LLM for text-based detection (only if pre-filtering couldn't determine)
        logger.debug("Locale not found via metadata, using LLM analysis")

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
            logger.debug(f"LLM locale detection result: {result}")
            return result  # type: ignore

        except Exception as e:
            logger.warning(f"LLM locale detection failed: {e}")
            return {
                "locale": "en-US",
                "confidence": 0.5,
                "language_name": "English (fallback)",
            }

    async def classify_document(
        self, url: str, text: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Classify if document is a legal document and determine its type.

        Priority order:
        1. Check URL patterns for document type indicators
        2. Check metadata (title, description) for document type
        3. Check content heuristics (keywords, structure)
        4. Use LLM analysis (only if needed)

        Args:
            url: Document URL
            text: Document content
            metadata: Document metadata

        Returns:
            Dict containing classification, justification, and is_legal_document flag
        """
        # 1. Pre-filter using URL patterns (very fast, no LLM needed)
        url_lower = url.lower()
        url_patterns = {
            "privacy_policy": [
                r"/privacy",
                r"/privacy-policy",
                r"/privacy_policy",
                r"/datenschutz",  # German
                r"/politique-de-confidentialite",  # French
                r"/politica-de-privacidad",  # Spanish
            ],
            "terms_of_service": [
                r"/terms",
                r"/terms-of-service",
                r"/terms_of_service",
                r"/tos",
                r"/terms-and-conditions",
                r"/nutzungsbedingungen",  # German
                r"/conditions-d-utilisation",  # French
                r"/terminos-de-servicio",  # Spanish
            ],
            "cookie_policy": [
                r"/cookie",
                r"/cookie-policy",
                r"/cookie_policy",
                r"/cookies",
                r"/cookie-richtlinie",  # German
            ],
            "copyright_policy": [
                r"/copyright",
                r"/dmca",
                r"/copyright-policy",
            ],
        }

        for doc_type, patterns in url_patterns.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    # Verify it's actually a legal document (not just a link)
                    text_lower = text.lower()
                    legal_indicators = [
                        "effective date",
                        "last updated",
                        "governing law",
                        "jurisdiction",
                        "dispute",
                        "liability",
                        "indemnification",
                    ]
                    has_legal_content = any(
                        indicator in text_lower for indicator in legal_indicators
                    )

                    if has_legal_content or len(text) > 500:  # Substantive content
                        logger.debug(f"Document type from URL pattern ({pattern}): {doc_type}")
                        return {
                            "classification": doc_type,
                            "classification_justification": f"Detected from URL pattern: {pattern}",
                            "is_legal_document": True,
                            "is_legal_document_justification": "URL pattern and content indicate legal document",
                        }

        # 2. Check metadata for document type indicators
        if metadata:
            title = (metadata.get("title") or "").lower()
            description = (
                metadata.get("description") or metadata.get("og:description") or ""
            ).lower()
            combined_meta = f"{title} {description}"

            meta_keywords = {
                "privacy_policy": [
                    "privacy policy",
                    "privacy notice",
                    "data protection",
                    "datenschutz",
                ],
                "terms_of_service": [
                    "terms of service",
                    "terms and conditions",
                    "user agreement",
                    "tos",
                ],
                "cookie_policy": ["cookie policy", "cookie notice", "cookie consent"],
                "copyright_policy": ["copyright", "dmca", "intellectual property"],
            }

            for doc_type, keywords in meta_keywords.items():
                if any(keyword in combined_meta for keyword in keywords):
                    # Check if content is substantial (not just a navigation page)
                    if len(text) > 300:
                        logger.debug(f"Document type from metadata: {doc_type}")
                        return {
                            "classification": doc_type,
                            "classification_justification": "Detected from metadata keywords",
                            "is_legal_document": True,
                            "is_legal_document_justification": "Metadata and content indicate legal document",
                        }

        # 3. Check content heuristics (keywords and structure)
        text_lower = text.lower()
        text_sample = text_lower[:2000]  # Check first 2000 chars

        # Legal document indicators
        legal_keywords = {
            "privacy_policy": [
                "personal information",
                "data collection",
                "data processing",
                "privacy rights",
                "data protection",
                "personal data",
                "information we collect",
            ],
            "terms_of_service": [
                "terms of service",
                "user agreement",
                "acceptance of terms",
                "governing law",
                "dispute resolution",
                "limitation of liability",
                "indemnification",
            ],
            "cookie_policy": [
                "cookie policy",
                "cookies we use",
                "cookie consent",
                "tracking technologies",
                "third-party cookies",
            ],
        }

        # Count matches for each document type
        doc_type_scores: dict[str, int] = {}
        for doc_type, keywords in legal_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_sample)
            if score > 0:
                doc_type_scores[doc_type] = score

        # If we have strong indicators, classify without LLM
        if doc_type_scores:
            best_type = max(doc_type_scores.items(), key=lambda x: x[1])
            if best_type[1] >= 3:  # At least 3 keyword matches
                # Verify it's not just a navigation/link page
                if len(text) > 500 and (
                    "effective" in text_sample or "last updated" in text_sample
                ):
                    logger.debug(
                        f"Document type from content heuristics: {best_type[0]} (score: {best_type[1]})"
                    )
                    return {
                        "classification": best_type[0],
                        "classification_justification": f"Detected from content keywords (score: {best_type[1]})",
                        "is_legal_document": True,
                        "is_legal_document_justification": "Content keywords and structure indicate legal document",
                    }

        # 4. Quick rejection: If content is too short or lacks legal structure, likely not legal
        if len(text) < 200:
            logger.debug("Document too short to be legal document")
            return {
                "classification": "other",
                "classification_justification": "Document too short to be substantive legal content",
                "is_legal_document": False,
                "is_legal_document_justification": "Content length indicates this is not a legal document",
            }

        # Check for navigation/page structure indicators (not legal documents)
        nav_indicators = ["home", "about", "contact", "menu", "navigation", "search"]
        if any(indicator in text_lower[:500] for indicator in nav_indicators) and len(text) < 1000:
            logger.debug("Appears to be navigation/page structure, not legal document")
            return {
                "classification": "other",
                "classification_justification": "Content structure indicates navigation/page, not legal document",
                "is_legal_document": False,
                "is_legal_document_justification": "Lacks substantive legal content structure",
            }

        # 5. Use LLM for classification (only if pre-filtering couldn't determine)
        logger.debug("Inconclusive, using LLM for document classification")
        content_sample = text[: self.max_content_length]
        categories_list = "\n".join(f"- {cat}" for cat in self.categories)

        prompt = f"""Analyze webpage content to determine if it's a legal document and classify its type.

URL: {url}
Content: {content_sample}
Metadata: {json.dumps(metadata, indent=2)}

Categories:
{categories_list}

Return JSON with:
- classification: most appropriate category (use "other" if not legal/unclear)
- classification_justification: brief explanation of category choice
- is_legal_document: boolean (True only for substantive legal text)
- is_legal_document_justification: rationale for legal classification

Example output:
{{
  "classification": "privacy_policy",
  "classification_justification": "The content is a privacy policy for a website.",
  "is_legal_document": True,
  "is_legal_document_justification": "The content is a privacy policy for a website."
}}

Note: Cookie banners, navigation elements, or links to legal documents don't count as legal documents themselves."""

        system_prompt = """You are a legal document classifier. Identify substantive legal content and categorize accurately."""

        try:
            async with usage_tracking(self._create_usage_tracker("classify_document")):
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
            logger.debug(f"Document classification result: {result}")
            return result  # type: ignore

        except Exception as e:
            logger.warning(f"Document classification failed: {e}")
            return {
                "classification": "other",
                "classification_justification": f"Classification failed: {e}",
                "is_legal_document": False,
                "is_legal_document_justification": "Could not analyze due to error",
            }

    async def detect_regions(self, text: str, metadata: dict[str, Any], url: str) -> dict[str, Any]:
        """
        Detect if document applies globally or to specific regions.

        Priority order:
        1. Check URL patterns for region indicators
        2. Check metadata for region information
        3. Check content for explicit region mentions and compliance frameworks
        4. Use LLM analysis (only if needed)

        Args:
            text: Document content
            metadata: Document metadata
            url: Document URL

        Returns:
            Dict containing region analysis with mapped region codes
        """
        # 1. Check URL patterns for region indicators
        url_lower = url.lower()
        url_region_patterns = {
            r"/eu/": ["EU"],
            r"/europe/": ["EU"],
            r"/uk/": ["UK"],
            r"/gb/": ["UK"],
            r"/us/": ["US"],
            r"/usa/": ["US"],
            r"/ca/": ["Canada"],
            r"/canada/": ["Canada"],
            r"/au/": ["Australia"],
            r"/australia/": ["Australia"],
            r"/br/": ["Brazil"],
            r"/brazil/": ["Brazil"],
            r"/kr/": ["South Korea"],
            r"/korea/": ["South Korea"],
            r"/jp/": ["Asia"],  # Japan
            r"/asia/": ["Asia"],
        }

        detected_regions = []
        for pattern, regions in url_region_patterns.items():
            if re.search(pattern, url_lower):
                detected_regions.extend(regions)
                logger.debug(f"Found region from URL pattern ({pattern}): {regions}")

        if detected_regions:
            mapped_regions = []
            for region in detected_regions:
                mapped = self._map_region_name_to_code(region)
                if mapped and mapped not in mapped_regions:
                    mapped_regions.append(mapped)

            if mapped_regions:
                return {
                    "regions": mapped_regions,
                    "confidence": 0.80,
                    "justification": "Detected from URL pattern",
                    "regional_indicators": [f"URL pattern: {url}"],
                }

        # 2. Check metadata for region information
        if metadata:
            # Check for region-specific metadata
            meta_text = json.dumps(metadata).lower()
            if any(term in meta_text for term in ["eu", "european union", "gdpr"]):
                return {
                    "regions": ["EU"],
                    "confidence": 0.75,
                    "justification": "Detected from metadata (EU/GDPR references)",
                    "regional_indicators": ["Metadata contains EU/GDPR references"],
                }

        # 3. Check content for explicit region mentions and compliance frameworks
        text_lower = text.lower()
        text_sample = text_lower[:3000] if len(text_lower) > 3000 else text_lower

        # Compliance framework indicators
        compliance_frameworks = {
            "GDPR": ["EU", "European Union"],
            "CCPA": ["US"],
            "PIPEDA": ["Canada"],
            "LGPD": ["Brazil"],
            "PDPA": ["South Korea"],
        }

        detected_from_content = []
        for framework, regions in compliance_frameworks.items():
            if framework.lower() in text_sample:
                detected_from_content.extend(regions)
                logger.debug(f"Found region from compliance framework ({framework}): {regions}")

        # Explicit region mentions
        region_phrases = {
            "for california residents": ["US"],
            "for california users": ["US"],
            "california privacy": ["US"],
            "for users in the eu": ["EU"],
            "for european users": ["EU"],
            "for uk residents": ["UK"],
            "for canadian users": ["Canada"],
            "for users in canada": ["Canada"],
            "for australian users": ["Australia"],
            "for users in brazil": ["Brazil"],
        }

        for phrase, regions in region_phrases.items():
            if phrase in text_sample:
                detected_from_content.extend(regions)
                logger.debug(f"Found region from explicit mention ({phrase}): {regions}")

        # Governing law / jurisdiction clauses
        jurisdiction_patterns = [
            (r"governed by the laws of (?:the )?([^,\.]+)", ["UK", "US", "Canada"]),
            (r"jurisdiction.*(?:england|wales|united kingdom)", ["UK"]),
            (r"jurisdiction.*(?:california|new york|united states)", ["US"]),
            (r"jurisdiction.*(?:ontario|british columbia|canada)", ["Canada"]),
        ]

        for pattern, default_regions in jurisdiction_patterns:
            matches = list(re.finditer(pattern, text_sample, re.IGNORECASE))
            if matches:
                # Try to extract specific region from match
                detected_from_content.extend(default_regions)
                logger.debug(f"Found region from jurisdiction clause: {default_regions}")

        if detected_from_content:
            # Deduplicate and map regions
            unique_regions = []
            for region in detected_from_content:
                mapped = self._map_region_name_to_code(region)
                if mapped and mapped not in unique_regions:
                    unique_regions.append(mapped)

            if unique_regions:
                return {
                    "regions": unique_regions,
                    "confidence": 0.85,
                    "justification": "Detected from content (compliance frameworks, explicit mentions, or jurisdiction clauses)",
                    "regional_indicators": [f"Content analysis found: {', '.join(unique_regions)}"],
                }

        # 4. Default to global if no specific regions found via pre-filtering
        logger.debug("Found no specific regions, defaulting to global")
        return {
            "regions": ["global"],
            "confidence": 0.70,
            "justification": "No specific regions detected, defaulting to global",
            "regional_indicators": [],
        }

    def _map_region_name_to_code(self, region_name: str) -> Region | None:
        """Map a region name to a Document Region code."""
        region_mapping = {
            "united states": "US",
            "usa": "US",
            "us": "US",
            "america": "US",
            "california": "US",  # California is part of US
            "european union": "EU",
            "eu": "EU",
            "europe": "EU",
            "united kingdom": "UK",
            "uk": "UK",
            "gb": "UK",
            "britain": "UK",
            "england": "UK",
            "wales": "UK",
            "asia": "Asia",
            "australia": "Australia",
            "canada": "Canada",
            "brazil": "Brazil",
            "south korea": "South Korea",
            "korea": "South Korea",
            "israel": "Israel",
        }

        mapped = region_mapping.get(region_name.lower())
        return cast(Region, mapped) if mapped else None

    def _map_regions_to_document_format(
        self, is_global: bool, specific_regions: list[str]
    ) -> list[Region]:
        """Map detected regions to Document Region literals."""
        if is_global:
            return ["global"]

        regions: list[Region] = []
        for region in specific_regions:
            mapped = self._map_region_name_to_code(region)
            if mapped and mapped not in regions:
                regions.append(mapped)

        return regions if regions else ["Other"]

    async def extract_title(
        self, markdown: str, metadata: dict[str, Any], url: str, doc_type: str
    ) -> dict[str, Any]:
        """
        Extract meaningful title from document.

        Args:
            markdown: Document markdown content
            metadata: Document metadata
            url: Document URL
            doc_type: Classified document type

        Returns:
            Dict containing extracted title and confidence
        """
        # Quick extraction from metadata first
        if metadata:
            for key in ["title", "og:title"]:
                if key in metadata and metadata[key]:
                    title = metadata[key].strip()
                    if title:
                        return {"title": title, "confidence": 0.9}

        # Extract from markdown content
        lines = markdown.split("\n")
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith("#") and len(line) < 200:
                title = line.lstrip("#").strip()
                if title:
                    return {"title": title, "confidence": 0.8}

        # Fallback to document type with domain
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.replace("www.", "")
        type_titles = {
            "privacy_policy": "Privacy Policy",
            "terms_of_service": "Terms of Service",
            "cookie_policy": "Cookie Policy",
            "terms_and_conditions": "Terms and Conditions",
            "data_processing_agreement": "Data Processing Agreement",
            "gdpr_policy": "GDPR Policy",
            "copyright_policy": "Copyright Policy",
            "safety_policy": "Safety Policy",
        }

        title = f"{type_titles.get(doc_type, 'Legal Document')} - {domain}"
        return {"title": title, "confidence": 0.5}

    async def extract_effective_date(self, content: str, metadata: dict[str, Any]) -> str | None:
        """
        Extract the effective date from a legal document.

        First attempts static extraction from metadata and common patterns,
        then falls back to LLM analysis if needed.

        Args:
            content: Document text content
            metadata: Document metadata

        Returns:
            Effective date as ISO string (YYYY-MM-DD) or None if not found
        """

        # Try static extraction first
        effective_date = await self._extract_effective_date_static(content, metadata)
        if effective_date:
            logger.debug(f"Found effective date statically: {effective_date}")
            return effective_date

        # Fall back to LLM analysis
        logger.debug("Static extraction failed, using LLM for effective date")
        return await self._extract_effective_date_llm(content, metadata)

    async def _extract_effective_date_static(
        self, content: str, metadata: dict[str, Any]
    ) -> str | None:
        """
        Attempt static extraction of effective date from metadata and content patterns.

        Args:
            content: Document text content
            metadata: Document metadata

        Returns:
            Effective date as ISO string or None
        """
        import re

        # Check metadata first
        if metadata:
            for key in ["effective_date", "last_updated", "date", "published"]:
                if key in metadata and metadata[key]:
                    date_str = str(metadata[key]).strip()
                    parsed_date = self._parse_date_string(date_str)
                    if parsed_date:
                        return parsed_date

        # Common effective date patterns in legal documents (ordered by specificity)
        # More specific patterns first to avoid false matches
        patterns = [
            # Explicit "Effective date:" or "Effective as of:"
            r"effective\s+(?:date|as\s+of):\s*([^.\n<]+)",
            # "Last updated:" or "Last modified:"
            r"last\s+(?:updated|modified):?\s*([^.\n<]+)",
            # "Updated on:" or "Modified on:"
            r"(?:updated|modified)\s+on:?\s*([^.\n<]+)",
            # "Revision date:" or "Version date:"
            r"(?:revision|version)\s+date:?\s*([^.\n<]+)",
            # "This policy is effective..." or "This agreement takes effect..."
            r"(?:this\s+(?:policy|agreement|document|terms?)\s+)?(?:is\s+)?(?:effective|takes\s+effect)\s+(?:as\s+of\s+)?([^.\n<]+)",
            # "Effective:" standalone
            r"effective:?\s*([^.\n<]+)",
            # "Date of effect:" or "Date effective:"
            r"date\s+(?:of\s+effect|effective):?\s*([^.\n<]+)",
            # "Published:" or "Publication date:"
            r"(?:publication\s+)?date:?\s*([^.\n<]+)",
            # ISO date format in context (YYYY-MM-DD)
            r"(?:effective|updated|modified|published).*?(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            # Common date formats near "effective" keywords
            r"(?:effective|updated).*?((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4})",
            r"(?:effective|updated).*?((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[\s\.]+\d{1,2},?\s+\d{4})",
        ]

        # Search in first 5000 chars where dates are typically mentioned
        search_text = content[:5000].lower()

        for pattern in patterns:
            matches = re.finditer(pattern, search_text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                date_str = match.group(1).strip()
                # Clean up common trailing words/phrases
                date_str = re.sub(r"\s*(and|or|,|;|\.|$).*$", "", date_str, flags=re.IGNORECASE)
                date_str = date_str.strip()

                if date_str:
                    parsed_date = self._parse_date_string(date_str)
                    if parsed_date:
                        logger.debug(
                            f"Extracted date from pattern '{pattern}': {date_str} -> {parsed_date}"
                        )
                        return parsed_date

        return None

    async def _extract_effective_date_llm(
        self, content: str, metadata: dict[str, Any]
    ) -> str | None:
        """
        Use LLM to extract effective date from document content.

        Args:
            content: Document text content
            metadata: Document metadata

        Returns:
            Effective date as ISO string or None if not found
        """
        # Use first portion of content where dates are typically mentioned
        content_sample = content[:3000] if len(content) > 3000 else content

        prompt = f"""Analyze this legal document to find the effective date.

Content: {content_sample}
Metadata: {json.dumps(metadata, indent=2) if metadata else "None"}

Look for:
- "Effective date:", "Effective as of:", etc.
- "Last updated:", "Updated on:", etc.
- "This policy is effective...", "This agreement takes effect..."
- Any explicit date mentioned as when the document becomes effective

Return JSON:
{{
    "effective_date": "YYYY-MM-DD" or null,
    "confidence": float 0-1,
    "source_text": "exact text snippet where date was found" or null,
    "reasoning": "explanation of why this date was chosen or why none found"
}}

IMPORTANT: Return null for effective_date if you cannot find a clear effective date. Do not guess or infer dates."""

        system_prompt = """You are an expert at extracting effective dates from legal documents. Only return dates that are explicitly stated as effective dates, last updated dates, or similar. Do not guess or infer dates."""

        try:
            async with usage_tracking(self._create_usage_tracker("extract_effective_date")):
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
            content = message.content  # type: ignore
            if not content:
                raise ValueError("Empty response from LLM")

            result = json.loads(content)
            effective_date = result.get("effective_date")

            if effective_date:
                # Validate the date format
                parsed_date = self._parse_date_string(effective_date)
                if parsed_date:
                    logger.debug(
                        f"LLM found effective date: {parsed_date} "
                        f"(confidence: {result.get('confidence', 0):.2f})"
                    )
                    return parsed_date

            logger.debug("LLM could not find effective date")
            return None

        except Exception as e:
            logger.warning(f"LLM effective date extraction failed: {e}")
            return None

    def _parse_date_string(self, date_str: str) -> str | None:
        """
        Parse a date string into ISO format (YYYY-MM-DD).

        Args:
            date_str: Date string to parse

        Returns:
            ISO formatted date string or None if parsing fails
        """
        if not date_str or not isinstance(date_str, str):
            return None

        # Clean up the date string
        date_str = date_str.strip().replace(",", "")

        # Common date formats to try
        formats = [
            "%Y-%m-%d",  # 2023-12-01
            "%m/%d/%Y",  # 12/01/2023
            "%d/%m/%Y",  # 01/12/2023
            "%B %d, %Y",  # December 1, 2023
            "%b %d, %Y",  # Dec 1, 2023
            "%d %B %Y",  # 1 December 2023
            "%d %b %Y",  # 1 Dec 2023
            "%Y-%m-%dT%H:%M:%S",  # ISO with time
            "%Y-%m-%d %H:%M:%S",  # Standard with time
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try to extract year-month-day pattern with regex
        pattern = r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})"
        match = re.search(pattern, date_str)
        if match:
            year, month, day = match.groups()
            try:
                parsed = datetime(int(year), int(month), int(day))
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass

        return None


class LegalDocumentPipeline:
    """
    Main pipeline orchestrator for legal document crawling and processing.

    This class coordinates the entire pipeline from product retrieval to document storage,
    providing comprehensive error handling, logging, and performance monitoring.
    """

    def __init__(
        self,
        max_depth: int = 4,
        max_pages: int = 1000,
        crawler_strategy: str = "bfs",
        concurrent_limit: int = 10,
        delay_between_requests: float = 1.0,
        timeout: int = 30,
        respect_robots_txt: bool = True,
        max_parallel_products: int = 3,
        use_browser: bool = True,
        proxy: str | None = None,
    ):
        """
        Initialize the legal document pipeline.

        Args:
            max_depth: Maximum crawl depth per product
            max_pages: Maximum pages to crawl per product
            crawler_strategy: Crawling strategy ("bfs", "dfs", "best_first")
            concurrent_limit: Maximum concurrent requests
            delay_between_requests: Delay between requests in seconds
            timeout: Request timeout in seconds
            respect_robots_txt: Whether to respect robots.txt
            max_parallel_products: Maximum number of products to process in parallel
            use_browser: Whether to use browser for crawling
            proxy: Optional proxy URL
        """
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.crawler_strategy = crawler_strategy
        self.concurrent_limit = concurrent_limit
        self.delay_between_requests = delay_between_requests
        self.timeout = timeout
        self.respect_robots_txt = respect_robots_txt
        self.max_parallel_products = max_parallel_products
        self.use_browser = use_browser
        self.proxy = proxy

        # Initialize components
        self.analyzer = DocumentAnalyzer()
        self.stats = ProcessingStats()

        logger.info(
            f"Pipeline initialized with max_depth={max_depth}, "
            f"max_pages={max_pages}, strategy={crawler_strategy}"
        )

    def _create_crawler_for_product(self, product: Product) -> ClauseaCrawler:
        """Create a configured crawler instance for a specific product."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{timestamp}_{product.slug}_crawl.log"
        log_file_path = f"logs/{log_filename}"

        return ClauseaCrawler(
            max_depth=self.max_depth,
            max_pages=self.max_pages,
            max_concurrent=self.concurrent_limit,
            delay_between_requests=self.delay_between_requests,
            timeout=self.timeout,
            allowed_domains=product.domains,
            respect_robots_txt=self.respect_robots_txt,
            user_agent="ClauseaCrawler/2.0 (Legal Document Discovery Bot of Clausea)",
            follow_external_links=False,
            min_legal_score=0.0,
            strategy=self.crawler_strategy,
            log_file_path=log_file_path,
            use_browser=self.use_browser,
            proxy=self.proxy,
            allowed_paths=product.crawl_allowed_paths,
            denied_paths=product.crawl_denied_paths,
        )

    async def _store_documents(self, documents: list[Document]) -> int:
        """
        Store documents with intelligent deduplication and update logic.

        Args:
            documents: List of documents to store

        Returns:
            Number of documents actually stored (new + updated)
        """
        stored_count = 0
        updated_count = 0
        duplicate_count = 0
        error_count = 0

        async with get_db() as db:
            document_service = create_document_service()

            for document in documents:
                try:
                    # Check for existing document
                    existing_doc = await document_service.get_document_by_url(db, document.url)
                    if existing_doc:
                        # Calculate content hashes for comparison
                        current_hash = hashlib.sha256(document.text.encode()).hexdigest()
                        existing_hash = hashlib.sha256(existing_doc.text.encode()).hexdigest()

                        if current_hash != existing_hash:
                            # Update existing document with new content
                            logger.info(f"Updating document: {document.url}")
                            document.id = existing_doc.id  # Preserve original ID
                            await document_service.update_document(db, document)
                            stored_count += 1
                            updated_count += 1
                        else:
                            logger.info(
                                f"⏭️ Skipping unchanged document (duplicate): {document.url}"
                            )
                            self.stats.duplicates_skipped += 1
                            duplicate_count += 1
                    else:
                        # Create new document
                        logger.info(f"Creating new document: {document.url}")
                        await document_service.store_document(db, document)
                        stored_count += 1

                except Exception as e:
                    logger.error(f"❌ Failed to store document {document.url}: {e}", exc_info=True)
                    error_count += 1

        # Log summary of storage operation
        if len(documents) > 0:
            logger.info(
                f"📦 Storage summary: {stored_count} stored ({len(documents) - stored_count - error_count} new, "
                f"{updated_count} updated), {duplicate_count} duplicates skipped, {error_count} errors"
            )

        return stored_count

    async def _process_crawl_result(self, result: CrawlResult, product: Product) -> Document | None:
        """
        Process a single crawl result through the analysis pipeline.

        Args:
            result: Crawl result from ClauseaCrawler
            product: Product being processed

        Returns:
            Document if legal and English, None otherwise
        """
        self.analyzer.reset_usage_stats()
        usage_reason = "completed"
        document: Document | None = None

        try:
            # Convert markdown to plain text for analysis
            text_content = markdown_to_text(result.markdown)

            # Classify document first (regardless of language)
            classification = await self.analyzer.classify_document(
                result.url, text_content, result.metadata
            )

            logger.debug(
                f"Classification for {result.url}: {classification.get('classification')} "
                f"(legal: {classification.get('is_legal_document')})"
            )

            # Skip non-legal documents
            if not classification.get("is_legal_document", False):
                logger.debug(f"Skipping non-legal document: {result.url}")
                usage_reason = (
                    f"non-legal classification: {classification.get('classification', 'unknown')}"
                )
                return None

            # Detect locale only for legal documents
            locale_result = await self.analyzer.detect_locale(
                text_content, result.metadata, result.url
            )
            detected_locale = locale_result.get("locale", "en-US")
            language_name = locale_result.get("language_name", "English")

            logger.debug(
                f"Locale detection for {result.url}: {detected_locale} "
                f"({language_name}, confidence: {locale_result.get('confidence', 0):.2f})"
            )

            # Skip non-English documents*
            # TODO: Support other languages
            if "en" not in detected_locale.lower():
                logger.debug(f"Skipping non-English document: {result.url}")
                self.stats.non_english_skipped += 1
                usage_reason = f"non-English locale: {detected_locale}"
                return None

            self.stats.english_documents += 1
            self.stats.legal_documents_processed += 1

            # Detect regions
            region_detection = await self.analyzer.detect_regions(
                text_content, result.metadata, result.url
            )

            # Extract effective date
            effective_date_str = await self.analyzer.extract_effective_date(
                text_content, result.metadata
            )
            effective_date = None
            if effective_date_str:
                try:
                    effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
                    logger.debug(f"Parsed effective date: {effective_date}")
                except ValueError as e:
                    logger.warning(f"Failed to parse effective date '{effective_date_str}': {e}")

            # Extract title
            title_result = await self.analyzer.extract_title(
                result.markdown,
                result.metadata,
                result.url,
                classification.get("classification", "other"),
            )

            # Create document
            document = Document(
                title=title_result.get("title", "Untitled Legal Document"),
                url=result.url,
                product_id=product.id,
                markdown=result.markdown,
                text=text_content,
                metadata=result.metadata,
                doc_type=classification.get("classification", "other"),
                locale=detected_locale,
                regions=region_detection.get("regions", ["global"]),
                effective_date=effective_date,
            )

            effective_date_info = (
                f", effective: {document.effective_date.strftime('%Y-%m-%d')}"
                if document.effective_date
                else ""
            )
            logger.info(
                f"✅ Processed legal document: {document.title} "
                f"({document.doc_type}, {document.locale}, {document.regions}{effective_date_info})"
            )

            usage_reason = "success"
            return document

        except Exception as e:
            usage_reason = f"error: {e.__class__.__name__}"
            logger.error(f"Failed to process crawl result {result.url}: {e}")
            return None
        finally:
            # Extract document info if available (document may not exist if processing failed)
            document_id = document.id if document else None
            document_title = document.title if document else None

            # Get usage summary before it's consumed by log_llm_usage
            usage_summary = self.analyzer.get_usage_summary()

            # Aggregate usage stats for pipeline totals
            for model_stats in usage_summary.values():
                self.stats.total_prompt_tokens += model_stats.get("prompt_tokens", 0)
                self.stats.total_completion_tokens += model_stats.get("completion_tokens", 0)
                self.stats.total_tokens += model_stats.get("total_tokens", 0)
                cost = model_stats.get("cost")
                if cost is not None and cost > 0:
                    self.stats.total_cost += cost

            # Now log the usage (this will consume the summary)
            self.analyzer.log_llm_usage(
                context=result.url,
                reason=usage_reason,
                operation_type="crawl",
                product_slug=product.slug,
                product_id=product.id,
                document_url=result.url,
                document_title=document_title,
                document_id=document_id,
            )

    def _normalize_url(self, url_or_domain: str) -> str:
        """
        Normalize a URL or domain to ensure it has a protocol.

        Args:
            url_or_domain: URL or domain string

        Returns:
            Normalized URL with https:// protocol
        """
        url_or_domain = url_or_domain.strip()
        if not url_or_domain:
            return url_or_domain

        # If already has a protocol, use it as-is
        if url_or_domain.startswith(("http://", "https://")):
            return url_or_domain

        # Prepend https://
        return f"https://{url_or_domain}"

    def _get_crawl_urls(self, product: Product) -> list[str]:
        """
        Get crawl URLs for a product, falling back to domains if crawl_base_urls is empty.

        Args:
            product: Product to get URLs for

        Returns:
            List of URLs to crawl (all normalized with https:// protocol)
        """
        if product.crawl_base_urls:
            # Normalize crawl_base_urls to ensure they have https:// protocol
            return [self._normalize_url(url) for url in product.crawl_base_urls if url.strip()]

        # Fallback to domains if crawl_base_urls is empty
        if not product.domains:
            return []

        # Convert domains to URLs (prepend https:// if not already present)
        urls = []
        for domain in product.domains:
            normalized = self._normalize_url(domain)
            if normalized:
                urls.append(normalized)

        return urls

    async def _process_product(self, product: Product) -> list[Document]:
        """
        Process a single product through the complete pipeline.

        Args:
            product: Product to process

        Returns:
            List of processed and stored documents
        """
        product_start_time = time.time()
        log_memory_usage(f"Starting {product.name}")

        # Get crawl URLs (from crawl_base_urls or fallback to domains)
        crawl_urls = self._get_crawl_urls(product)

        if not crawl_urls:
            logger.warning(
                f"No crawl base URLs or domains for {product.name}. "
                f"Cannot crawl without starting URLs."
            )
            self.stats.products_failed += 1
            self.stats.failed_product_slugs.append(product.slug)
            return []

        # Log whether we're using crawl_base_urls or domains
        using_domains = not product.crawl_base_urls
        source = "domains" if using_domains else "crawl_base_urls"
        try:
            logger.info(
                f"🕷️ Crawling {product.name} ({len(product.domains)} domains) "
                f"from {len(crawl_urls)} base URLs (using {source})"
            )

            # Create crawler and crawl documents
            crawler = self._create_crawler_for_product(product)
            crawl_results = []

            try:
                for base_url in crawl_urls:
                    logger.info(f"Crawling base URL: {base_url}")
                    results = await crawler.crawl(base_url)
                    crawl_results.extend(results)
            finally:
                # Clean up file logging after all base URLs are processed
                crawler._cleanup_file_logging()

            self.stats.total_urls_crawled += len(crawl_results)
            self.stats.total_documents_found += len(crawl_results)

            logger.info(f"📄 Found {len(crawl_results)} documents for {product.name}")

            # Process each crawl result
            processed_documents = []
            for result in crawl_results:
                if result.success:
                    document = await self._process_crawl_result(result, product)
                    if document:
                        processed_documents.append(document)
                else:
                    logger.warning(f"Failed to crawl {result.url}: {result.error_message}")

            # Store processed documents
            if processed_documents:
                stored_count = await self._store_documents(processed_documents)
                self.stats.legal_documents_stored += stored_count
                logger.info(
                    f"💾 Stored {stored_count}/{len(processed_documents)} "
                    f"legal documents for {product.name}"
                )
            else:
                logger.info(f"No legal documents found for {product.name}")

            # Cleanup crawler (specifically browser resources)
            await crawler._cleanup_browser()

            self.stats.products_processed += 1

            product_duration = time.time() - product_start_time
            log_memory_usage(f"Completed {product.name}")
            logger.info(
                f"✅ Completed {product.name} in {product_duration:.2f}s "
                f"({len(processed_documents)} legal docs)"
            )

            return processed_documents

        except Exception as e:
            logger.error(f"Failed to process product {product.name}: {e}")
            self.stats.products_failed += 1
            self.stats.failed_product_slugs.append(product.slug)
            return []

    async def run(self, products: list[Product] | None = None) -> ProcessingStats:
        """
        Execute the complete legal document crawling pipeline.

        Returns:
            ProcessingStats with comprehensive pipeline metrics
        """
        # Start comprehensive monitoring
        tracemalloc.start()
        pipeline_start_time = time.time()

        logger.info("🚀 Starting Legal Document Crawling Pipeline")
        log_memory_usage("Pipeline start")

        # Start background memory monitoring
        memory_task = asyncio.create_task(memory_monitor_task(60))

        try:
            # Get all products
            if products is None:
                async with get_db() as db:
                    product_service = create_product_service()
                    products = await product_service.get_all_products(db)
            logger.info(f"📊 Processing {len(products)} products")

            # Use a semaphore to limit parallel products
            semaphore = asyncio.Semaphore(self.max_parallel_products)

            async def _process_product_with_semaphore(idx: int, product: Product) -> None:
                async with semaphore:
                    logger.info(f"🏢 [{idx}/{len(products)}] Starting product: {product.name}")
                    await self._process_product(product)
                    logger.info(f"✅ [{idx}/{len(products)}] Finished product: {product.name}")

            # Create tasks for all products
            tasks = [
                _process_product_with_semaphore(i, product) for i, product in enumerate(products, 1)
            ]

            # Execute tasks in parallel with limited concurrency
            await asyncio.gather(*tasks)

            # Calculate final statistics
            self.stats.processing_time_seconds = time.time() - pipeline_start_time

            # Log comprehensive results
            logger.info("🎉 Pipeline completed successfully!")
            logger.info(f"📊 Products processed: {self.stats.products_processed}")
            logger.info(f"❌ Products failed: {self.stats.products_failed}")
            if self.stats.failed_product_slugs:
                logger.info(
                    f"❌ Failed product slugs: {', '.join(self.stats.failed_product_slugs)}"
                )
            logger.info(f"🌐 Total URLs crawled: {self.stats.total_urls_crawled}")
            logger.info(f"📄 Total documents found: {self.stats.total_documents_found}")
            logger.info(f"⚖️ Legal documents processed: {self.stats.legal_documents_processed}")
            logger.info(f"💾 Legal documents stored: {self.stats.legal_documents_stored}")
            logger.info(f"🗣️ English documents: {self.stats.english_documents}")
            logger.info(f"🌍 Non-English skipped: {self.stats.non_english_skipped}")
            logger.info(f"🔄 Duplicates skipped: {self.stats.duplicates_skipped}")
            logger.info(f"✅ Success rate: {self.stats.success_rate:.1f}%")
            logger.info(f"🎯 Legal detection rate: {self.stats.legal_detection_rate:.1f}%")
            # Format time as minutes or hours + minutes
            total_seconds = self.stats.processing_time_seconds
            if total_seconds >= 3600:
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                time_str = f"{hours}h {minutes}m"
            else:
                minutes = int(total_seconds // 60)
                seconds = int(total_seconds % 60)
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            logger.info(f"⏱️ Total time: {time_str}")

            # Log LLM token usage and cost
            if self.stats.total_tokens > 0:
                cost_str = f" (${self.stats.total_cost:.6f})" if self.stats.total_cost > 0 else ""
                logger.info(
                    f"🔢 LLM tokens: input={self.stats.total_prompt_tokens:,} "
                    f"output={self.stats.total_completion_tokens:,} "
                    f"total={self.stats.total_tokens:,}{cost_str}"
                )

            return self.stats

        finally:
            # Cleanup and final monitoring
            memory_task.cancel()
            log_memory_usage("Pipeline end")

            current, peak = tracemalloc.get_traced_memory()
            logger.info(
                f"🧠 Memory usage: Current={current / 1024 / 1024:.1f}MB, "
                f"Peak={peak / 1024 / 1024:.1f}MB"
            )
            tracemalloc.stop()


async def main() -> None:
    """Main entry point for the crawling pipeline."""
    try:
        pipeline = LegalDocumentPipeline(
            max_depth=4,
            max_pages=1000,
            crawler_strategy="bfs",
            concurrent_limit=10,
            delay_between_requests=1.0,
        )

        stats = await pipeline.run()

        # Exit with appropriate code
        if stats.products_failed > 0:
            failed_slugs = (
                ", ".join(stats.failed_product_slugs) if stats.failed_product_slugs else "unknown"
            )
            logger.warning(
                f"Pipeline completed with {stats.products_failed} failures: {failed_slugs}"
            )
        else:
            logger.info("Pipeline completed successfully")
        exit(0)

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        exit(130)
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
