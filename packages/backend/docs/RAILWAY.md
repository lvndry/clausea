# Deploying the Backend to Railway

This guide covers deploying `packages/backend` services to Railway. See also [Frontend Railway guide](../../frontend/docs/RAILWAY.md) for the Next.js app.

## Architecture

| Service            | Path               | Dockerfile           | Config              | Port / health        |
| ------------------ | ------------------ | -------------------- | ------------------- | -------------------- |
| API (FastAPI)      | `packages/backend` | `Dockerfile`         | `railway.toml`      | `$PORT`, `/health`   |
| Worker (crawler)   | `packages/backend` | `Dockerfile.worker`  | Dashboard overrides | `$PORT`, `/health`   |
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

Only one `railway.toml` can live at the service root (`packages/backend`). **Every service that shares this root reads the same file** — including its `dockerfilePath = "Dockerfile"` and `healthcheckPath = "/health"`. The API service uses these defaults; the worker and Streamlit services **must override the Dockerfile path in the Railway dashboard** (worker can keep `/health` when using `Dockerfile.worker`).

## Railway setup (dashboard)

### 1. API service

1. **New Service** → **GitHub Repo** → select `clausea`
2. Set **Root Directory** to `packages/backend`
3. Railway reads `railway.toml` and builds with `Dockerfile` automatically

| Setting        | Value                                           |
| -------------- | ----------------------------------------------- |
| Root Directory | `packages/backend`                              |
| Builder        | Dockerfile (from `railway.toml`)                |
| Start command  | *(empty — image CMD binds `${PORT}` via shell)* |
| Health check   | `/health`                                       |

`railway.toml` sets `watchPatterns = ["packages/backend/**"]` so monorepo pushes only redeploy when backend files change.

### 2. Worker service

Create a **separate service** in the same project (recommended for shared variables and networking).

| Setting        | Value                                              |
| -------------- | -------------------------------------------------- |
| Root Directory | `packages/backend`                                 |
| Dockerfile     | `Dockerfile.worker` (**override in dashboard**)    |
| Start command  | *(empty — use image CMD `python worker.py`)*       |
| Health check   | `/health` (liveness-only; optional — can disable)  |
| Replicas       | Start with **1**; scale up only after deploy succeeds |

Railway cannot read a second `railway.toml` at the same root. In the worker service dashboard:

1. **Settings → Build → Dockerfile Path** → `Dockerfile.worker` (not `Dockerfile`)
2. **Settings → Deploy → Start Command** → leave empty (image CMD `python worker.py`)
3. **Settings → Deploy → Health Check Path** → `/health` (inherits from shared `railway.toml`) or leave blank to disable

> **Common failure:** Build log shows `load build definition from packages/backend/Dockerfile` (not `Dockerfile.worker`), and deploy fails with **"N/N replicas never became healthy!"** and **"service unavailable"** on every attempt. That usually means the worker is still using the API Dockerfile/start command (uvicorn) or the wrong entrypoint — not a MongoDB issue. Fix the Dockerfile path and clear the start command. Also verify replica count: nothing in this repo sets replicas; that is a dashboard setting.

The worker image serves `GET /health` on `$PORT` (liveness-only, like the API — no MongoDB check). Railway health checks are optional; you can disable them on the worker if preferred.

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
| `PADDLE_CLIENT_TOKEN` | Paddle.js client-side token for checkout overlay (`/subscriptions/checkout-config`) |
| `PADDLE_WEBHOOK_SECRET` | Paddle webhooks        |
| `PADDLE_PRICE_PRO_MONTHLY` | Pro monthly Paddle price ID (exposed via `/subscriptions/plans`) |
| `PADDLE_PRICE_PRO_ANNUAL` | Pro annual Paddle price ID (optional) |
| `PADDLE_ENVIRONMENT` | `sandbox` or `production` |
| `RESEND_API_KEY`    | Transactional email        |

### Optional

| Variable           | Description                                      |
| ------------------ | ------------------------------------------------ |
| `PINECONE_API_KEY` | Vector search (if enabled)                       |
| `ANTHROPIC_API_KEY`| Alternate LLM provider                           |
| `SERVICE_API_KEY`  | Service-to-service auth (Streamlit → API)        |
| `CRAWLER_*`        | Crawler tuning (see `src/core/config.py`)        |

Railway sets `PORT` automatically — do not hardcode it. **Do not** set `startCommand` in shared `railway.toml`: Railway passes it to the process without shell expansion, so `--port $PORT` becomes the literal string `$PORT` and uvicorn crashloops. Each service Dockerfile CMD uses `sh -c` with `${PORT:-8000}` instead.

### Wiring frontend to API (private network)

Add a **service variable** on the API service (Railway does not infer this from runtime `PORT`):

```text
PORT=8080
```

Use the value shown in deploy logs (`Uvicorn running on http://0.0.0.0:8080` or dual-stack). On the **frontend** service:

```text
BACKEND_BASE_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}
```

Private traffic stays off the public internet (no egress billing for frontend→API hops). The API Dockerfile binds uvicorn with an empty `--host` so dual-stack listeners accept both Railway IPv4 healthchecks and private-network IPv6.

See [frontend RAILWAY.md](../../frontend/docs/RAILWAY.md).

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
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e MONGO_URI=mongodb://host.docker.internal:27017/clausea \
  -e ENVIRONMENT=development \
  -e OPENAI_API_KEY=sk-... \
  clausea-worker
curl http://localhost:8000/health
```

## Troubleshooting

| Symptom                      | Fix                                                                 |
| ---------------------------- | ------------------------------------------------------------------- |
| **"N/N replicas never became healthy"** + `/health` + `service unavailable`, build uses `Dockerfile` not `Dockerfile.worker` | **Worker misconfiguration.** Set Dockerfile to `Dockerfile.worker`, clear start command (no uvicorn). Reduce replicas to 1 until deploy passes. Not a MongoDB issue. |
| Worker deploy OK but runs API instead of crawls | Dockerfile path still `Dockerfile` (uvicorn CMD). Set `Dockerfile.worker` and clear start command. |
| API health check fails       | Deploy logs show `Invalid value for '--port': '$PORT'` → remove `startCommand` from `railway.toml` / dashboard; use Dockerfile CMD with `${PORT}`. `/health` is liveness-only. Check `MONGO_URI` for `/health/ready`. |
| Worker OOM / crashloops      | Lower `PIPELINE_WORKER_CONCURRENCY`; increase memory; add replicas after deploy succeeds |
| Worker redeploys on API push | Expected if both share root — use watch paths or separate triggers  |
| Crawls fail in worker        | Verify Camoufox libs in image; check `CRAWLER_USE_BROWSER=true`     |
| CORS errors from frontend    | Set `CORS_ORIGINS` on API to include frontend URL                   |
| Auth fails                   | Verify `CLERK_JWKS_URL` matches your Clerk instance                 |
| Frontend cannot reach API on private domain | API must use uvicorn `--host ''` (dual-stack), not `0.0.0.0` only. Set frontend `BACKEND_BASE_URL` to `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}` with `PORT` defined on the API service. |

### Why regular `Dockerfile` + `python worker.py` fails health

If the worker service still builds from the API `Dockerfile` (uvicorn entrypoint) or the start command is overridden to `python worker.py` while Railway probes a port nothing is listening on, health checks fail until timeout. Use `Dockerfile.worker` (which runs `worker.py` and serves `/health` on `$PORT`) and leave the start command empty.
