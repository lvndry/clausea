# Product Intelligence Data Model

## Collections

| Collection | Purpose |
|---|---|
| `products` | Product metadata + denormalized `stats` |
| `documents` | Markdown + `extraction` + `analysis` (evidence lives here only) |
| `product_intelligence` | One doc/product: rollup + overview + explainer + compliance + deep_analysis |
| `document_changes` | Slim change log (hash + metadata, no markdown copies) |
| `pipeline_jobs` | Pipeline state (terminal jobs TTL after 90 days) |

## Read paths

- `/products/{slug}/topics` → `product_intelligence.rollup` + citation hydration from `documents.extraction`
- `/products/{slug}/overview` → `product_intelligence.overview`
- Extension `/domains` → `products.stats.has_overview`
