# Deploying the Frontend to Railway

This guide covers deploying `packages/frontend` (Next.js) to Railway alongside the existing backend service.

## Architecture

| Service             | Path                | Builder                         | Port                       |
| ------------------- | ------------------- | ------------------------------- | -------------------------- |
| Frontend (this app) | `packages/frontend` | Dockerfile (standalone Next.js) | `$PORT` (Railway-assigned) |
| Backend API         | `packages/backend`  | Dockerfile                      | `8000` or `$PORT`          |

The frontend proxies API requests server-side via `BACKEND_BASE_URL`. Browser clients never call the backend directly for authenticated routes.

## Railway setup (dashboard)

### 1. Create or use an existing project

If the backend is already on Railway, add a **new service** to the same project (recommended for shared networking and variables).

### 2. Connect the GitHub repo

1. **New Service** → **GitHub Repo** → select `clausea`
2. Set **Root Directory** to `packages/frontend`
3. Railway reads `railway.toml` and builds with the Dockerfile automatically

### 3. Configure the service

| Setting        | Value                              |
| -------------- | ---------------------------------- |
| Root Directory | `packages/frontend`                |
| Builder        | Dockerfile (from `railway.toml`)   |
| Watch paths    | Default (scoped to root directory) |

No custom build or start command is needed — the Dockerfile handles install, build, and `node server.js`.

### 4. Set environment variables

Set these in the Railway dashboard for the **frontend service**. Variables marked **build** must be present before the first deploy (Next.js inlines `NEXT_PUBLIC_*` at build time).

#### Required

| Variable                            | Build | Description                                    |
| ----------------------------------- | ----- | ---------------------------------------------- |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes   | Clerk publishable key for auth UI              |
| `CLERK_SECRET_KEY`                  | No    | Clerk secret key for server-side auth          |
| `NEXT_PUBLIC_APP_URL`               | Yes   | Public site URL, e.g. `https://clausea.co`     |
| `BACKEND_BASE_URL`                  | No    | Backend API URL, e.g. `https://api.clausea.co` |

#### Recommended

| Variable                   | Build | Description                                   |
| -------------------------- | ----- | --------------------------------------------- |
| `NEXT_PUBLIC_POSTHOG_KEY`  | Yes   | PostHog project API key                       |
| `NEXT_PUBLIC_POSTHOG_HOST` | Yes   | PostHog host, e.g. `https://eu.i.posthog.com` |
| `LOGO_DEV_API_KEY`         | No    | Logo.dev token for product logos API route    |

#### Optional

| Variable                                      | Build | Description                    |
| --------------------------------------------- | ----- | ------------------------------ |
| `NEXT_PUBLIC_PADDLE_PRICE_PRO_MONTHLY`        | Yes   | Paddle price ID for Pro plan   |
| `NEXT_PUBLIC_PADDLE_PRICE_INDIVIDUAL_MONTHLY` | Yes   | Legacy alias for Pro price ID  |
| `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION`        | Yes   | Google Search Console meta tag |
| `NEXT_PUBLIC_BING_VERIFICATION`               | Yes   | Bing Webmaster meta tag        |

Railway sets `PORT`, `NODE_ENV`, and `RAILWAY_*` automatically — do not override `PORT`.

#### Wiring to the backend on Railway

If the backend service is named `api` (adjust to match your service name):

```text
BACKEND_BASE_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
```

Or use the production custom domain:

```text
BACKEND_BASE_URL=https://api.clausea.co
```

### 5. Custom domain

1. **Settings** → **Networking** → **Custom Domain**
2. Add `clausea.co` and `www.clausea.co`
3. Update DNS (CNAME to Railway's target)
4. Set `NEXT_PUBLIC_APP_URL=https://clausea.co` and **redeploy** (build-time var)

### 6. Clerk configuration

In the [Clerk Dashboard](https://dashboard.clerk.com), add the Railway/production URLs:

- Sign-in redirect: `https://clausea.co`
- Allowed origins: `https://clausea.co`, `https://www.clausea.co`

### 7. Backend CORS (if applicable)

Ensure the backend `CORS_ORIGINS` includes the frontend origin:

```text
CORS_ORIGINS=https://clausea.co,https://www.clausea.co
```

## CLI deploy (alternative)

From the frontend directory:

```bash
cd packages/frontend
railway link          # link to project + service
railway up --detach -m "Deploy frontend"
```

## Local Docker smoke test

```bash
cd packages/frontend
docker build -t clausea-frontend .
docker run --rm -p 3000:3000 \
  -e PORT=3000 \
  -e BACKEND_BASE_URL=http://host.docker.internal:8000 \
  -e NEXT_PUBLIC_APP_URL=http://localhost:3000 \
  -e NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_... \
  -e CLERK_SECRET_KEY=sk_test_... \
  clausea-frontend
```

## Migrating from Vercel

1. Deploy to Railway and verify on the `*.up.railway.app` URL
2. Point DNS for `clausea.co` from Vercel to Railway
3. Update Clerk allowed origins if the domain changed during testing
4. Remove or archive the Vercel project once traffic is stable
5. Update the privacy policy (already references Railway for backend; frontend now on Railway too)

## Troubleshooting

| Symptom                       | Fix                                                                                                                                                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth broken in production     | Verify `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` was set **before** build; redeploy after adding it                                                                                                                   |
| API calls fail                | Check `BACKEND_BASE_URL` points to the live backend; verify backend CORS                                                                                                                                        |
| Empty products / ECONNREFUSED | Do **not** set `BACKEND_BASE_URL` to `https://*.railway.internal` — private domains use HTTP on the service `$PORT`, not HTTPS on 443. Use `https://${{api.RAILWAY_PUBLIC_DOMAIN}}` or `https://api.clausea.co` |
| Wrong canonical URLs in SEO   | Set `NEXT_PUBLIC_APP_URL` and redeploy                                                                                                                                                                          |
| Container exits immediately   | Check deploy logs; ensure `output: "standalone"` is in `next.config.mjs`                                                                                                                                        |
| Health check fails            | Railway probes `/`; ensure the app binds to `0.0.0.0` (handled by Dockerfile `HOSTNAME`)                                                                                                                        |
