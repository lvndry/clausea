"""Module-level helpers and constants for the pipeline package."""

from __future__ import annotations

import hashlib
import os
import re
from urllib.parse import urlparse

import tldextract

from src.core.logging import get_logger
from src.models.document import Document

logger = get_logger(__name__)
logger_discovery = get_logger(__name__, component="pipeline:discovery")
logger_analysis = get_logger(__name__, component="pipeline:analysis")
logger_storage = get_logger(__name__, component="pipeline:storage")

_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

MIN_LEGAL_SCORE_THRESHOLD = 0.2

RESUME_FRESH_HOURS = float(os.getenv("PIPELINE_RESUME_FRESH_HOURS", "24"))

_LOCALE_PATH_RE = re.compile(r"^/[a-z]{2}([-_][a-z]{2})?(/|$)", re.IGNORECASE)
_LOCALE_HOST_RE = re.compile(r"^[a-z]{2}([-_][a-z]{2})?\.", re.IGNORECASE)


def _content_fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.md5(normalized[:5000].encode()).hexdigest()


def _diff_fields(existing: Document, incoming: Document) -> list[str]:
    tracked = ["text", "title", "doc_type", "locale", "regions", "effective_date"]
    changed = []
    for field in tracked:
        old_val = getattr(existing, field)
        new_val = getattr(incoming, field)
        if field == "regions":
            if set(old_val or []) != set(new_val or []):
                changed.append(field)
        elif old_val != new_val:
            changed.append(field)
    return changed


def _canonical_rank(url: str) -> tuple[int, int]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    looks_locale = bool(_LOCALE_PATH_RE.match(path)) or (
        bool(_LOCALE_HOST_RE.match(host)) and not host.startswith("www.")
    )
    return (1 if looks_locale else 0, len(path))


__all__ = [
    "MIN_LEGAL_SCORE_THRESHOLD",
    "RESUME_FRESH_HOURS",
    "_LOCALE_HOST_RE",
    "_LOCALE_PATH_RE",
    "_TLD_EXTRACT",
    "_canonical_rank",
    "_content_fingerprint",
    "_diff_fields",
    "logger",
    "logger_analysis",
    "logger_discovery",
    "logger_storage",
]
