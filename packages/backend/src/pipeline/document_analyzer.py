"""AI-powered document analysis: locale detection, legal classification, date extraction, and region analysis.

**What it does**
After the crawler returns a ``CrawlResult``, ``DocumentAnalyzer`` runs four
analyses in sequence, each calling an LLM-backed analyzer:
1. ``LocaleAnalyzer`` — detects the document language (en/fr/de/…).
2. ``DocumentClassifier`` — classifies the document type (privacy policy,
   terms of service, cookie policy, etc.).
3. ``DateExtractor`` — extracts effective/last-updated dates from the text.
4. ``RegionDetector`` — determines which legal regimes apply (GDPR, CCPA, LGPD, …).

**What it contains**
- ``DocumentAnalyzer`` class that holds references to all four analyzer singletons.
- ``analyze(crawl_result) -> dict``: runs all four analyzers, returns combined
  analysis dict with confidence scores.

**What it allows/prevents**
Allows the pipeline to enrich crawl results with semantic metadata before
storage.  Prevents non-English documents from being processed with wrong
locale assumptions and prevents misclassification of document type (critical
for choosing the right extraction clusters).
"""

import re
from datetime import datetime
from typing import Any

from src.analyzers.date_extractor import DateExtractor
from src.analyzers.document_classifier import DocumentClassifier
from src.analyzers.locale_analyzer import LocaleAnalyzer
from src.analyzers.region_detector import RegionDetector
from src.core.logging import get_logger
from src.llm import SupportedModel, acompletion_with_fallback
from src.utils.llm_usage_tracking_mixin import LLMUsageTrackingMixin

logger = get_logger(__name__)


class DocumentAnalyzer(LLMUsageTrackingMixin):
    def __init__(
        self,
        model_name: SupportedModel | None = None,
        max_content_length: int = 5000,
    ):
        super().__init__()
        self.model_name = model_name
        self.max_content_length = max_content_length

        self.locale_analyzer = LocaleAnalyzer()
        self.document_classifier: DocumentClassifier = DocumentClassifier(
            max_content_length=max_content_length
        )
        self.region_detector = RegionDetector()
        self.date_extractor = DateExtractor()

    def reset_usage_stats(self) -> None:
        super().reset_usage_stats()
        self.locale_analyzer.reset_usage_stats()
        self.document_classifier.reset_usage_stats()
        self.date_extractor.reset_usage_stats()

    def get_usage_summary(self) -> dict[str, dict[str, Any]]:
        summary = super().get_usage_summary()
        for analyzer in (self.locale_analyzer, self.document_classifier, self.date_extractor):
            summary = self._merge_usage_summary(summary, analyzer.get_usage_summary())
        return summary

    def consume_usage_summary(self) -> tuple[dict[str, dict[str, Any]], list[Any]]:
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
        return await self.locale_analyzer.detect_locale(text, metadata, url)

    async def classify_document(
        self, url: str, text: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.document_classifier.classify_document(url, text, metadata)

    async def detect_regions(
        self, text: str, metadata: dict[str, Any], url: str | None = None
    ) -> dict[str, Any]:
        return await self.region_detector.detect_regions(text, metadata, url or "")

    async def extract_title(
        self, markdown: str, metadata: dict[str, Any], url: str, doc_type: str
    ) -> dict[str, Any]:
        title: str | None = None
        source = "metadata"
        title = metadata.get("title") or metadata.get("og:title") or metadata.get("twitter:title")
        if title:
            cleaned = re.sub(r"\s+", " ", title).strip()
            if cleaned:
                logger.debug(f"extracted title from metadata: '{cleaned}'")
                return {"title": cleaned, "source": source, "confidence": 0.9}

        title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if title_match:
            cleaned = re.sub(r"\s+", " ", title_match.group(1)).strip()
            if cleaned:
                source = "markdown_header"
                logger.debug(f"extracted title from markdown: '{cleaned}'")
                return {"title": cleaned, "source": source, "confidence": 0.8}

        from urllib.parse import urlparse as _urlparse

        parsed = _urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            title = path_parts[-1].replace("-", " ").replace("_", " ").title()
        else:
            title = parsed.netloc.replace("www.", "").split(".")[0].title()
        title = f"{title} — {doc_type.replace('_', ' ').title()}"
        source = "url_fallback"
        logger.debug(f"extracted title from fallback: '{title}'")
        return {"title": title, "source": source, "confidence": 0.5}

    async def extract_effective_date(self, content: str, metadata: dict[str, Any]) -> str | None:
        result = await self._extract_effective_date_static(content, metadata)
        if result:
            return result
        return await self._extract_effective_date_llm(content, metadata)

    async def _extract_effective_date_static(
        self, content: str, metadata: dict[str, Any]
    ) -> str | None:
        import re as _re

        metadata_date = (
            metadata.get("date")
            or metadata.get("published_date")
            or metadata.get("last_modified")
            or metadata.get("effective_date")
        )
        if metadata_date:
            parsed = self._parse_date_string(str(metadata_date))
            if parsed:
                return parsed

        prefixes = [
            r"effective\s+date",
            r"last\s+updated",
            r"last\s+modified",
            r"updated",
            r"revised",
            r"version\s+date",
            r"policy\s+date",
            r"date\s+of\s+last\s+(?:revision|update|modification)",
            r"this\s+(?:policy|agreement)\s+was\s+last\s+(?:updated|modified|revised)",
            r"these\s+terms\s+were\s+last\s+(?:updated|modified|revised)",
        ]
        date_patterns = [
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+\d{4}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{2}/\d{2}/\d{4}\b",
            r"\b\d{4}/\d{2}/\d{2}\b",
        ]

        for prefix in prefixes:
            for date_pat in date_patterns:
                pattern = rf"(?i:{prefix}).{{0,60}}?({date_pat})"
                match = _re.search(pattern, content[:3000])
                if match:
                    parsed = self._parse_date_string(match.group(1))
                    if parsed:
                        return parsed
        return None

    async def _extract_effective_date_llm(
        self, content: str, metadata: dict[str, Any]
    ) -> str | None:
        system_prompt = """You are a precise date extractor. Your task is to find the effective date,
last updated date, or last modified date in the provided policy document text.

Rules:
1. Return ONLY the date in YYYY-MM-DD format
2. If no date is found, return "null"
3. Prioritize: effective date > last updated > last modified > published date
4. Look for dates in headers, footers, and introductory paragraphs first
5. Be thorough — check multiple locations in the text"""

        text_sample = content[: min(len(content), self.max_content_length)]

        user_prompt = f"""Find the effective date or last updated date in this policy document.

Document URL: {metadata.get("url", "unknown")}
Document type: {metadata.get("doc_type", "unknown")}

Text:
{text_sample}

Return only the date in YYYY-MM-DD format, or "null" if no date is found."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await acompletion_with_fallback(
                messages,
                model_priority=[self.model_name] if self.model_name else None,
            )
            content: str | None = response.choices[0].message.content
            if content:
                content = content.strip()
                if content.lower() != "null":
                    parsed = self._parse_date_string(content)
                    if parsed:
                        logger.debug(f"extracted effective date via LLM: {parsed}")
                        return parsed
        except Exception as e:
            logger.debug(f"LLM date extraction failed: {e}")
        return None

    def _parse_date_string(self, date_str: str) -> str | None:
        date_str = date_str.strip().strip(".,;:)")
        if not date_str:
            return None

        # Remove ordinal suffixes
        date_str = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", date_str)

        # Normalize whitespace
        date_str = re.sub(r"\s+", " ", date_str)

        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%B %d %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%b %d %Y",
            "%d %b %Y",
            "%B %d,%Y",
            "%b %d,%Y",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.year < 2000 or parsed.year > 2030:
                    continue
                if parsed <= datetime.now():
                    return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try parsing just the year
        year_match = re.search(r"\b(20\d{2})\b", date_str)
        if year_match:
            year = int(year_match.group(1))
            if 2000 <= year <= 2030:
                return f"{year}-01-01"

        return None


__all__ = ["DocumentAnalyzer"]
