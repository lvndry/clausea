# Deploying the Backend to Railway

This guide covers deploying `packages/backend` services to Railway. See also [Frontend Railway guide](../../frontend/docs/RAILWAY.md) for the Next.js app.

## Architecture

| Service            | Path               | Dockerfile           | Config              | Port / health        |
| ------------------ | ------------------ | -------------------- | ------------------- | -------------------- |
| API (FastAPI)      | `packages/backend` | `Dockerfile`         | `railway.toml`      | `$PORT`, `/health`   |
| Worker (crawler)   | `packages/backend` | `Dockerfile.worker`  | Dashboard overrides | No HTTP (no probe)   |
| Streamlit (optional) | `packages/backend` | `Dockerfile.streamlit` | Dashboard overrides | `$PORT`, `/_stcore/health` |

The API serves user-facing requests. The worker runs pipeline jobs (crawls, parsing, LLM calls) out of process so heavy work never blocks the API. Streamlit is an optional internal admin dashboard.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│  API        │     │  Streamlit  │
│  (Next.js)  │     │  (FastAPI)  │     │  (optional) │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐       MongoDB Atlas
                    │   Worker    │──────────────┘
                    │  (crawler)  │
                    └─────────────┘
```

Only one `railway.toml` can live at the service root. The API service uses it; the worker and Streamlit services configure their Dockerfile in the Railway dashboard.

## Railway setup (dashboard)

### 1. API service

1. **New Service** → **GitHub Repo** → select `clausea`
2. Set **Root Directory** to `packages/backend`
3. Railway reads `railway.toml` and builds with `Dockerfile` automatically

| Setting        | Value                                           |
| -------------- | ----------------------------------------------- |
| Root Directory | `packages/backend`                              |
| Builder        | Dockerfile (from `railway.toml`)                |
| Start command  | From `railway.toml` (`uvicorn … --port $PORT`)  |
| Health check   | `/health`                                       |

`railway.toml` sets `watchPatterns = ["packages/backend/**"]` so monorepo pushes only redeploy when backend files change.

### 2. Worker service

Create a **separate service** in the same project (recommended for shared variables and networking).

| Setting        | Value                                              |
| -------------- | -------------------------------------------------- |
| Root Directory | `packages/backend`                                 |
| Dockerfile     | `Dockerfile.worker` (override in dashboard)        |
| Start command  | *(empty — use image CMD `python worker.py`)*       |
| Health check   | **Disabled** (worker has no HTTP endpoint)         |

Railway cannot read a second `railway.toml` at the same root. Set **Settings → Build → Dockerfile Path** to `Dockerfile.worker` manually.

The worker image is identical to the API image except for the entrypoint. It needs Camoufox/Firefox runtime libraries for headless crawls.

**Worker tuning (optional env vars):**

| Variable                            | Default | Description                          |
| ----------------------------------- | ------- | ------------------------------------ |
| `PIPELINE_WORKER_CONCURRENCY`       | `3`     | Max jobs running at once             |
| `PIPELINE_WORKER_POLL_SECONDS`      | `3`     | Idle poll interval                   |
| `PIPELINE_WORKER_STALE_SWEEP_SECONDS` | `300` | How often to reap orphaned jobs      |

Allocate more memory for the worker than the API (512MB–1GB+); Camoufox crawls are memory-heavy.

### 3. Streamlit service (optional)

For an internal admin dashboard, add another service:

| Setting        | Value                                                                 |
| -------------- | --------------------------------------------------------------------- |
| Root Directory | `packages/backend`                                                    |
| Dockerfile     | `Dockerfile.streamlit`                                                |
| Start command  | `streamlit run src/dashboard/app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true` |
| Health check   | `/_stcore/health`                                                     |

Restrict access via Railway networking or VPN; do not expose publicly unless required.

## Environment variables

Set variables on the **API** and **worker** services (share via Railway shared variables or copy manually). The worker needs database and LLM keys; it does not need Clerk JWT or CORS settings for normal operation.

### Required (API + worker)

| Variable         | Description                                      |
| ---------------- | ------------------------------------------------ |
| `MONGO_URI`      | MongoDB Atlas connection string                  |
| `ENVIRONMENT`    | `production` in Railway                          |
| `OPENAI_API_KEY` | LLM provider (or other keys your deployment uses) |

### Required (API only)

| Variable          | Description                                    |
| ----------------- | ---------------------------------------------- |
| `CLERK_JWKS_URL`  | Clerk JWKS URL for JWT validation              |
| `CORS_ORIGINS`    | Frontend origins, e.g. `https://clausea.co`  |

### Recommended (API)

| Variable            | Description                |
| ------------------- | -------------------------- |
| `POSTHOG_API_KEY`   | Product analytics          |
| `PADDLE_API_KEY`    | Billing                    |
| `PADDLE_WEBHOOK_SECRET` | Paddle webhooks        |
| `RESEND_API_KEY`    | Transactional email        |

### Optional

| Variable           | Description                                      |
| ------------------ | ------------------------------------------------ |
| `PINECONE_API_KEY` | Vector search (if enabled)                       |
| `ANTHROPIC_API_KEY`| Alternate LLM provider                           |
| `SERVICE_API_KEY`  | Service-to-service auth (Streamlit → API)        |
| `CRAWLER_*`        | Crawler tuning (see `src/core/config.py`)        |

Railway sets `PORT` automatically — do not hardcode it. The API `railway.toml` start command binds to `$PORT`.

### Wiring frontend to API

If the frontend service is named `frontend`:

```text
BACKEND_BASE_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
```

Set on the **frontend** service. See [frontend RAILWAY.md](../../frontend/docs/RAILWAY.md).

## CLI deploy (alternative)

From the backend directory, link each service separately:

```bash
cd packages/backend
railway link          # link to project + api service
railway up --detach -m "Deploy API"
```

For the worker, switch the linked service in the dashboard or CLI, then deploy with Dockerfile.worker configured in the service settings.

## Local Docker smoke test

**API:**

```bash
cd packages/backend
docker build -t clausea-api .
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e MONGO_URI=mongodb://host.docker.internal:27017/clausea \
  -e ENVIRONMENT=development \
  clausea-api
curl http://localhost:8000/health
```

**Worker:**

```bash
cd packages/backend
docker build -f Dockerfile.worker -t clausea-worker .
docker run --rm \
  -e MONGO_URI=mongodb://host.docker.internal:27017/clausea \
  -e ENVIRONMENT=development \
  -e OPENAI_API_KEY=sk-... \
  clausea-worker
```

## Troubleshooting

| Symptom                      | Fix                                                                 |
| ---------------------------- | ------------------------------------------------------------------- |
| API health check fails       | Confirm start command uses `$PORT`; `/health` is liveness-only (200 even while DB warms up). Check deploy logs for missing `MONGO_URI` or MongoDB connectivity; use `/health/ready` for readiness. |
| Worker OOM / crashloops      | Lower `PIPELINE_WORKER_CONCURRENCY`; increase memory; add replicas  |
| Worker redeploys on API push | Expected if both share root — use watch paths or separate triggers  |
| Crawls fail in worker        | Verify Camoufox libs in image; check `CRAWLER_USE_BROWSER=true`     |
| CORS errors from frontend    | Set `CORS_ORIGINS` on API to include frontend URL                   |
| Auth fails                   | Verify `CLERK_JWKS_URL` matches your Clerk instance                 |
