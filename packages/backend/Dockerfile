# ── Stage 1: builder ─────────────────────────────────────────────────────────
# Installs build-time tools, compiles Python dependencies, and fetches the
# Camoufox Firefox binary. Nothing from this stage leaks into the final image.
FROM python:3.11-slim AS builder

ENV VENV_PATH="/opt/venv"
ENV PATH="$VENV_PATH/bin:$PATH"
# UV_PROJECT_ENVIRONMENT tells uv sync where to create/use the project venv.
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
# Camoufox uses XDG_CACHE_HOME to determine where to install the browser binary.
# Pin it to a known path so the COPY into the final stage is predictable.
ENV XDG_CACHE_HOME="/opt/camoufox-cache"

RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.9

COPY pyproject.toml ./
COPY uv.lock ./

# --no-install-project skips building the local `clausea` package (source isn't
# copied here). All external dependencies are still installed into /opt/venv.
RUN uv sync --no-dev --frozen --no-install-project && uv cache clean

# Download the Camoufox Firefox binary at build time (stored at $XDG_DATA_HOME/camoufox).
# Running this here avoids any network call at container startup.
RUN /opt/venv/bin/camoufox fetch

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
# Clean image containing only the venv, the Camoufox binary, runtime system
# libraries, and application code. Build tools (gcc, libffi-dev, uv) are absent.
FROM python:3.11-slim

ENV VENV_PATH="/opt/venv"
ENV PATH="$VENV_PATH/bin:$PATH"
ENV PYTHONPATH="/app"
ENV XDG_CACHE_HOME="/opt/camoufox-cache"

# Runtime-only system libraries required by the Camoufox Firefox binary.
# These satisfy the dynamic linker at process start; they are not used
# during headless operation but Firefox links against them unconditionally.
RUN apt-get update && apt-get install -y \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo-gobject2 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdbus-glib-1-2 \
    libdrm2 \
    libfontconfig1 \
    libfreetype6 \
    libgbm1 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libgtk-3-0 \
    libharfbuzz0b \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb-shm0 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the compiled virtual environment (all external deps, no local package).
COPY --from=builder /opt/venv /opt/venv

# Copy the pre-fetched Camoufox Firefox binary (stored under XDG_CACHE_HOME).
COPY --from=builder /opt/camoufox-cache /opt/camoufox-cache

COPY . .

EXPOSE 8000

# Exec form: uvicorn runs as PID 1 so Railway's SIGTERM is delivered directly.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
