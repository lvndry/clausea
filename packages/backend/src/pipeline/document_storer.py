"""Deduplicated ``Document`` storage with content-change detection and versioning.

**What it does**
Handles the final storage phase of the pipeline:
1. Looks up an existing document by canonical URL in the database.
2. Compares the new document's content fingerprint (SHA-256) with the stored version.
   - Identical content → skip update (``documents_skipped++``).
   - Different content → update the stored document and increment version (``documents_updated++``).
   - No existing document → insert new record (``documents_stored++``).

**What it contains**
- ``DocumentStorer`` class.
- ``store_document(document, product, stats)``: the main store-or-update method.
- ``_compute_fingerprint(content)``: SHA-256 of the cleaned text.
- ``_check_existing(canonical_url)``: database lookup by canonical URL.

**What it allows/prevents**
Allows the pipeline to re-crawl the same product periodically without creating
duplicate records.  Prevents redundant DB writes when content hasn't changed
and ensures every content change is tracked with a version increment.
"""

from __future__ import annotations

import hashlib

from src.core.database import db_session
from src.models.document import Document
from src.pipeline.helpers import (
    _canonical_rank,
    _content_fingerprint,
    _diff_fields,
    canonicalize_url,
    logger_storage,
)
from src.pipeline.models import ProcessingStats
from src.repositories.document_version_repository import DocumentVersionRepository
from src.repositories.pipeline_repository import PipelineRepository
from src.services.service_factory import create_document_service
from src.utils.markdown import markdown_to_text

_MAX_MARKDOWN_LENGTH = 150_000
_MARKDOWN_TRUNCATION_SUFFIX = "\n\n[Content truncated at 150,000 characters]"


class DocumentStorer:
    def __init__(self, stats: ProcessingStats, job_id: str | None = None) -> None:
        self._stats = stats
        self._job_id = job_id
        self._pipeline_repo = PipelineRepository() if job_id else None

    async def store_documents(self, documents: list[Document]) -> int:
        stored_count = 0
        linked_count = 0
        updated_count = 0
        duplicate_count = 0
        error_count = 0
        stored_delta = 0
        found_delta = 0

        documents = sorted(documents, key=lambda d: _canonical_rank(d.url))
        seen_fingerprints: dict[tuple[str | None, str], str] = {}

        async with db_session() as db:
            document_service = create_document_service()

            for document in documents:
                try:
                    # Skip non-policy documents — they should never reach storage.
                    if document.doc_type == "other":
                        logger_storage.debug(
                            "skipping other-type document (not a policy doc): %s",
                            document.url,
                        )
                        continue

                    # Cap markdown to avoid storing bloated omnibus legal documents.
                    # Idempotent: skip if already truncated from a previous run.
                    # Work with a local variable so the caller's Document is only
                    # updated when the content actually changes.
                    markdown = document.markdown
                    if len(markdown) > _MAX_MARKDOWN_LENGTH and not markdown.endswith(
                        _MARKDOWN_TRUNCATION_SUFFIX
                    ):
                        markdown = markdown[:_MAX_MARKDOWN_LENGTH] + _MARKDOWN_TRUNCATION_SUFFIX
                        document.markdown = markdown
                        # Re-derive text from the truncated markdown so the content
                        # fingerprint (computed below) reflects exactly what will be
                        # stored — not the original pre-truncation content.
                        document.text = markdown_to_text(markdown)

                    source_product_id = document.product_id
                    existing_doc = await document_service.get_document_by_url(db, document.url)
                    if not existing_doc:
                        canonical = canonicalize_url(document.url)
                        if canonical != document.url:
                            existing_doc = await document_service.get_document_by_url(db, canonical)
                            if existing_doc:
                                logger_storage.debug(
                                    "matched locale variant %s to canonical document %s",
                                    document.url,
                                    canonical,
                                )

                    # Cross-run dedup: if the URL is new but there's already a document
                    # for the same product with identical content, link instead of duplicating.
                    if not existing_doc and document.text and document.text.strip():
                        content_fp = _content_fingerprint(document.text)
                        existing_doc = await document_service.find_existing_by_content_hash(
                            db, source_product_id, content_fp
                        )
                        if existing_doc:
                            logger_storage.info(
                                "collapsing cross-run content duplicate %s "
                                "(identical to stored %s, hash=%s)",
                                document.url,
                                existing_doc.url,
                                content_fp[:12],
                            )
                            self._stats.duplicates_skipped += 1
                            duplicate_count += 1
                            if not existing_doc.is_linked_to_product(source_product_id):
                                linked = await document_service.link_document_to_product(
                                    db, existing_doc.id, source_product_id
                                )
                                if linked:
                                    stored_count += 1
                                    linked_count += 1
                                    stored_delta += 1
                                    found_delta += 1
                                    logger_storage.info(
                                        "linked content-duplicate %s to product %s",
                                        existing_doc.url,
                                        source_product_id,
                                    )
                            seen_fingerprints[(source_product_id, content_fp)] = existing_doc.url
                            continue
                    if existing_doc:
                        linked_this_run = False
                        if not existing_doc.is_linked_to_product(source_product_id):
                            linked_this_run = await document_service.link_document_to_product(
                                db, existing_doc.id, source_product_id
                            )
                            if linked_this_run:
                                logger_storage.info(
                                    "linked existing canonical document %s to product %s",
                                    document.url,
                                    source_product_id,
                                )

                        metadata_str = f"|{document.title}|{document.doc_type}|{document.locale}|{','.join(document.regions)}|{document.effective_date}|"
                        current_hash = hashlib.sha256(
                            (document.text + metadata_str).encode()
                        ).hexdigest()

                        existing_metadata_str = f"|{existing_doc.title}|{existing_doc.doc_type}|{existing_doc.locale}|{','.join(existing_doc.regions)}|{existing_doc.effective_date}|"
                        existing_hash = hashlib.sha256(
                            (existing_doc.text + existing_metadata_str).encode()
                        ).hexdigest()

                        if current_hash != existing_hash:
                            if not document.text.strip() and existing_doc.text.strip():
                                logger_storage.warning(
                                    f"refusing to overwrite non-empty document with empty content: {document.url}"
                                )
                                self._stats.duplicates_skipped += 1
                                duplicate_count += 1
                                continue

                            document.product_id = existing_doc.product_id
                            document.product_ids = [
                                *existing_doc.product_ids,
                                *(
                                    [source_product_id]
                                    if source_product_id not in existing_doc.product_ids
                                    else []
                                ),
                            ]
                            changed = _diff_fields(existing_doc, document)
                            await DocumentVersionRepository().archive(
                                db, existing_doc, job_id=self._job_id, changed_fields=changed
                            )

                            logger_storage.info(
                                f"updating existing document with changes: {document.url}"
                            )
                            document.id = existing_doc.id
                            document.content_hash = _content_fingerprint(document.text)
                            await document_service.update_document(db, document)
                            stored_count += 1
                            updated_count += 1
                            stored_delta += 1
                            found_delta += 1
                        else:
                            if linked_this_run:
                                stored_count += 1
                                linked_count += 1
                                stored_delta += 1
                                found_delta += 1
                            else:
                                logger_storage.debug(
                                    f"skipping unchanged document (duplicate): {document.url}"
                                )
                                self._stats.duplicates_skipped += 1
                                duplicate_count += 1
                        if document.text and document.text.strip():
                            seen_fingerprints[
                                (source_product_id, _content_fingerprint(document.text))
                            ] = document.url
                    else:
                        if document.text and document.text.strip():
                            fp_key = (
                                source_product_id,
                                _content_fingerprint(document.text),
                            )
                            kept_url = seen_fingerprints.get(fp_key)
                            if kept_url and kept_url != document.url:
                                logger_storage.info(
                                    f"collapsing same-content variant {document.url} "
                                    f"(identical to {kept_url})"
                                )
                                self._stats.duplicates_skipped += 1
                                duplicate_count += 1
                                continue
                            seen_fingerprints[fp_key] = document.url

                        logger_storage.info(f"storing new document: {document.url}")
                        document.content_hash = _content_fingerprint(document.text)
                        await document_service.store_document(db, document)
                        stored_count += 1
                        stored_delta += 1
                        found_delta += 1

                except Exception as e:
                    logger_storage.error(
                        f"failed to store document {document.url}: {e}", exc_info=True
                    )
                    error_count += 1

            if self._pipeline_repo and self._job_id and (stored_delta or found_delta):
                await self._pipeline_repo.inc_document_counters(
                    db, self._job_id, stored=stored_delta, found=found_delta
                )

        if len(documents) > 0:
            new_count = stored_count - updated_count - linked_count
            logger_storage.info(
                f"storage complete: {stored_count} stored "
                f"({new_count} new, {updated_count} updated, {linked_count} linked), "
                f"{duplicate_count} duplicates skipped, {error_count} errors"
            )

        return stored_count


__all__ = ["DocumentStorer"]
