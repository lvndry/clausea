"""Re-export shim for the monolithic ``extraction_service`` module.

**What it does**
Re-exports every symbol that was previously importable from
``src.services.extraction_service`` so all existing imports and test
monkeypatches continue working.

**What it contains**
- ``extract_document_facts``: the main extraction entry point.
- ``_EXTRACTION_PRIMARY``: default extraction cluster key.
- ``_clean_raw``, ``_merge_*`` functions used by the merge pipeline.
- ``_PrivacySignals``, ``_DataItem``, ``_ThirdParty``, … internal models.

**What it prevents**
Consumers reaching into submodules (``from src.services.extraction_service.merging import …``).
All symbols stay accessible at the package level.
"""

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
