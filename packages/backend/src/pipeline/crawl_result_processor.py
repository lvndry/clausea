"""Validates, classifies, and enriches a single ``CrawlResult`` into a ``Document``.

**What it does**
For each ``CrawlResult`` produced by the crawler:
1. Validates that the result has sufficient content and a high enough policy score.
2. Runs ``DocumentAnalyzer`` to get locale, doc-type classification, dates, and regions.
3. Normalises the result URL (strips trailing slash, enforces https).
4. Builds a ``Document`` Pydantic model with all metadata, analysis, and the cleaned text.
5. Returns the ``Document`` (or ``None`` if the result should be skipped).

**What it contains**
- ``CrawlResultProcessor`` class.
- ``process_crawl_result(crawl_result, product) -> Document | None``.
- Internal helpers for URL normalisation and content validation.

**What it allows/prevents**
Allows the pipeline to convert raw crawl results into persisted ``Document``
records.  Prevents low-quality or irrelevant pages from entering the database
(bypasses storage entirely if policy score is below threshold or content is empty).
"""

from __future__ import annotations

from datetime import datetime

from src.crawler import ClauseaCrawler, CrawlResult
from src.models.document import Document, coerce_doc_type_from_classifier
from src.models.product import Product
from src.pipeline.document_analyzer import DocumentAnalyzer
from src.pipeline.helpers import (
    MIN_LEGAL_SCORE_THRESHOLD,
    logger,
    logger_analysis,
)
from src.pipeline.models import ProcessingStats


class CrawlResultProcessor:
    def __init__(self, analyzer: DocumentAnalyzer, stats: ProcessingStats) -> None:
        self._analyzer = analyzer
        self._stats = stats

    async def process(
        self, result: CrawlResult, product: Product, trusted: bool = False
    ) -> Document | None:
        self._analyzer.reset_usage_stats()
        usage_reason = "completed"
        document: Document | None = None

        try:
            markdown_content = result.markdown

            if not markdown_content or len(markdown_content.strip()) < 300:
                text_len = len(markdown_content.strip()) if markdown_content else 0
                self._stats.crawl_skip_reasons.append(
                    {
                        "url": result.url,
                        "reason": "insufficient_content",
                        "detail": f"text={text_len} chars",
                    }
                )
                logger_analysis.info(
                    f"[skip:insufficient_content] {result.url} (text={text_len} chars)"
                )
                return None

            if ClauseaCrawler._is_garbled_content(markdown_content):
                self._stats.crawl_skip_reasons.append(
                    {"url": result.url, "reason": "garbled_content", "detail": None}
                )
                logger_analysis.info(f"[skip:garbled_content] {result.url}")
                return None

            if (
                not trusted
                and result.legal_score is not None
                and result.legal_score < MIN_LEGAL_SCORE_THRESHOLD
            ):
                self._stats.crawl_skip_reasons.append(
                    {
                        "url": result.url,
                        "reason": "low_legal_score",
                        "detail": f"legal_score={result.legal_score:.2f}",
                    }
                )
                logger_analysis.info(
                    f"[skip:low_legal_score] {result.url} (legal_score={result.legal_score:.2f})"
                )
                return None

            classification = await self._analyzer.classify_document(
                result.url, markdown_content, result.metadata, legal_score=result.legal_score
            )

            logger_analysis.debug(
                f"classified as '{classification.get('classification')}' (is_policy: {classification.get('is_policy_document')})"
            )

            if not classification.get("is_policy_document", False):
                classification_label = str(classification.get("classification", "unknown"))
                self._stats.crawl_skip_reasons.append(
                    {
                        "url": result.url,
                        "reason": "non_policy_classification",
                        "detail": f"classifier={classification_label}",
                    }
                )
                logger_analysis.info(
                    f"[skip:non_policy_classification] {result.url} (classifier={classification_label})"
                )
                usage_reason = f"non-policy classification: {classification_label}"
                return None

            locale_result = await self._analyzer.detect_locale(
                markdown_content, result.metadata, result.url
            )
            detected_locale = locale_result.get("locale", "en-US")
            language_name = locale_result.get("language_name", "English")

            logger_analysis.debug(
                f"detected locale: {detected_locale} ({language_name}, confidence: {locale_result.get('confidence', 0):.2f})"
            )

            if "en" not in detected_locale.lower():
                self._stats.crawl_skip_reasons.append(
                    {
                        "url": result.url,
                        "reason": "non_english",
                        "detail": f"locale={detected_locale}",
                    }
                )
                logger_analysis.info(f"[skip:non_english] {result.url} (locale={detected_locale})")
                self._stats.non_english_skipped += 1
                usage_reason = f"non-English locale: {detected_locale}"
                return None

            self._stats.english_documents += 1
            self._stats.policy_documents_processed += 1

            region_detection = await self._analyzer.detect_regions(
                markdown_content, result.metadata, result.url
            )

            effective_date_str = await self._analyzer.extract_effective_date(
                markdown_content, result.metadata
            )
            effective_date = None
            if effective_date_str:
                try:
                    effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
                    logger.debug(f"Parsed effective date: {effective_date}")
                except ValueError as e:
                    logger.warning(f"Failed to parse effective date '{effective_date_str}': {e}")

            doc_type = coerce_doc_type_from_classifier(classification.get("classification"))
            title_result = await self._analyzer.extract_title(
                result.markdown,
                result.metadata,
                result.url,
                doc_type,
            )

            document = Document(
                title=title_result.get("title", "Untitled Policy Document"),
                url=result.url,
                product_id=product.id,
                markdown=result.markdown,
                metadata=result.metadata,
                doc_type=doc_type,
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
            document_id = document.id if document else None
            document_title = document.title if document else None

            usage_summary = self._analyzer.get_usage_summary()

            for model_stats in usage_summary.values():
                self._stats.total_prompt_tokens += model_stats.get("prompt_tokens", 0)
                self._stats.total_completion_tokens += model_stats.get("completion_tokens", 0)
                self._stats.total_tokens += model_stats.get("total_tokens", 0)
                cost = model_stats.get("cost")
                if cost is not None and cost > 0:
                    self._stats.total_cost += cost

            self._analyzer.log_llm_usage(
                context=result.url,
                reason=usage_reason,
                operation_type="crawl",
                product_slug=product.slug,
                product_id=product.id,
                document_url=result.url,
                document_title=document_title,
                document_id=document_id,
            )


__all__ = ["CrawlResultProcessor"]
