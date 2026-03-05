# ── Stage 1: builder ─────────────────────────────────────────────────────────
# Installs build-time tools, compiles Python dependencies, and fetches the
# Camoufox Firefox binary. Nothing from this stage leaks into the final image.
FROM python:3.11-slim AS builder

ENV VENV_PATH="/opt/venv"
ENV PATH="$VENV_PATH/bin:$PATH"
# Pin the Camoufox data directory to a known path so the binary is easy to
# COPY into the final stage, regardless of the container's HOME.
ENV XDG_DATA_HOME="/opt/camoufox-data"

RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.9
RUN uv venv $VENV_PATH

COPY pyproject.toml ./
COPY uv.lock ./

RUN --mount=type=cache,id=cacheKey-uv-cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=300 UV_RETRIES=5 uv sync --no-dev --frozen

# Download the Camoufox Firefox binary at build time (stored at $XDG_DATA_HOME/camoufox).
# Running this here avoids any network call at container startup.
RUN uv run camoufox fetch

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
# Clean image containing only the venv, the Camoufox binary, runtime system
# libraries, and application code. Build tools (gcc, libffi-dev, uv) are absent.
FROM python:3.11-slim

ENV VENV_PATH="/opt/venv"
ENV PATH="$VENV_PATH/bin:$PATH"
ENV PYTHONPATH="/app"
ENV XDG_DATA_HOME="/opt/camoufox-data"

# Runtime-only system libraries required by the Camoufox Firefox binary.
# These satisfy the dynamic linker at process start; they are not used
# during headless operation but Firefox links against them unconditionally.
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libx11-6 \
    libxcb1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy compiled Python environment (no build tools, only runtime packages).
COPY --from=builder /opt/venv /opt/venv

# Copy the pre-fetched Camoufox Firefox binary.
COPY --from=builder /opt/camoufox-data /opt/camoufox-data

COPY . .

EXPOSE 8000

# Exec form: uvicorn runs as PID 1 so Railway's SIGTERM is delivered directly.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
