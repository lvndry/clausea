"""One-shot production fix for corrupted product names.

Reuses the pipeline's real extractor (``_extract_brand_name``) so the DB fix
applies the exact same rules as future crawls. Default mode is a dry-run; pass
``--apply`` to write.

For every product:
  1. Build synthetic CrawlResults from stored document metadata.
  2. corrected = majority og:site_name/application-name (cleaned, validated,
     domain-affined) -> "auto_extracted"; else domain-derived -> "auto_domain".
  3. If the current name is bad (lacks domain affinity, contains a section
     suffix, or is a placeholder) -> replace with ``corrected``.
  4. Legacy products with name_source=None get a source assigned so the new
     pipeline gate works going forward.
"""

import argparse
import asyncio
import os
import re
from collections import defaultdict

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/Users/lvndry/github/clausea/packages/backend/.env")

from src.crawler.models import CrawlResult  # noqa: E402
from src.models.product import (  # noqa: E402
    NAME_SOURCE_AUTO_DOMAIN,
    NAME_SOURCE_AUTO_EXTRACTED,
)
from src.pipeline.pipeline import (  # noqa: E402
    _DATEISH,
    _GENERIC_PLACEHOLDERS,
    _SECTION_SUFFIXES,
    _extract_brand_name,
    _has_affinity,
    _looks_like_descriptive_phrase,
)
from src.services.pipeline_service import _domain_to_product_name  # noqa: E402

URI = os.environ["PRODUCTION_MONGO_URI"]
DB_NAME = "clausea"


def _domain_to_product_name_local(domain: str) -> str:
    return _domain_to_product_name(domain)


def _is_bad_name(name: str, slug: str, domains: list[str]) -> bool:
    """A current name is bad when it is clearly a section/placeholder/descriptive
    title, OR when it has no relation to the product (neither slug nor any
    domain root). A curated brand that simply differs from the slug (e.g. "xAI"
    for slug "grok", domain "x.ai") is NOT bad because it matches the domain root.
    """
    if not name:
        return True
    lower = name.lower()
    if lower in _GENERIC_PLACEHOLDERS:
        return True
    if _DATEISH.match(name):
        return True
    for suffix in _SECTION_SUFFIXES:
        if re.search(r"\b" + re.escape(suffix) + r"\b", lower):
            return True
    if _looks_like_descriptive_phrase(name):
        return True
    if not _has_affinity(name, slug, domains):
        return True
    return False


def _compute_corrected(
    slug: str, domains: list[str], fake_results: list[CrawlResult]
) -> tuple[str, str]:
    extracted = _extract_brand_name(fake_results, slug, domains)
    if extracted:
        return extracted, NAME_SOURCE_AUTO_EXTRACTED
    primary = domains[0] if domains else slug
    return _domain_to_product_name_local(primary), NAME_SOURCE_AUTO_DOMAIN


async def main(apply: bool) -> None:
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]

    products = await db.products.find(
        {}, {"id": 1, "name": 1, "slug": 1, "domains": 1, "name_source": 1}
    ).to_list(length=None)

    docs = await db.documents.find(
        {},
        {
            "product_id": 1,
            "metadata.title": 1,
            "metadata.og:site_name": 1,
            "metadata.application-name": 1,
        },
    ).to_list(length=None)

    docs_by_product: dict[str, list[dict]] = defaultdict(list)
    for doc in docs:
        pid = doc.get("product_id")
        if pid:
            docs_by_product[pid].append(doc.get("metadata") or {})

    name_changes: list[tuple] = []
    source_only: list[tuple] = []
    skipped_good: list[tuple] = []

    for product in products:
        pid = product["id"]
        slug = product.get("slug", "")
        current = (product.get("name") or "").strip()
        domains = product.get("domains") or []
        existing_source = product.get("name_source")

        fake_results = [
            CrawlResult(
                url="",
                title=md.get("title", ""),
                content="",
                markdown="",
                metadata={
                    "og:site_name": md.get("og:site_name", ""),
                    "application-name": md.get("application-name", ""),
                },
                status_code=200,
                success=True,
            )
            for md in docs_by_product.get(pid, [])
            if md.get("og:site_name") or md.get("application-name") or md.get("title")
        ]

        corrected, corrected_source = _compute_corrected(slug, domains, fake_results)
        bad = _is_bad_name(current, slug, domains)

        if bad and current != corrected:
            name_changes.append((slug, current, corrected, corrected_source, existing_source))
        elif current == corrected:
            target_source = existing_source or NAME_SOURCE_AUTO_DOMAIN
            if target_source != existing_source:
                source_only.append((slug, current, target_source))
            else:
                skipped_good.append((slug, current))
        else:
            # Current name is good (affinity, no section suffix) but differs from
            # the computed candidate -> likely manually curated. Keep the name,
            # only assign a source if missing.
            target_source = existing_source or NAME_SOURCE_AUTO_DOMAIN
            if target_source != existing_source:
                source_only.append((slug, current, target_source))
            else:
                skipped_good.append((slug, current))

    print(f"\n{'=' * 120}\nNAME CHANGES ({len(name_changes)}) — bad names replaced\n{'=' * 120}")
    print(f"{'SLUG':<22} {'CURRENT':<42} -> {'CORRECTED':<28} {'SOURCE'}")
    print("-" * 120)
    for slug, current, corrected, source, _old in sorted(name_changes, key=lambda r: r[0].lower()):
        print(f"{slug:<22} {current[:40]:<42} -> {corrected[:26]:<28} {source}")

    print(
        f"\n{'=' * 120}\nSOURCE-ONLY UPDATES ({len(source_only)}) — name kept, name_source assigned\n{'=' * 120}"
    )
    for slug, current, target_source in sorted(source_only, key=lambda r: r[0].lower()):
        print(f"{slug:<22} {current[:40]:<42} source -> {target_source}")

    print(f"\nSkipped (already good, source set): {len(skipped_good)}")
    print(f"Total products: {len(products)}")

    if not apply:
        print("\n[DRY RUN] No changes written. Re-run with --apply to commit.")
        client.close()
        return

    confirm = input("\nType 'yes' to apply these changes to production: ")
    if confirm.strip().lower() != "yes":
        print("Aborted, no changes written.")
        client.close()
        return

    applied = 0
    for slug, current, corrected, source, _old in name_changes:
        result = await db.products.update_one(
            {"slug": slug}, {"$set": {"name": corrected, "name_source": source}}
        )
        if result.modified_count:
            applied += 1
            print(f"  [name] {slug}: '{current}' -> '{corrected}' ({source})")

    for slug, _current, target_source in source_only:
        result = await db.products.update_one(
            {"slug": slug}, {"$set": {"name_source": target_source}}
        )
        if result.modified_count:
            applied += 1
            print(f"  [source] {slug}: name_source -> {target_source}")

    print(f"\nApplied {applied} updates.")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
