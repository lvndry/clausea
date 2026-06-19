"""Main pipeline orchestrator — drives crawl → analyse → store for every product.

**What it does**
``PolicyDocumentPipeline`` is the top-level coordinator.  For each product:
1. Calls ``ClauseaCrawler.crawl_for_policy_documents(product)`` to discover
   and fetch policy pages.
2. Iterates over ``CrawlResult`` objects, passing each to ``CrawlResultProcessor``
   for validation and ``Document`` creation.
3. Passes each ``Document`` to ``DocumentStorer`` for deduplicated persistence.
4. Logs run statistics and returns ``ProcessingStats``.

**What it contains**
- ``PolicyDocumentPipeline`` class with ``run()`` method.
- ``_normalize_url(url)``: pipeline-level URL normaliser (``https://`` prefix, no trailing slash).
- ``_check_trusted_urls(result, trusted)``: bypass logic for pre-approved policy URLs.
- ``main()``: CLI entry point.

**What it allows/prevents**
Allows a single ``run()`` call to process hundreds of products without manual
intervention.  Prevents crawl results from bypassing analysis or storage (every
result flows through the full pipeline).  Prevents the pipeline from crashing
on individual product failures (catches and logs, continues to next product).
"""

from __future__ import annotations

import asyncio
import time
import tracemalloc
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv

from src.core.config import config, discovery_crawl_limits
from src.core.database import db_session
from src.crawler import ClauseaCrawler, CrawlResult
from src.models.crawl import CrawlSession
from src.models.document import Document
from src.models.pipeline_job import classify_crawl_error
from src.models.product import Product
from src.pipeline.crawl_result_processor import CrawlResultProcessor
from src.pipeline.document_analyzer import DocumentAnalyzer
from src.pipeline.document_storer import DocumentStorer
from src.pipeline.helpers import (
    _TLD_EXTRACT,
    RESUME_FRESH_HOURS,
    _content_fingerprint,
    logger,
    logger_discovery,
)
from src.pipeline.models import ProcessingStats
from src.repositories.crawl_repository import CrawlRepository
from src.services.service_factory import create_document_service, create_product_service
from src.utils.perf import log_memory_usage, memory_monitor_task

load_dotenv()


class PolicyDocumentPipeline:
    def __init__(
        self,
        max_depth: int | None = None,
        max_pages: int | None = None,
        crawler_strategy: str | None = None,
        concurrent_limit: int | None = None,
        delay_between_requests: float | None = None,
        timeout: int | None = None,
        respect_robots_txt: bool | None = None,
        max_parallel_products: int | None = None,
        use_browser: bool | None = None,
        proxy: str | None = None,
        fallback_min_legal_score: float | None = None,
        discovery_min_legal_score: float | None = None,
        discovery_strategy: str | None = None,
        fallback_strategy: str | None = None,
        min_docs_before_fallback: int | None = None,
        required_doc_types: list[str] | None = None,
        user_agent: str | None = None,
        progress_callback: Callable[[str, int, int], None]
        | Callable[[str, int, int], Awaitable[None]]
        | None = None,
        job_id: str | None = None,
    ):
        c = config.crawler

        def _resolve(val, default):
            return default if val is None else val

        self.max_depth = _resolve(max_depth, c.max_depth)
        self.max_pages = _resolve(max_pages, c.max_pages)
        self.discovery_max_pages, self.discovery_max_depth = discovery_crawl_limits(
            self.max_pages, self.max_depth
        )
        self.crawler_strategy = _resolve(crawler_strategy, c.crawler_strategy)
        self.concurrent_limit = _resolve(concurrent_limit, c.concurrent_limit)
        self.delay_between_requests = _resolve(delay_between_requests, c.delay_between_requests)
        self.timeout = _resolve(timeout, c.timeout)
        self.respect_robots_txt = _resolve(respect_robots_txt, c.respect_robots_txt)
        self.max_parallel_products = _resolve(max_parallel_products, c.max_parallel_products)
        self.use_browser = _resolve(use_browser, c.use_browser)
        self.browser_concurrency = c.browser_concurrency
        self.proxy = _resolve(proxy, c.proxy)
        self.fallback_min_legal_score = _resolve(
            fallback_min_legal_score, c.fallback_min_legal_score
        )
        self.discovery_min_legal_score = _resolve(
            discovery_min_legal_score, c.discovery_min_legal_score
        )
        self.discovery_strategy = _resolve(discovery_strategy, c.discovery_strategy)
        self.fallback_strategy = _resolve(fallback_strategy, c.fallback_strategy)
        self.min_docs_before_fallback = _resolve(
            min_docs_before_fallback, c.min_docs_before_fallback
        )
        self.required_doc_types = (
            required_doc_types if required_doc_types is not None else list(c.required_doc_types)
        )
        self.user_agent = _resolve(user_agent, c.user_agent)
        self.progress_callback: (
            Callable[[str, int, int], None] | Callable[[str, int, int], Awaitable[None]] | None
        ) = progress_callback
        self._pending_progress_tasks: list[asyncio.Task] = []
        self._job_id = job_id

        self.analyzer = DocumentAnalyzer()
        self.stats = ProcessingStats()
        self._storer = DocumentStorer(self.stats, job_id=self._job_id)
        self._result_processor = CrawlResultProcessor(self.analyzer, self.stats)

        logger.info(
            "Pipeline initialized: max_depth=%s max_pages=%s discovery=%s/%s (pages/depth) "
            "discovery_strategy=%s fallback_strategy=%s",
            self.max_depth,
            self.max_pages,
            self.discovery_max_pages,
            self.discovery_max_depth,
            self.discovery_strategy,
            self.fallback_strategy,
        )

    async def _get_recently_stored_urls(self, product: Product) -> list[str]:
        cutoff = datetime.now() - timedelta(hours=RESUME_FRESH_HOURS)
        try:
            async with db_session() as db:
                document_service = create_document_service()
                return await document_service.get_recent_document_urls(db, product.id, cutoff)
        except Exception as error:
            logger.warning(
                f"Could not load recently stored URLs for {product.name} "
                f"(resume skip disabled this run): {error}"
            )
            return []

    @staticmethod
    def _allowed_domains_for_product(product: Product) -> list[str]:
        domains = list(product.domains or [])
        seen = {_TLD_EXTRACT(d).domain for d in domains}
        for seed in product.crawl_base_urls or []:
            ext = _TLD_EXTRACT(seed)
            if ext.domain and ext.domain not in seen:
                seen.add(ext.domain)
                domains.append(f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain)
        return domains

    def _create_crawler_for_product(
        self,
        product: Product,
        *,
        max_depth: int | None = None,
        max_pages: int | None = None,
        min_legal_score: float | None = None,
        strategy: str | None = None,
        progress_phase: str | None = None,
        result_callback: Callable[[CrawlResult], Awaitable[None]] | None = None,
        stop_callback: Callable[[], bool] | Callable[[], Awaitable[bool]] | None = None,
        recently_stored_urls: list[str] | None = None,
    ) -> ClauseaCrawler:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{timestamp}_{product.slug}_crawl.log"
        log_file_path = f"logs/{log_filename}"

        progress_callback = None
        if self.progress_callback and progress_phase:

            def progress_callback(current: int, total: int) -> None:
                assert self.progress_callback is not None
                callback_result = self.progress_callback(progress_phase, current, total)
                if callback_result is not None:

                    async def _wrap():
                        await callback_result

                    task = asyncio.create_task(_wrap())
                    self._pending_progress_tasks.append(task)

        return ClauseaCrawler(
            max_depth=max_depth or self.max_depth,
            max_pages=max_pages or self.max_pages,
            max_concurrent=self.concurrent_limit,
            delay_between_requests=self.delay_between_requests,
            delay_jitter=config.crawler.rate_limit_jitter,
            timeout=self.timeout,
            allowed_domains=self._allowed_domains_for_product(product),
            respect_robots_txt=self.respect_robots_txt,
            user_agent=self.user_agent,
            follow_external_links=False,
            min_legal_score=min_legal_score if min_legal_score is not None else 0.0,
            strategy=strategy or self.crawler_strategy,
            log_file_path=log_file_path,
            use_browser=self.use_browser,
            browser_concurrency=self.browser_concurrency,
            proxy=self.proxy,
            allowed_paths=product.crawl_allowed_paths,
            denied_paths=product.crawl_denied_paths,
            progress_callback=progress_callback,
            result_callback=result_callback,
            stop_callback=stop_callback,
            recently_stored_urls=recently_stored_urls,
        )

    async def _store_documents(self, documents: list[Document]) -> int:
        return await self._storer.store_documents(documents)

    async def _process_crawl_result(
        self, result: CrawlResult, product: Product, trusted: bool = False
    ) -> Document | None:
        return await self._result_processor.process(result, product, trusted=trusted)

    def _normalize_url(self, url_or_domain: str) -> str:
        url = url_or_domain.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def _seed_dedupe_key(self, normalized_url: str) -> tuple[str, str, str, str]:
        from src.crawler import _TLD_EXTRACT as crawler_tld

        parsed = urlparse(normalized_url)
        ext = crawler_tld(normalized_url)
        registered_domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        normalized_path = parsed.path.rstrip("/") or "/"
        return (registered_domain, parsed.netloc, ext.subdomain, normalized_path)

    def _get_crawl_urls(self, product: Product) -> list[str]:
        urls: list[str] = []
        seen_dedup_keys: set[tuple[str, str, str, str]] = set()

        for domain in product.domains or []:
            normalized = self._normalize_url(domain)
            key = self._seed_dedupe_key(normalized)
            if key not in seen_dedup_keys:
                seen_dedup_keys.add(key)
                urls.append(normalized)

        for base_url in product.crawl_base_urls or []:
            normalized = self._normalize_url(base_url)
            key = self._seed_dedupe_key(normalized)
            if key not in seen_dedup_keys:
                seen_dedup_keys.add(key)
                urls.append(normalized)

        return urls

    async def _start_crawl_session(self, product: Product, crawl_urls: list[str]) -> CrawlSession:
        session = CrawlSession(
            product_id=product.id,
            job_id=self._job_id,
            status="in_progress",
            started_at=datetime.now(),
        )
        async with db_session() as db:
            crawl_repo = CrawlRepository()
            await crawl_repo.create(db, session)
        return session

    async def _finish_crawl_session(
        self,
        session: CrawlSession,
        stats: ProcessingStats,
        error: str | None = None,
    ) -> None:
        session.completed_at = datetime.now()
        session.status = "error" if error else "completed"
        session.error = error
        session.stats = stats.crawl_errors
        async with db_session() as db:
            crawl_repo = CrawlRepository()
            await crawl_repo.update(db, session)

    def _should_fallback_crawl(self, documents: list[Document]) -> bool:
        if len(documents) < self.min_docs_before_fallback:
            return True
        if self.required_doc_types:
            found_types = {d.doc_type for d in documents if d.doc_type}
            missing = set(self.required_doc_types) - found_types
            if missing:
                logger_discovery.info(f"🔍 Fallback needed — missing required types: {missing}")
                return True
        return False

    async def _classify_results(
        self,
        results: list[CrawlResult],
        product: Product,
        processed_urls: set[str],
        seen_fingerprints: set[str],
        trusted_urls: list[str] | None = None,
    ) -> list[Document]:
        documents: list[Document] = []
        trusted = set(trusted_urls or [])

        for result in results:
            if result.url in processed_urls:
                continue
            processed_urls.add(result.url)

            if result.success:
                fp = _content_fingerprint(result.content or "")
                if fp in seen_fingerprints:
                    logger_discovery.debug(f"Near-duplicate skipped: {result.url}")
                    continue
                seen_fingerprints.add(fp)

                document = await self._process_crawl_result(
                    result, product, trusted=result.url in trusted
                )
                if document is not None:
                    documents.append(document)
            else:
                logger_discovery.warning(f"Failed to crawl {result.url}: {result.error_message}")
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
        if not crawl_urls:
            return []
        logger_discovery.info(f"Crawling {len(crawl_urls)} base URL(s)")
        results = await crawler.crawl_multiple(crawl_urls)
        logger_discovery.info(f"Crawl returned {len(results)} result(s)")
        return results

    async def _process_product(self, product: Product) -> list[Document]:
        processed_documents: list[Document] = []
        processed_urls: set[str] = set()
        seen_fingerprints: set[str] = set()
        crawl_urls = self._get_crawl_urls(product)

        if not crawl_urls:
            logger_discovery.warning(f"No valid crawl URLs for {product.name}, skipping")
            return []

        trusted_urls: frozenset[str] = frozenset(
            self._normalize_url(u)
            for u in (product.crawl_base_urls or [])
            if self._normalize_url(u)
        )

        recently_stored = await self._get_recently_stored_urls(product)

        session = await self._start_crawl_session(product, crawl_urls)

        self.stats.total_urls_crawled += len(crawl_urls)

        total_results = 0

        try:

            async def result_callback(result: CrawlResult) -> None:
                docs = await self._classify_results(
                    [result],
                    product,
                    processed_urls,
                    seen_fingerprints,
                    trusted_urls=list(trusted_urls),
                )
                if docs:
                    stored = await self._store_documents(docs)
                    self.stats.policy_documents_stored += stored
                    processed_documents.extend(docs)

            logger_discovery.info(
                f"🔍 [{product.name}] Discovery pass: {self.discovery_strategy}, "
                f"max_depth={self.discovery_max_depth}, max_pages={self.discovery_max_pages}"
            )

            discovery_crawler = self._create_crawler_for_product(
                product,
                max_depth=self.discovery_max_depth,
                max_pages=self.discovery_max_pages,
                min_legal_score=self.discovery_min_legal_score,
                strategy=self.discovery_strategy,
                progress_phase="discovery",
                result_callback=result_callback,
                recently_stored_urls=recently_stored,
            )
            discovery_results = await self._crawl_base_urls(discovery_crawler, crawl_urls)
            total_results += len(discovery_results)

            logger_discovery.info(
                f"📄 [{product.name}] Discovery pass complete: {len(discovery_results)} pages"
            )

            if self._should_fallback_crawl(processed_documents):
                logger_discovery.info(
                    f"🔍 [{product.name}] Fallback pass: {self.fallback_strategy}, "
                    f"max_depth={self.max_depth}, max_pages={self.max_pages}"
                )
                fallback_crawler = self._create_crawler_for_product(
                    product,
                    max_depth=self.max_depth,
                    max_pages=self.max_pages,
                    min_legal_score=self.fallback_min_legal_score,
                    strategy=self.fallback_strategy,
                    progress_phase="fallback",
                    result_callback=result_callback,
                    recently_stored_urls=recently_stored,
                )
                fallback_results = await self._crawl_base_urls(fallback_crawler, crawl_urls)
                total_results += len(fallback_results)

                logger_discovery.info(
                    f"📄 [{product.name}] Fallback pass complete: {len(fallback_results)} pages"
                )
            else:
                logger_discovery.info(
                    f"✅ [{product.name}] Fallback skipped: "
                    f"{len(processed_documents)} docs meet criteria"
                )

            self.stats.total_urls_crawled += total_results
            self.stats.total_documents_found += total_results

            logger.info(f"💾 [{product.name}] Stored {len(processed_documents)} policy documents")

            self.stats.products_processed += 1
            await self._finish_crawl_session(session, self.stats)

        except Exception as e:
            self.stats.products_failed += 1
            self.stats.failed_product_slugs.append(product.slug)
            logger.error(f"❌ [{product.name}] Processing failed: {e}")
            await self._finish_crawl_session(session, self.stats, error=str(e))
            return []

        return processed_documents

    async def run(self, products: list[Product] | None = None) -> ProcessingStats:
        tracemalloc.start()
        pipeline_start_time = time.time()

        logger.info("🚀 Starting Policy Document Crawling Pipeline")
        log_memory_usage("Pipeline start")

        memory_task = asyncio.create_task(memory_monitor_task(60))

        try:
            if products is None:
                async with db_session() as db:
                    product_service = create_product_service()
                    products = await product_service.get_all_products(db)
            logger.info(f"📊 Processing {len(products)} products")

            semaphore = asyncio.Semaphore(self.max_parallel_products)

            async def _process_product_with_semaphore(idx: int, product: Product) -> None:
                async with semaphore:
                    logger.info(f"🏢 [{idx}/{len(products)}] Starting product: {product.name}")
                    await self._process_product(product)
                    logger.info(f"✅ [{idx}/{len(products)}] Finished product: {product.name}")

            tasks = [
                _process_product_with_semaphore(i, product) for i, product in enumerate(products, 1)
            ]

            await asyncio.gather(*tasks)

            if self._pending_progress_tasks:
                await asyncio.gather(*self._pending_progress_tasks, return_exceptions=True)
                self._pending_progress_tasks.clear()

            self.stats.processing_time_seconds = time.time() - pipeline_start_time

            logger.info("🎉 Pipeline completed successfully!")
            logger.info(f"📊 Products processed: {self.stats.products_processed}")
            logger.info(f"❌ Products failed: {self.stats.products_failed}")
            if self.stats.failed_product_slugs:
                logger.info(
                    f"❌ Failed product slugs: {', '.join(self.stats.failed_product_slugs)}"
                )
            logger.info(f"🌐 Total URLs crawled: {self.stats.total_urls_crawled}")
            logger.info(f"📄 Total documents found: {self.stats.total_documents_found}")
            logger.info(f"📋 Policy documents processed: {self.stats.policy_documents_processed}")
            logger.info(f"💾 Policy documents stored: {self.stats.policy_documents_stored}")
            logger.info(f"🗣️ English documents: {self.stats.english_documents}")
            logger.info(f"🌍 Non-English skipped: {self.stats.non_english_skipped}")
            logger.info(f"🔄 Duplicates skipped: {self.stats.duplicates_skipped}")
            logger.info(f"✅ Success rate: {self.stats.success_rate:.1f}%")
            logger.info(f"🎯 Legal detection rate: {self.stats.legal_detection_rate:.1f}%")
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

            if self.stats.total_tokens > 0:
                cost_str = f" (${self.stats.total_cost:.6f})" if self.stats.total_cost > 0 else ""
                logger.info(
                    f"🔢 LLM tokens: input={self.stats.total_prompt_tokens:,} "
                    f"output={self.stats.total_completion_tokens:,} "
                    f"total={self.stats.total_tokens:,}{cost_str}"
                )

            return self.stats

        finally:
            memory_task.cancel()
            log_memory_usage("Pipeline end")

            current, peak = tracemalloc.get_traced_memory()
            logger.info(
                f"🧠 Memory usage: Current={current / 1024 / 1024:.1f}MB, "
                f"Peak={peak / 1024 / 1024:.1f}MB"
            )
            tracemalloc.stop()


async def main() -> None:
    try:
        pipeline = PolicyDocumentPipeline()

        stats = await pipeline.run()

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
