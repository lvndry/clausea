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

load_dotenv()

MAX_MARKDOWN_LENGTH = 150_000
TRUNCATION_SUFFIX = "\n\n[Content truncated at 150,000 characters]"
ATLAS_QUOTA_ERROR_CODE = 8000


async def run_cleanup() -> None:
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient
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
        return

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
            return
    else:
        print("      Nothing to delete (idempotent).")

    # ------------------------------------------------------------------
    # Step 2: Remove text field from all remaining documents
    # ------------------------------------------------------------------
    print("\n[2/3] Counting documents that still have a 'text' field …")
    try:
        text_count = await db.documents.count_documents({"text": {"$exists": True, "$ne": ""}})
    except OperationFailure as e:
        _handle_quota_error(e)
        return

    print(f"      Found {text_count} documents with non-empty text field.")
    unset_count = 0
    if text_count > 0:
        # Sample a few docs to estimate average text size before removing.
        sample = (
            await db.documents.find(
                {"text": {"$exists": True, "$ne": ""}},
                {"text": 1},
            )
            .limit(200)
            .to_list(length=200)
        )
        avg_text_bytes = (
            sum(len((doc.get("text") or "").encode()) for doc in sample) / len(sample)
            if sample
            else 0
        )
        estimated_mb = (avg_text_bytes * text_count) / (1024 * 1024)
        print(
            f"      Estimated text field size: {estimated_mb:.1f} MB "
            f"(avg {avg_text_bytes / 1024:.1f} KB per doc)."
        )
        print("      Removing 'text' field via $unset …")
        try:
            result = await db.documents.update_many(
                {"text": {"$exists": True}},
                {"$unset": {"text": ""}},
            )
            unset_count = result.modified_count
            print(f"      Removed 'text' from {unset_count} documents.")
        except OperationFailure as e:
            _handle_quota_error(e)
            return
    else:
        print("      No documents have a text field (idempotent).")

    # ------------------------------------------------------------------
    # Step 3: Truncate oversized markdown
    # ------------------------------------------------------------------
    print(f"\n[3/3] Finding documents with markdown > {MAX_MARKDOWN_LENGTH:,} chars …")
    try:
        # MongoDB can't filter on string length directly without $where; use a
        # JS expression via $expr + $strLenCP for an indexed-compatible query.
        oversized_cursor = db.documents.find(
            {
                "$expr": {
                    "$gt": [{"$strLenCP": {"$ifNull": ["$markdown", ""]}}, MAX_MARKDOWN_LENGTH]
                }
            },
            {"id": 1, "url": 1, "markdown": 1},
        )
        oversized_docs = await oversized_cursor.to_list(length=None)
    except OperationFailure as e:
        _handle_quota_error(e)
        return

    print(f"      Found {len(oversized_docs)} oversized documents.")
    truncated_count = 0
    truncated_mb_freed = 0.0

    for doc in oversized_docs:
        original_markdown: str = doc.get("markdown") or ""
        if len(original_markdown) <= MAX_MARKDOWN_LENGTH:
            continue  # Already within limits (idempotent).
        if original_markdown.endswith(TRUNCATION_SUFFIX):
            continue  # Already truncated in a previous run.

        truncated_markdown = original_markdown[:MAX_MARKDOWN_LENGTH] + TRUNCATION_SUFFIX
        bytes_freed = len(original_markdown.encode()) - len(truncated_markdown.encode())
        truncated_mb_freed += bytes_freed / (1024 * 1024)

        try:
            await db.documents.update_one(
                {"id": doc["id"]},
                {"$set": {"markdown": truncated_markdown}},
            )
            truncated_count += 1
        except OperationFailure as e:
            _handle_quota_error(e)
            return

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

    if unset_count > 0:
        estimated_total_text_mb: float = (
            (avg_text_bytes * text_count) / (1024 * 1024) if text_count > 0 else 0.0
        )
        print(f"  estimated MB freed (text)    : ~{estimated_total_text_mb:.1f} MB")
    if truncated_mb_freed > 0:
        print(f"  estimated MB freed (markdown): ~{truncated_mb_freed:.1f} MB")

    client.close()


if __name__ == "__main__":
    asyncio.run(run_cleanup())
