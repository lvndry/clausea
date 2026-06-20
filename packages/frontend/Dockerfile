# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM oven/bun:1 AS deps
WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# ── Stage 2: build Next.js (standalone output) ────────────────────────────────
FROM oven/bun:1 AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

# NEXT_PUBLIC_* and other build-time env vars are injected by Railway during build.
RUN bun run build

# ── Stage 3: production runtime ─────────────────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# Railway sets PORT at runtime; Next.js standalone server reads it automatically.
CMD ["node", "server.js"]
