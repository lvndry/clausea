"""One-time cleanup script to recover MongoDB storage space.

Performs three idempotent operations in order:
1. Deletes all documents where ``doc_type == "other"`` (not policy docs).
2. Removes the ``text`` field from all remaining documents via ``$unset``
   (``markdown`` is the canonical representation; ``text`` was a 47 MB duplicate).
3. Truncates ``markdown`` to 150 KB on oversized documents, appending a note.

Prints a human-readable summary of changes and estimated MB freed.

Usage:
    uv run python scripts/cleanup_documents.py

The script is safe to run multiple times (idempotent for all three steps).

IMPORTANT: MongoDB Atlas writes are currently blocked when the cluster exceeds its
storage quota. Run this script ONLY after the cluster has been resized or after
manually freeing space via the Atlas UI.  If writes are still blocked the script
will print a clear message and exit.
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

# Import shared constants from the storer so the truncation suffix stays in
# sync — the cleanup script's idempotency check relies on the same string.
from src.pipeline.document_storer import _MARKDOWN_TRUNCATION_SUFFIX, _MAX_MARKDOWN_LENGTH

load_dotenv()

ATLAS_QUOTA_ERROR_CODE = 8000
_BULK_BATCH_SIZE = 500


async def run_cleanup() -> None:
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import UpdateOne
    from pymongo.errors import OperationFailure

    from src.core.config import config

    uri = config.database.mongodb_uri
    if "+srv" in uri:
        client: AsyncIOMotorClient = AsyncIOMotorClient(uri, tls=True, tlsCAFile=certifi.where())
    else:
        client = AsyncIOMotorClient(uri)

    db = client["clausea"]

    print("=" * 60)
    print("Clausea document cleanup")
    print("=" * 60)

    def _handle_quota_error(e: OperationFailure) -> None:
        if e.code == ATLAS_QUOTA_ERROR_CODE:
            print(
                "\n[ERROR] Atlas storage quota exceeded — upgrade cluster tier "
                "before running cleanup.\n"
                "Visit https://cloud.mongodb.com to resize your cluster."
            )
            sys.exit(1)
        raise

    # ------------------------------------------------------------------
    # Step 1: Delete other-type documents
    # ------------------------------------------------------------------
    print("\n[1/3] Counting 'other'-type documents …")
    try:
        other_count = await db.documents.count_documents({"doc_type": "other"})
    except OperationFailure as e:
        _handle_quota_error(e)

    print(f"      Found {other_count} other-type documents.")
    deleted_count = 0
    if other_count > 0:
        print(f"      Deleting {other_count} other-type documents …")
        try:
            result = await db.documents.delete_many({"doc_type": "other"})
            deleted_count = result.deleted_count
            print(f"      Deleted {deleted_count} documents.")
        except OperationFailure as e:
            _handle_quota_error(e)
    else:
        print("      Nothing to delete (idempotent).")

    # ------------------------------------------------------------------
    # Step 2: Remove text field from all remaining documents
    # ------------------------------------------------------------------
    # Use the same filter for the count and the $unset so the reported number
    # matches the actual documents modified.
    _text_exists_query = {"text": {"$exists": True}}

    print("\n[2/3] Counting documents that still have a 'text' field …")
    try:
        text_count = await db.documents.count_documents(_text_exists_query)
    except OperationFailure as e:
        _handle_quota_error(e)

    print(f"      Found {text_count} documents with a 'text' field.")
    unset_count = 0
    avg_text_bytes = 0.0
    if text_count > 0:
        # Sample up to 200 non-empty docs to estimate the average text size.
        # The estimate is based on the non-empty sub-sample; actual savings may
        # differ slightly if some stored text fields are empty strings.
        sample = (
            await db.documents.find(
                {"text": {"$exists": True, "$ne": ""}},
                {"text": 1},
            )
            .limit(200)
            .to_list(length=200)
        )
        if sample:
            avg_text_bytes = sum(len((doc.get("text") or "").encode()) for doc in sample) / len(
                sample
            )
            estimated_mb = (avg_text_bytes * text_count) / (1024 * 1024)
            print(
                f"      Estimated text field size: ~{estimated_mb:.1f} MB "
                f"(avg {avg_text_bytes / 1024:.1f} KB per non-empty doc, ×{text_count} total)."
            )
        else:
            # All sampled documents had empty/missing text — skip the estimate.
            print("      Estimated text field size: unavailable (no non-empty docs in sample).")
        print("      Removing 'text' field via $unset …")
        try:
            result = await db.documents.update_many(
                _text_exists_query,
                {"$unset": {"text": ""}},
            )
            unset_count = result.modified_count
            print(f"      Removed 'text' from {unset_count} documents.")
        except OperationFailure as e:
            _handle_quota_error(e)
    else:
        print("      No documents have a text field (idempotent).")

    # ------------------------------------------------------------------
    # Step 3: Truncate oversized markdown (streamed, bulk-write batches)
    # ------------------------------------------------------------------
    print(f"\n[3/3] Finding documents with markdown > {_MAX_MARKDOWN_LENGTH:,} chars …")
    try:
        # $strLenCP counts Unicode code points; $ifNull guards documents where
        # markdown is absent (returns 0 length so they are excluded).
        oversized_cursor = db.documents.find(
            {
                "$expr": {
                    "$gt": [
                        {"$strLenCP": {"$ifNull": ["$markdown", ""]}},
                        _MAX_MARKDOWN_LENGTH,
                    ]
                }
            },
            {"id": 1, "url": 1, "markdown": 1},
        )
    except OperationFailure as e:
        _handle_quota_error(e)

    truncated_count = 0
    truncated_mb_freed = 0.0
    bulk_updates: list[UpdateOne] = []

    try:
        async for doc in oversized_cursor:
            original_markdown: str = doc.get("markdown") or ""
            if len(original_markdown) <= _MAX_MARKDOWN_LENGTH:
                continue  # Already within limits (idempotent).
            if original_markdown.endswith(_MARKDOWN_TRUNCATION_SUFFIX):
                continue  # Already truncated in a previous run.

            truncated_markdown = (
                original_markdown[:_MAX_MARKDOWN_LENGTH] + _MARKDOWN_TRUNCATION_SUFFIX
            )
            bytes_freed = len(original_markdown.encode()) - len(truncated_markdown.encode())
            truncated_mb_freed += bytes_freed / (1024 * 1024)

            bulk_updates.append(
                UpdateOne({"id": doc["id"]}, {"$set": {"markdown": truncated_markdown}})
            )

            if len(bulk_updates) >= _BULK_BATCH_SIZE:
                await db.documents.bulk_write(bulk_updates, ordered=False)
                truncated_count += len(bulk_updates)
                bulk_updates = []

        if bulk_updates:
            await db.documents.bulk_write(bulk_updates, ordered=False)
            truncated_count += len(bulk_updates)

    except OperationFailure as e:
        _handle_quota_error(e)

    if truncated_count:
        print(f"      Truncated {truncated_count} documents, freed ~{truncated_mb_freed:.1f} MB.")
    else:
        print("      No documents exceed the size limit (idempotent).")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  other-type documents deleted : {deleted_count}")
    print(f"  'text' field removed from    : {unset_count} documents")
    print(f"  oversized markdown truncated : {truncated_count} documents")

    if unset_count > 0 and avg_text_bytes > 0.0:
        estimated_total_text_mb = (avg_text_bytes * text_count) / (1024 * 1024)
        print(f"  estimated MB freed (text)    : ~{estimated_total_text_mb:.1f} MB")
    if truncated_mb_freed > 0:
        print(f"  estimated MB freed (markdown): ~{truncated_mb_freed:.1f} MB")

    client.close()


if __name__ == "__main__":
    asyncio.run(run_cleanup())
