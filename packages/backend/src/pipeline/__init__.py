"""Re-export shim for the monolithic ``pipeline`` module.

**What it does**
Re-exports every symbol previously importable from ``src.pipeline`` so that
existing imports and test monkeypatches continue working after the split into
six submodules.

**What it contains**
- ``PolicyDocumentPipeline``: the main pipeline orchestrator class.
- ``CrawlResultProcessor``: per-crawl-result validation and document creation.
- ``DocumentAnalyzer``: AI-powered locale/date/region analysis.
- ``DocumentStorer``: deduplicated storage with versioning.
- ``db_session``, ``create_document_service``: framework dependencies
  (re-exported so tests can monkeypatch them).
- ``ProcessingStats``: aggregate run statistics.
- ``logger``, ``logger_analysis``, ``logger_discovery``, ``logger_storage``:
  package-level loggers (re-exported for test assertions).

**What it prevents**
Consumers importing from submodules directly.  All pipeline symbols remain
accessible at ``src.pipeline``.
"""

from src.core.database import db_session

# Re-export submodule references so pyright resolves
# ``pipeline_module.pipeline`` and ``pipeline_module.document_storer``
# in test monkeypatching code.
from src.pipeline import (
    document_storer,  # noqa: F811
    pipeline,  # noqa: F811
)
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
    "document_storer",
    "logger",
    "logger_analysis",
    "logger_discovery",
    "logger_storage",
    "main",
    "pipeline",
]
