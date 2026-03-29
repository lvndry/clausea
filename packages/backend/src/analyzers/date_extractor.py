"""
Date Extraction Analyzer

Specialized analyzer for extracting effective dates from policy documents through
static pattern matching and LLM fallback analysis.
"""

import json
import re
from datetime import datetime
from typing import Any

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.utils.llm_usage import usage_tracking
from src.utils.llm_usage_tracking_mixin import LLMUsageTrackingMixin

logger = get_logger(__name__, component="date extraction")


class DateExtractor(LLMUsageTrackingMixin):
    """
    AI-powered date extractor for policy document effective dates.

    Uses a multi-layered approach prioritizing speed and accuracy:
    1. Metadata extraction (fastest)
    2. Static pattern matching with comprehensive regex
    3. LLM analysis (fallback)
    """

    def __init__(self):
        super().__init__()

        # Comprehensive date patterns for policy documents
        self.date_patterns = [
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

        # Ordinal indicators mapping
        self.ordinals = {
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

        # Extended date formats to try
        self.date_formats = [
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

        # Month names mapping
        self.month_names = {
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

    async def extract_effective_date(self, content: str, metadata: dict[str, Any]) -> str | None:
        """
        Extract the effective date from a policy document.

        First attempts static extraction from metadata and common patterns,
        then falls back to LLM analysis if needed.

        Args:
            content: Document text content
            metadata: Document metadata

        Returns:
            Effective date as ISO string (YYYY-MM-DD) or None if not found
        """

        # Try static extraction first
        effective_date = self._extract_effective_date_static(content, metadata)
        if effective_date:
            logger.debug(f"extracted effective date via pattern matching: {effective_date}")
            return effective_date

        # Fall back to LLM analysis
        logger.debug("pattern matching failed to find date; invoking LLM for extraction")
        return await self._extract_effective_date_llm(content, metadata)

    def _extract_effective_date_static(self, content: str, metadata: dict[str, Any]) -> str | None:
        """
        Attempt static extraction of effective date from metadata and content patterns.

        Args:
            content: Document text content
            metadata: Document metadata

        Returns:
            Effective date as ISO string or None
        """
        # Check metadata first
        if metadata:
            for key in ["effective_date", "last_updated", "date", "published"]:
                if key in metadata and metadata[key]:
                    date_str = str(metadata[key]).strip()
                    parsed_date = self._parse_date_string(date_str)
                    if parsed_date:
                        return parsed_date

        # Search in first 5000 chars where dates are typically mentioned
        search_text = content[:5000].lower()

        for pattern in self.date_patterns:
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
                            f"matched pattern '{pattern}': extracted '{date_str}' → {parsed_date}"
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

        prompt = f"""Analyze this policy document to find the effective date.

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

        system_prompt = """You are an expert at extracting effective dates from policy documents. Only return dates that are explicitly stated as effective dates, last updated dates, or similar. Do not guess or infer dates."""

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
                        f"LLM extracted effective date: {parsed_date} (confidence: {result.get('confidence', 0):.2f})"
                    )
                    return parsed_date

            logger.debug("LLM could not identify an effective date in document")
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
        for ordinal, number in self.ordinals.items():
            date_str = date_str.replace(ordinal, number)

        for fmt in self.date_formats:
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
        # Pattern: month day, year or month day year
        month_day_year_pattern = (
            r"(?:"
            + "|".join(self.month_names.keys())
            + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"
        )
        match = re.search(month_day_year_pattern, date_str)
        if match:
            month_name, day, year = match.groups()
            month = self.month_names[month_name.lower()]
            try:
                parsed = datetime(int(year), month, int(day))
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass

        return None
