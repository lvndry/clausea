# Clausea Browser Extension

Browser extension for **Clausea – Privacy Policy Analyzer**. Analyze privacy policies and terms of service with AI directly from the toolbar.

## Prerequisites

- **Node.js** 18+ (or **Bun**)
- Package manager: `npm`, `yarn`, `pnpm`, or `bun`

## Setup

From the repo root or from this directory:

```bash
# From monorepo root
cd packages/extension
bun install   # or: npm install

# WXT generates types on install; if you skip postinstall, run:
bun run wxt prepare
```

## Dev workflow

### 1. Start the dev server

```bash
bun run dev
```

This runs WXT in development mode:

- Builds the extension into **`.output/chrome-mv3`** (Chrome/Chromium)
- Watches for file changes and rebuilds
- Serves the extension assets (dev server runs on port **3535** by default)

Keep this terminal running while developing.

### 2. Load the extension unpacked in Chrome

1. Open Chrome and go to **`chrome://extensions`**.
2. Turn **Developer mode** on (top-right toggle).
3. Click **Load unpacked**.
4. Choose the folder: **`packages/extension/.output/chrome-mv3`**
   (from the repo root: `./packages/extension/.output/chrome-mv3`)
5. The extension should appear in the list and in the toolbar.

After code changes, the dev build updates automatically. If the extension doesn’t refresh:

- Go to **`chrome://extensions`** and click the **reload** icon on the Clausea extension.

### 3. Firefox (optional)

```bash
bun run dev:firefox
```

Load the unpacked extension in Firefox:

1. Open **`about:debugging`** → **This Firefox**.
2. Click **Load Temporary Add-on**.
3. Select the **`manifest.json`** inside **`.output/firefox-mv2`** (path is created when you run `dev:firefox`).

## Scripts

| Command                 | Description                              |
| ----------------------- | ---------------------------------------- |
| `bun run dev`           | Dev build + watch (Chrome)               |
| `bun run dev:firefox`   | Dev build + watch (Firefox)              |
| `bun run build`         | Production build (Chrome)                |
| `bun run build:firefox` | Production build (Firefox)               |
| `bun run zip`           | Build and create zip for Chrome store    |
| `bun run zip:firefox`   | Build and create zip for Firefox add-ons |
| `bun run lint`          | Run ESLint                               |
| `bun run type-check`    | Run TypeScript check (no emit)           |

Production builds also go under **`.output/`** (e.g. `.output/chrome-mv3` for Chrome).

## Load unpacked (quick reference)

| Browser | Dev build path (after `bun run dev`)                           |
| ------- | -------------------------------------------------------------- |
| Chrome  | `packages/extension/.output/chrome-mv3`                        |
| Firefox | `packages/extension/.output/firefox-mv2` (use `manifest.json`) |

## Backend for development

The extension talks to the Clausea API. For local development it can use:

- **Production:** `https://api.clausea.co`
- **Local:** `http://localhost:8000` (run the backend from `packages/backend` and point the extension at it if needed)

Host permissions for both are set in the manifest.

## Optional: different icon in dev

To use a different icon only in development (e.g. a "DEV" badge), add `icon-dev/16.png`, `icon-dev/32.png`, `icon-dev/48.png`, and `icon-dev/128.png` under `public/`, then in `wxt.config.ts` use `icon-dev/` paths for `action.default_icon` and `icons` when `mode === "development"`.

## Project structure

- **`entrypoints/`** – Popup UI, background script, and other entrypoints
- **`lib/`** – Shared utilities and API client
- **`icon/`** – Extension icons
- **`wxt.config.ts`** – WXT and manifest configuration
- **`.output/`** – Build output (generated; load this folder as “unpacked”)
