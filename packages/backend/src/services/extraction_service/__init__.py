"""Extraction service — re-exports for backward compatibility."""

from src.services.extraction_service.merging import (
    _clean_raw,
    _merge_ai_usage,
    _merge_children_policy,
    _merge_cookie_trackers,
    _merge_data_items,
    _merge_privacy_signals,
    _merge_retention_rules,
    _merge_text_items,
    _merge_third_parties,
)
from src.services.extraction_service.models import (
    _AIUsage,
    _ChildrenPolicy,
    _CookieTracker,
    _DataItem,
    _Item,
    _PrivacySignals,
    _RetentionRule,
    _ThirdParty,
)
from src.services.extraction_service.service import _EXTRACTION_PRIMARY, extract_document_facts
from src.services.extraction_service.utils import _chunk_text, _extraction_validator

__all__ = [
    "_AIUsage",
    "_EXTRACTION_PRIMARY",
    "_ChildrenPolicy",
    "_PrivacySignals",
    "_RetentionRule",
    "_ThirdParty",
    "_chunk_text",
    "_clean_raw",
    "_CookieTracker",
    "_DataItem",
    "_Item",
    "_extraction_validator",
    "_merge_ai_usage",
    "_merge_children_policy",
    "_merge_cookie_trackers",
    "_merge_data_items",
    "_merge_privacy_signals",
    "_merge_retention_rules",
    "_merge_text_items",
    "_merge_third_parties",
    "extract_document_facts",
]
