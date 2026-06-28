"""Shared fixtures for pipeline tests that must pass the pre-analysis thin-evidence gate."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def passing_thin_evidence_stored_docs() -> list[SimpleNamespace]:
    """Three core docs across two types — satisfies MIN_DISTINCT_CORE_TYPES and MIN_TOTAL_CORE_DOCS."""
    return [
        SimpleNamespace(doc_type="privacy_policy"),
        SimpleNamespace(doc_type="privacy_policy"),
        SimpleNamespace(doc_type="terms_of_service"),
    ]


def make_doc_svc_passing_thin_gate() -> MagicMock:
    svc = MagicMock()
    svc.get_product_documents_by_slug = AsyncMock(return_value=passing_thin_evidence_stored_docs())
    return svc
