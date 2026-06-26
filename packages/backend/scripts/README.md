# Backend operational scripts

Run from `packages/backend` with `uv run python scripts/<name>.py`.

## Pipeline queue (production ops)

| Script | Purpose |
|--------|---------|
| `pipeline_monitor.py` | **Primary monitor.** Modes: `regen` (5-min PIPELINE_UPDATE), `watch` (regen + auto requeue crawl), `down` (SERVICE_DOWN_ALERT), `status` (one-shot) |
| `queue_status.py` | One-shot queue snapshot (same as `pipeline_monitor.py status`) |
| `crawler_monitor.py` | Deep production watchdog: Railway logs, memory, auto-fix, redeploy |
| `requeue_analysis.py` | Queue analysis-only jobs (`skip_crawl`); default: products **missing** overviews; `--stale-hours N` for regen |
| `requeue_crawl.py` | Queue full crawls — **default: only products with zero policy docs** |
| `cancel_wasteful_crawls.py` | Interrupt full crawls when docs already exist |
| `quiesce_jobs.py` | Mark in-flight/interrupted/retryable-failed jobs non-retryable (stop worker auto-refill) |

### Typical production workflow

```bash
# 5-min regen progress (chat notifications parse PIPELINE_UPDATE)
uv run python scripts/pipeline_monitor.py --production

# One-shot queue check
uv run python scripts/queue_status.py --production

# Queue analysis-only for products missing overviews (e.g. stripe)
uv run python scripts/requeue_analysis.py --production --dry-run
uv run python scripts/requeue_analysis.py --production stripe

# Stop all work and prevent worker sweeps from requeueing
uv run python scripts/quiesce_jobs.py --production --dry-run
uv run python scripts/quiesce_jobs.py --production

# Only crawl products with no stored documents (e.g. openai)
uv run python scripts/requeue_crawl.py --production --dry-run

# Stop accidental full crawls on indexed products
uv run python scripts/cancel_wasteful_crawls.py --production --dry-run
uv run python scripts/cancel_wasteful_crawls.py --production
```

## Regeneration & review (dev / ad-hoc)

| Script | Purpose |
|--------|---------|
| `regenerate_overviews.py` | Direct LLM overview regen (bypasses workers), batch + concurrency |
| `analyze_only.py` | Dev shortcut: summarize + overview for one slug in-process |
| `review_product.py` | Compact ✅/⚠️ verdict after a pipeline run |
| `eval_quality.py` | Verbose doc + overview dump for manual QA |
| `run_pipeline_eval.py` | Full pipeline for one URL via PipelineService |

## Ship & validation

| Script | Purpose |
|--------|---------|
| `ship_health_check.py` | Ship-readiness gates with exit codes (`--json`) |
| `validate_topic_rollout.py` | Topic-evidence quality gates for selected slugs |

## Crawler / content probes

| Script | Purpose |
|--------|---------|
| `crawl_probe.py` | Crawl strategy probe with JSON output |
| `content_probe.py` | Single-page fetch length probe |
| `fetch_fixture.py` | Fetch URL → classification test fixture |

## Benchmarks & build

| Script | Purpose |
|--------|---------|
| `benchmark_pipeline.py` | LLM escalation benchmark on JSON corpus |
| `patch_playwright.py` | Docker build: patch Playwright for Camoufox |

## Shared libraries

| Module | Purpose |
|--------|---------|
| `src/ops/script_env.py` | `--production` flag, Mongo URI, `job_url()` |
| `src/ops/promotion.py` | Dev-only local ↔ prod Mongo bulk sync (`PromotionManager`) |
| `src/services/pipeline_eligibility.py` | When to full-crawl vs analysis-only |
| `src/services/pipeline_snapshot.py` | Read-only queue/regen snapshot queries |

## Removed (merged)

- `cli.py` — interactive dev TUI; use targeted scripts instead (`analyze_only.py`, `run_pipeline_eval.py`, `fetch_fixture.py`)
- `pipeline_watch.py` → use `pipeline_monitor.py watch`
- `crawler_down_watch.py` → use `pipeline_monitor.py down`
