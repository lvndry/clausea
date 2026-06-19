"""Policy document crawling pipeline — re-exports for backward compatibility."""

from src.core.database import db_session
from src.pipeline.crawl_result_processor import CrawlResultProcessor
from src.pipeline.document_analyzer import DocumentAnalyzer
from src.pipeline.document_storer import DocumentStorer
from src.pipeline.helpers import (
    _LOCALE_HOST_RE,
    _LOCALE_PATH_RE,
    _TLD_EXTRACT,
    MIN_LEGAL_SCORE_THRESHOLD,
    RESUME_FRESH_HOURS,
    _canonical_rank,
    _content_fingerprint,
    _diff_fields,
    logger,
    logger_analysis,
    logger_discovery,
    logger_storage,
)
from src.pipeline.models import ProcessingStats
from src.pipeline.pipeline import PolicyDocumentPipeline, main
from src.services.service_factory import create_document_service

__all__ = [
    "CrawlResultProcessor",
    "DocumentAnalyzer",
    "DocumentStorer",
    "MIN_LEGAL_SCORE_THRESHOLD",
    "PolicyDocumentPipeline",
    "ProcessingStats",
    "RESUME_FRESH_HOURS",
    "_LOCALE_HOST_RE",
    "_LOCALE_PATH_RE",
    "_TLD_EXTRACT",
    "_canonical_rank",
    "_content_fingerprint",
    "_diff_fields",
    "create_document_service",
    "db_session",
    "logger",
    "logger_analysis",
    "logger_discovery",
    "logger_storage",
    "main",
]
