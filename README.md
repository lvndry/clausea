<div align="center">
  <img src="packages/frontend/public/static/favicons/logo.png" alt="Clausea" width="160" />

  <h1>Clausea</h1>

  <p><strong>Policy document intelligence for SaaS products.</strong><br />
  Turn privacy policies, terms of service, and related legal pages into plain-English risk assessments.</p>

  <p>
    <a href="https://clausea.co">clausea.co</a>
    ·
    <a href="https://clausea.co/products/slack">Example report</a>
    ·
    <a href="https://github.com/lvndry/clausea/blob/main/LICENSE">AGPL-3.0</a>
  </p>

  <p>
    <a href="https://deepwiki.com/lvndry/clausea"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki" /></a>
  </p>
</div>

---

## About

Clausea crawls and analyzes policy documents — privacy policies, terms of service, cookie policies, GDPR notices, DPAs, and more — for SaaS products. It extracts structured signals (data collected, third-party sharing, user rights, retention, consent model) and synthesizes them into a **0–10 risk score**, a qualitative verdict, and decision-ready summaries.

Live product pages: `https://clausea.co/products/{slug}`
Machine-readable summaries: `https://clausea.co/api/products/{slug}/summary.txt`

## Features

| Area | What you get |
| --- | --- |
| **Whole-site coverage** | Crawls a vendor's full policy surface, not just a single pasted URL |
| **Risk scoring** | 0–10 score with grade, verdict, and score breakdown |
| **Plain-English summaries** | Consumer-friendly explainers plus detailed policy overviews |
| **Topic intelligence** | Stance and evidence across key privacy topics |
| **Compliance signals** | GDPR and CCPA-relevant clause detection |
| **Source documents** | Linked, cited policy pages behind every finding |
| **Browser extension** | Analyze policies from the toolbar ([`packages/extension`](packages/extension)) |
| **Developer API** | FastAPI backend with OpenAPI docs at `/docs` |

### Risk score scale

| Score | Verdict |
| --- | --- |
| 0–2 | Very user-friendly |
| 3–4 | User-friendly |
| 5–6 | Moderate concerns |
| 7–8 | Pervasive data collection |
| 9–10 | Very pervasive |

## Who it's for

- **Individuals** checking what an app does with their data before signing up
- **Privacy-conscious users** comparing vendor policies
- **Compliance and legal teams** auditing third-party SaaS vendors
- **Developers** building on the Clausea API or self-hosting the stack

## Repository structure

Monorepo with three packages:

```
clausea/
├── packages/
│   ├── backend/     # FastAPI API, crawler, analysis pipeline, Streamlit ops dashboard
│   ├── frontend/    # Next.js web app (marketing site + product dashboard)
│   └── extension/   # Browser extension (Chrome / Firefox via WXT)
├── Makefile         # Dev workflow shortcuts
├── dev.sh           # Starts frontend + backend together
└── AGENTS.md        # Agent / contributor guidelines
```

| Package | Stack | Docs |
| --- | --- | --- |
| [`packages/backend`](packages/backend) | Python 3.11+, FastAPI, MongoDB, LiteLLM | [Backend README](packages/backend/README.md) |
| [`packages/frontend`](packages/frontend) | Next.js, React, TypeScript, Tailwind | [Frontend README](packages/frontend/README.md) |
| [`packages/extension`](packages/extension) | WXT, TypeScript | [Extension README](packages/extension/README.md) |

## Getting started

### Prerequisites

- **Python 3.11+** with [uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** with [bun](https://bun.sh/)
- **MongoDB** (local or Atlas)
- API keys as needed: OpenAI, Anthropic, Clerk, Pinecone (see env examples)

### Setup

```bash
git clone https://github.com/lvndry/clausea.git
cd clausea
make setup
```

`make setup` installs dependencies, creates env files from examples, and configures pre-commit hooks. Run `make help` for all commands.

### Environment

```bash
# Backend — edit with MongoDB URI, LLM keys, Clerk JWKS, etc.
cp packages/backend/.env.example packages/backend/.env

# Frontend — Makefile/setup uses .env.local
cp packages/frontend/.env.example packages/frontend/.env.local
```

See [`packages/backend/.env.example`](packages/backend/.env.example) and [`packages/frontend/.env.example`](packages/frontend/.env.example) for the full variable list.

### Run locally

```bash
# Frontend + backend
make dev

# Or individually
make run-backend    # http://localhost:8000
make run-frontend   # http://localhost:3000
make dashboard      # Streamlit ops dashboard (http://localhost:8501)
```

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |
| Ops dashboard | http://localhost:8501 |

### Extension development

```bash
make setup-extension   # once
make extension-dev     # builds to packages/extension/.output/chrome-mv3
```

Load the unpacked extension from `packages/extension/.output/chrome-mv3` in `chrome://extensions`. See the [extension README](packages/extension/README.md).

## Development

```bash
make test      # backend (pytest) + frontend (vitest)
make lint      # ruff + eslint
make format    # ruff format + prettier
```

Backend-only checks (from `packages/backend`):

```bash
uv run ty check
uv run ruff check
uv run pytest
```

Contributing: fork, branch, open a PR. See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

## How it works

At a high level, indexing a product runs a three-step pipeline:

1. **Crawl** — two-pass discovery (precision-first, recall fallback) to find and persist policy pages
2. **Analyze** — evidence-first LLM extraction per document, with LiteLLM routing and fallbacks
3. **Synthesize** — product overview, topic stances, risk score, and rollup across core documents

Deep dives:

- [Crawl → pipeline workflow](packages/backend/docs/CRAWL_TO_PIPELINE_WORKFLOW.md)
- [Crawler design](packages/backend/docs/CRAWLER.md)
- [Data model](packages/backend/docs/DATA_MODEL.md)
- [Railway deployment](packages/backend/docs/RAILWAY.md)
- [Streamlit ops dashboard](packages/backend/docs/STREAMLIT_SETUP.md)

## License

[AGPL-3.0](LICENSE)

## Contact

- **Website:** [clausea.co](https://clausea.co)
- **Email:** [contact@clausea.co](mailto:contact@clausea.co)
