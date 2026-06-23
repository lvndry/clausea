# Product Intelligence Data Model

## Overview

Clausea stores policy intelligence using a **document-centric source of truth** with a **unified product cache**.

## Collections

| Collection | Purpose |
|---|---|
| `products` | Product metadata + denormalized `stats` |
| `documents` | Markdown + `extraction` + `analysis` (evidence lives here only) |
| `product_intelligence` | One doc/product: rollup + overview + explainer + compliance + deep_analysis |
| `document_changes` | Slim change log (hash + metadata, no markdown copies) |
| `pipeline_jobs` | Pipeline state (terminal jobs TTL after 90 days) |

## Deprecated (migration only)

- `findings`, `aggregations`, `product_overviews`, `product_explainers`, `product_compliance`, `deep_analyses`, `document_versions`

Run migration:

```bash
cd packages/backend
MONGO_URI=... uv run python scripts/migrate_to_product_intelligence.py --dry-run
MONGO_URI=... uv run python scripts/migrate_to_product_intelligence.py
```

## Read paths

- `/products/{slug}/topics` → `product_intelligence.rollup` + citation hydration from `documents.extraction`
- `/products/{slug}/overview` → `product_intelligence.overview`
- Extension `/domains` → `products.stats.has_overview`
