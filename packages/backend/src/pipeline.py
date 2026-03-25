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
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.analyzers.date_extractor import DateExtractor
from src.analyzers.document_classifier import DocumentClassifier
from src.analyzers.locale_analyzer import LocaleAnalyzer
from src.analyzers.region_detector import RegionDetector
from src.core.database import db_session
from src.core.logging import get_logger
from src.crawler import ClauseaCrawler, CrawlResult
from src.llm import SupportedModel, acompletion_with_fallback
from src.models.crawl import CrawlSession
from src.models.document import Document
from src.models.pipeline_job import classify_crawl_error
from src.models.product import Product
from src.repositories.crawl_repository import CrawlRepository
from src.services.service_factory import create_document_service, create_product_service
from src.utils.llm_usage import usage_tracking
from src.utils.llm_usage_tracking_mixin import LLMUsageTrackingMixin
from src.utils.markdown import markdown_to_text
from src.utils.perf import log_memory_usage, memory_monitor_task

load_dotenv()

logger = get_logger(__name__)
logger_discovery = get_logger(__name__, component="pipeline:discovery")
logger_analysis = get_logger(__name__, component="pipeline:analysis")
logger_storage = get_logger(__name__, component="pipeline:storage")


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

    # Per-URL crawl failures collected during the pipeline run
    crawl_errors: list[dict[str, Any]] = Field(default_factory=list)

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

        # Initialize specialized analyzers

        self.locale_analyzer = LocaleAnalyzer()
        self.document_classifier = DocumentClassifier(max_content_length=max_content_length)
        self.region_detector = RegionDetector()
        self.date_extractor = DateExtractor()

    def reset_usage_stats(self) -> None:
        """Clear recorded LLM usage statistics across all analyzers."""
        super().reset_usage_stats()
        self.locale_analyzer.reset_usage_stats()
        self.document_classifier.reset_usage_stats()
        self.date_extractor.reset_usage_stats()

    def get_usage_summary(self) -> dict[str, dict[str, Any]]:
        """Aggregate token usage from all analyzers without clearing records."""
        summary = super().get_usage_summary()
        for analyzer in (self.locale_analyzer, self.document_classifier, self.date_extractor):
            summary = self._merge_usage_summary(summary, analyzer.get_usage_summary())
        return summary

    def consume_usage_summary(self) -> tuple[dict[str, dict[str, Any]], list[Any]]:
        """Return aggregated usage information and clear recorded statistics."""
        summary, records = super().consume_usage_summary()
        for analyzer in (self.locale_analyzer, self.document_classifier, self.date_extractor):
            analyzer_summary, analyzer_records = analyzer.consume_usage_summary()
            summary = self._merge_usage_summary(summary, analyzer_summary)
            records.extend(analyzer_records)
        return summary, records

    def _merge_usage_summary(
        self, base: dict[str, dict[str, Any]], incoming: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        for model, stats in incoming.items():
            entry = base.setdefault(
                model,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "provider_models": [],
                },
            )
            entry["prompt_tokens"] += stats.get("prompt_tokens", 0)
            entry["completion_tokens"] += stats.get("completion_tokens", 0)
            entry["total_tokens"] += stats.get("total_tokens", 0)
            if stats.get("cost"):
                entry["cost"] = (entry.get("cost", 0.0) or 0.0) + stats.get("cost", 0.0)

            providers = set(entry.get("provider_models") or [])
            providers.update(stats.get("provider_models") or [])
            entry["provider_models"] = sorted(providers)

        return base

    async def detect_locale(
        self, text: str, metadata: dict[str, Any], url: str | None = None
    ) -> dict[str, Any]:
        """
        Detect the locale of a document.

        Delegates to the specialized LocaleAnalyzer.

        Args:
            text: Document content
            metadata: Document metadata
            url: Optional document URL for pattern analysis

        Returns:
            Dict containing locale, confidence, and language_name
        """
        return await self.locale_analyzer.detect_locale(text, metadata, url)

    async def classify_document(
        self, url: str, text: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Classify if document is a legal document and determine its type.

        Delegates to the specialized DocumentClassifier.

        Args:
            url: Document URL
            text: Document content
            metadata: Document metadata

        Returns:
            Dict containing classification, justification, and is_legal_document flag
        """
        return await self.document_classifier.classify_document(url, text, metadata)

    async def detect_regions(self, text: str, metadata: dict[str, Any], url: str) -> dict[str, Any]:
        """
        Detect if document applies globally or to specific regions.

        Delegates to the specialized RegionDetector.

        Args:
            text: Document content
            metadata: Document metadata
            url: Document URL

        Returns:
            Dict containing region analysis with mapped region codes
        """
        return await self.region_detector.detect_regions(text, metadata, url)

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

        Args:
            content: Document text content
            metadata: Document metadata

        Returns:
            Effective date as ISO string (YYYY-MM-DD) or None if not found
        """
        return await self.date_extractor.extract_effective_date(content, metadata)

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
            r"last\s+(?:updated|modified|revised|reviewed):?\s*([^.\n<]+)",
            # "Updated on:" or "Modified on:"
            r"(?:updated|modified|revised)\s+on:?\s*([^.\n<]+)",
            # "Revision date:" or "Version date:"
            r"(?:revision|version)\s+date:?\s*([^.\n<]+)",
            # "This policy is effective..." or "This agreement takes effect..."
            r"(?:this\s+(?:policy|agreement|document|terms?|privacy|cookie)\s+)?(?:is\s+)?(?:effective|takes\s+effect|became\s+effective)\s+(?:as\s+of\s+)?([^.\n<]+)",
            # "Effective:" standalone
            r"effective:?\s*([^.\n<]+)",
            # "Date of effect:" or "Date effective:"
            r"date\s+(?:of\s+effect|effective):?\s*([^.\n<]+)",
            # "Published:" or "Publication date:"
            r"(?:publication|publish)\s+date:?\s*([^.\n<]+)",
            # "Posted:" or "Posted on:"
            r"(?:posted|post)\s+(?:on|date)?:?\s*([^.\n<]+)",
            # "Created:" or "Creation date:"
            r"(?:creation|created?)\s+date:?\s*([^.\n<]+)",
            # ISO date format in context (YYYY-MM-DD)
            r"(?:effective|updated|modified|published|posted|created).*?(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            # US/European numeric date format (MM/DD/YYYY or DD/MM/YYYY)
            r"(?:effective|updated|modified|published).*?(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            # Full month names
            r"(?:effective|updated|modified|published).*?((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
            # Abbreviated month names
            r"(?:effective|updated).*?((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[\s\.]\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
            # Relative dates (for fallback, but try to convert to actual dates)
            r"effective\s+immediately",
            r"effective\s+upon\s+(?:publication|posting|acceptance)",
            r"effective\s+(?:from|as\s+of)\s+(?:the\s+)?date\s+(?:of|this)",
            # Date ranges (take the start date)
            r"effective\s+(?:from|between)\s+([^.\n<]+?)(?:\s+(?:to|through|until)\s+[^.\n<]+)",
            r"effective\s+([^.\n<]+?)\s+through\s+([^.\n<]+)",  # Capture first date
            # International date formats
            r"(?:effective|updated).*?(\d{1,2}\.\d{1,2}\.\d{4})",  # DD.MM.YYYY (German)
            r"(?:effective|updated).*?(\d{4}年\d{1,2}月\d{1,2}日)",  # YYYY年MM月DD日 (Japanese)
            # Ordinal indicators
            r"(?:effective|updated).*?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\s+(?:of\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december),?\s+\d{4}",
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

        Enhanced to handle more formats, ordinal indicators, and international variations.

        Args:
            date_str: Date string to parse

        Returns:
            ISO formatted date string or None if parsing fails
        """
        if not date_str or not isinstance(date_str, str):
            return None

        # Clean up the date string
        date_str = date_str.strip().replace(",", "").replace(".", "").lower()

        # Handle relative dates (return None as they're not specific dates)
        if any(
            word in date_str for word in ["immediately", "upon", "as of the date", "as of this"]
        ):
            return None

        # Handle ordinal indicators (convert to cardinal numbers)
        ordinals = {
            "first": "1",
            "1st": "1",
            "second": "2",
            "2nd": "2",
            "third": "3",
            "3rd": "3",
            "fourth": "4",
            "4th": "4",
            "fifth": "5",
            "5th": "5",
            "sixth": "6",
            "6th": "6",
            "seventh": "7",
            "7th": "7",
            "eighth": "8",
            "8th": "8",
            "ninth": "9",
            "9th": "9",
            "tenth": "10",
            "10th": "10",
        }
        for ordinal, number in ordinals.items():
            date_str = date_str.replace(ordinal, number)

        # Extended date formats to try
        formats = [
            # ISO and standard formats
            "%Y-%m-%d",  # 2023-12-01
            "%Y/%m/%d",  # 2023/12/01
            "%m/%d/%Y",  # 12/01/2023
            "%d/%m/%Y",  # 01/12/2023
            "%d.%m.%Y",  # 01.12.2023 (German style)
            # Full month names
            "%B %d %Y",  # December 1 2023
            "%b %d %Y",  # Dec 1 2023
            "%d %B %Y",  # 1 December 2023
            "%d %b %Y",  # 1 Dec 2023
            # With commas and periods
            "%B %d, %Y",  # December 1, 2023
            "%b %d, %Y",  # Dec 1, 2023
            # ISO with time components
            "%Y-%m-%dT%H:%M:%S",  # ISO with time
            "%Y-%m-%d %H:%M:%S",  # Standard with time
            "%Y-%m-%dT%H:%M:%SZ",  # ISO with timezone
            # Japanese format
            "%Y年%m月%d日",  # 2023年12月1日
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try to extract various year-month-day patterns with regex
        patterns = [
            r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",  # YYYY-MM-DD or YYYY/MM/DD
            r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",  # MM/DD/YYYY or DD/MM/YYYY (ambiguous)
        ]

        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                groups = match.groups()
                if len(groups[0]) == 4:  # YYYY-MM-DD format
                    year, month, day = groups
                else:  # Assume MM/DD/YYYY for US-centric parsing
                    month, day, year = groups

                try:
                    parsed = datetime(int(year), int(month), int(day))
                    return parsed.strftime("%Y-%m-%d")
                except ValueError:
                    continue

        # Try to parse month name + day + year
        month_names = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }

        # Pattern: month day, year or month day year
        month_day_year_pattern = (
            r"(" + "|".join(month_names.keys()) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"
        )
        match = re.search(month_day_year_pattern, date_str, re.IGNORECASE)
        if match:
            month_name, day, year = match.groups()
            month = month_names[month_name.lower()]
            try:
                parsed = datetime(int(year), month, int(day))
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
        max_depth: int | None = None,
        max_pages: int | None = None,
        crawler_strategy: str = "bfs",
        concurrent_limit: int | None = None,
        delay_between_requests: float = 1.0,
        timeout: int = 30,
        respect_robots_txt: bool = True,
        max_parallel_products: int = 3,
        use_browser: bool = True,
        proxy: str | None = None,
        discovery_max_depth: int | None = None,
        discovery_max_pages: int | None = None,
        fallback_max_depth: int | None = None,
        fallback_max_pages: int | None = None,
        fallback_min_legal_score: float = 1.5,
        min_docs_before_fallback: int = 2,
        required_doc_types: list[str] | None = None,
        progress_callback: Callable[[str, int, int], None]
        | Callable[[str, int, int], Awaitable[None]]
        | None = None,  # Optional progress callback (phase, current, total)
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
            discovery_max_depth: Max depth for discovery pass
            discovery_max_pages: Max pages for discovery pass
            fallback_max_depth: Max depth for fallback crawl
            fallback_max_pages: Max pages for fallback crawl
            fallback_min_legal_score: Min legal score for fallback crawl
            min_docs_before_fallback: Minimum legal docs before skipping fallback
            required_doc_types: Required document types before skipping fallback
        """
        from src.core.config import config

        self.max_depth = max_depth or config.crawler.max_depth
        self.max_pages = max_pages or config.crawler.max_pages
        self.crawler_strategy = crawler_strategy
        self.concurrent_limit = concurrent_limit or config.crawler.concurrent_limit
        self.delay_between_requests = delay_between_requests
        self.timeout = timeout
        self.respect_robots_txt = respect_robots_txt
        self.max_parallel_products = max_parallel_products
        self.use_browser = use_browser
        self.proxy = proxy
        self.discovery_max_depth = discovery_max_depth or config.crawler.discovery_max_depth
        self.discovery_max_pages = discovery_max_pages or config.crawler.discovery_max_pages
        self.fallback_max_depth = fallback_max_depth or self.max_depth
        self.fallback_max_pages = fallback_max_pages or self.max_pages
        self.fallback_min_legal_score = fallback_min_legal_score
        self.min_docs_before_fallback = min_docs_before_fallback
        self.required_doc_types = required_doc_types or [
            "privacy_policy",
            "terms_of_service",
        ]
        self.progress_callback: (
            Callable[[str, int, int], None] | Callable[[str, int, int], Awaitable[None]] | None
        ) = progress_callback
        self._pending_progress_tasks: list[asyncio.Task] = []

        # Initialize components
        self.analyzer = DocumentAnalyzer()
        self.stats = ProcessingStats()

        logger.info(
            f"Pipeline initialized with max_depth={self.max_depth}, "
            f"max_pages={self.max_pages}, strategy={crawler_strategy}"
        )

    def _create_crawler_for_product(
        self,
        product: Product,
        *,
        max_depth: int | None = None,
        max_pages: int | None = None,
        min_legal_score: float | None = None,
        strategy: str | None = None,
        progress_phase: str | None = None,
    ) -> ClauseaCrawler:
        """Create a configured crawler instance for a specific product."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{timestamp}_{product.slug}_crawl.log"
        log_file_path = f"logs/{log_filename}"

        # Create progress callback that forwards to pipeline callback with phase
        progress_callback = None
        if self.progress_callback and progress_phase:

            def progress_callback(current: int, total: int) -> None:
                # Handle both sync and async callbacks
                assert self.progress_callback is not None  # Guaranteed by outer condition
                callback_result = self.progress_callback(progress_phase, current, total)
                if callback_result is not None:
                    # Track the task to ensure it's awaited before the pipeline finishes
                    async def _wrap():
                        await callback_result

                    task = asyncio.create_task(_wrap())
                    self._pending_progress_tasks.append(task)

        from src.core.config import config

        return ClauseaCrawler(
            max_depth=max_depth or self.max_depth,
            max_pages=max_pages or self.max_pages,
            max_concurrent=self.concurrent_limit,
            delay_between_requests=self.delay_between_requests,
            delay_jitter=config.crawler.rate_limit_jitter,
            timeout=self.timeout,
            allowed_domains=product.domains,
            respect_robots_txt=self.respect_robots_txt,
            user_agent="ClauseaCrawler/2.0 (Legal Document Discovery Bot of Clausea)",
            follow_external_links=False,
            min_legal_score=min_legal_score if min_legal_score is not None else 0.0,
            strategy=strategy or self.crawler_strategy,
            log_file_path=log_file_path,
            use_browser=self.use_browser,
            proxy=self.proxy,
            allowed_paths=product.crawl_allowed_paths,
            denied_paths=product.crawl_denied_paths,
            progress_callback=progress_callback,
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

        async with db_session() as db:
            document_service = create_document_service()

            for document in documents:
                try:
                    # Check for existing document
                    existing_doc = await document_service.get_document_by_url(db, document.url)
                    if existing_doc:
                        # Calculate content + metadata hashes for comparison
                        # We include metadata that the LLM might have updated (title, doc_type, locale, regions, effective_date)
                        # We use separators to avoid potential string collisions
                        metadata_str = f"|{document.title}|{document.doc_type}|{document.locale}|{','.join(document.regions)}|{document.effective_date}|"
                        current_hash = hashlib.sha256(
                            (document.text + metadata_str).encode()
                        ).hexdigest()

                        existing_metadata_str = f"|{existing_doc.title}|{existing_doc.doc_type}|{existing_doc.locale}|{','.join(existing_doc.regions)}|{existing_doc.effective_date}|"
                        existing_hash = hashlib.sha256(
                            (existing_doc.text + existing_metadata_str).encode()
                        ).hexdigest()

                        if current_hash != existing_hash:
                            # Update existing document with new content/metadata
                            logger_storage.info(
                                f"updating existing document with changes: {document.url}"
                            )
                            document.id = existing_doc.id  # Preserve original ID
                            await document_service.update_document(db, document)
                            stored_count += 1
                            updated_count += 1
                        else:
                            logger_storage.debug(
                                f"skipping unchanged document (duplicate): {document.url}"
                            )
                            self.stats.duplicates_skipped += 1
                            duplicate_count += 1
                    else:
                        # Create new document
                        logger_storage.info(f"storing new document: {document.url}")
                        await document_service.store_document(db, document)
                        stored_count += 1

                except Exception as e:
                    logger_storage.error(
                        f"failed to store document {document.url}: {e}", exc_info=True
                    )
                    error_count += 1

        # Log summary of storage operation
        if len(documents) > 0:
            logger_storage.info(
                f"storage complete: {stored_count} stored ({stored_count - updated_count} new, {updated_count} updated), {duplicate_count} duplicates skipped, {error_count} errors"
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
            text_content = markdown_to_text(result.markdown)

            # Skip empty or very short content without wasting LLM calls
            if not text_content or len(text_content.strip()) < 100:
                logger_analysis.debug(f"skipping document with insufficient content: {result.url}")
                return None

            # Skip garbled/binary content that slipped through
            if ClauseaCrawler._is_garbled_content(text_content):
                logger_analysis.debug(
                    f"skipping document with garbled/binary content: {result.url}"
                )
                return None

            # Always classify before storing; skip non-legal and get proper title
            classification = await self.analyzer.classify_document(
                result.url, text_content, result.metadata
            )

            logger_analysis.debug(
                f"classified as '{classification.get('classification')}' (is_legal: {classification.get('is_legal_document')})"
            )

            # Skip non-legal documents
            if not classification.get("is_legal_document", False):
                logger_analysis.debug(f"skipping non-legal document: {result.url}")
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

            logger_analysis.debug(
                f"detected locale: {detected_locale} ({language_name}, confidence: {locale_result.get('confidence', 0):.2f})"
            )

            # Skip non-English documents*
            # TODO: Support other languages
            if "en" not in detected_locale.lower():
                logger_analysis.debug(
                    f"skipping non-English document ({detected_locale}): {result.url}"
                )
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
            logger_analysis.info(
                f"analyzed document: '{document.title}' ({document.doc_type}, {document.locale}, {document.regions}{effective_date_info})"
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

    async def _start_crawl_session(self, product: Product, crawl_urls: list[str]) -> CrawlSession:
        session = CrawlSession(
            product_id=product.id,
            product_slug=product.slug,
            seed_urls=crawl_urls,
            status="running",
            settings={
                "discovery_max_depth": self.discovery_max_depth,
                "discovery_max_pages": self.discovery_max_pages,
                "fallback_max_depth": self.fallback_max_depth,
                "fallback_max_pages": self.fallback_max_pages,
                "strategy": self.crawler_strategy,
            },
            stats={"mode": "hybrid"},
        )
        async with db_session() as db:
            repo = CrawlRepository()
            await repo.create_session(db, session)
        return session

    async def _finish_crawl_session(
        self, session: CrawlSession, stats: dict[str, int], error: str | None = None
    ) -> None:
        session.stats.update(stats)
        session.status = "failed" if error else "completed"
        session.error = error
        session.completed_at = datetime.now()
        async with db_session() as db:
            repo = CrawlRepository()
            await repo.update_session(db, session)

    def _should_fallback_crawl(self, documents: list[Document]) -> bool:
        if len(documents) < self.min_docs_before_fallback:
            return True
        doc_types = {doc.doc_type for doc in documents}
        return not all(req in doc_types for req in self.required_doc_types)

    async def _classify_results(
        self,
        results: list[CrawlResult],
        product: Product,
        processed_urls: set[str],
    ) -> list[Document]:
        """Classify a batch of crawl results and return legal documents.

        Mutates *processed_urls* to track deduplication across calls.
        Failed crawl results are collected in ``self.stats.crawl_errors``.
        """
        documents: list[Document] = []
        for result in results:
            if result.url in processed_urls:
                continue
            processed_urls.add(result.url)
            if result.success:
                document = await self._process_crawl_result(result, product)
                if document:
                    documents.append(document)
            else:
                logger.warning(f"Failed to crawl {result.url}: {result.error_message}")
                self.stats.crawl_errors.append(
                    {
                        "url": result.url,
                        "status_code": result.status_code,
                        "error_message": result.error_message,
                        "error_type": classify_crawl_error(
                            result.error_message, result.status_code
                        ),
                    }
                )
        return documents

    async def _crawl_base_urls(
        self, crawler: ClauseaCrawler, crawl_urls: list[str]
    ) -> list[CrawlResult]:
        results: list[CrawlResult] = []
        try:
            for base_url in crawl_urls:
                logger.info(f"Crawling base URL: {base_url}")
                results.extend(await crawler.crawl(base_url))
        finally:
            crawler._cleanup_file_logging()
            await crawler._cleanup_browser()
        return results

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
        crawl_session: CrawlSession | None = None
        try:
            logger.info(
                f"🕷️ Crawling {product.name} ({len(product.domains)} domains) "
                f"from {len(crawl_urls)} base URLs (using {source})"
            )

            # Create crawl session for auditability
            crawl_session = await self._start_crawl_session(product, crawl_urls)

            processed_urls: set[str] = set()
            total_results = 0

            # ----------------------------------------------------------
            # Stage 1: Crawl (pure fetching, no classification)
            # ----------------------------------------------------------

            # Discovery pass (precision-first)
            logger_discovery.info(
                f"starting discovery pass for '{product.name}' (max_depth={self.discovery_max_depth}, max_pages={self.discovery_max_pages})"
            )
            discovery_crawler = self._create_crawler_for_product(
                product,
                max_depth=self.discovery_max_depth,
                max_pages=self.discovery_max_pages,
                min_legal_score=2.5,
                strategy="best_first",
                progress_phase="discovery",
            )
            discovery_results = await self._crawl_base_urls(discovery_crawler, crawl_urls)
            logger_discovery.info(
                f"discovery pass complete for '{product.name}': found {len(discovery_results)} pages"
            )
            total_results += len(discovery_results)

            # ----------------------------------------------------------
            # Stage 2: Classify + Score
            # ----------------------------------------------------------

            processed_documents = await self._classify_results(
                discovery_results, product, processed_urls
            )

            # Fallback deep crawl (recall-first) if coverage is low
            if self._should_fallback_crawl(processed_documents):
                logger_discovery.info(
                    f"discovery coverage insufficient for '{product.name}'; starting fallback deep crawl (max_depth={self.fallback_max_depth}, max_pages={self.fallback_max_pages})"
                )
                fallback_crawler = self._create_crawler_for_product(
                    product,
                    max_depth=self.fallback_max_depth,
                    max_pages=self.fallback_max_pages,
                    min_legal_score=self.fallback_min_legal_score,
                    strategy="bfs",
                    progress_phase="fallback",
                )
                fallback_results = await self._crawl_base_urls(fallback_crawler, crawl_urls)
                logger_discovery.info(
                    f"fallback pass complete for '{product.name}': found {len(fallback_results)} pages"
                )
                total_results += len(fallback_results)

                fallback_docs = await self._classify_results(
                    fallback_results, product, processed_urls
                )
                processed_documents.extend(fallback_docs)

            self.stats.total_urls_crawled += total_results
            self.stats.total_documents_found += total_results

            logger.info(f"📄 Found {total_results} pages for {product.name}")

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

            await self._finish_crawl_session(
                crawl_session,
                stats={
                    "pages_crawled": total_results,
                    "legal_documents": len(processed_documents),
                },
            )

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
            if crawl_session:
                await self._finish_crawl_session(
                    crawl_session, stats={"pages_crawled": 0, "legal_documents": 0}, error=str(e)
                )
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
                async with db_session() as db:
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

            # Ensure all progress callbacks are finished before returning
            if self._pending_progress_tasks:
                await asyncio.gather(*self._pending_progress_tasks, return_exceptions=True)
                self._pending_progress_tasks.clear()

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
