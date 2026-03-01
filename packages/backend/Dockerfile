FROM python:3.11-slim

ENV VENV_PATH="/opt/venv"
ENV PATH="$VENV_PATH/bin:$PATH"
ENV PYTHONPATH="/app"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libffi-dev \
    # System libraries required by Camoufox (Firefox-based headless browser)
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

RUN pip install --no-cache-dir uv==0.9
RUN uv venv $VENV_PATH

COPY pyproject.toml ./
COPY uv.lock ./

RUN uv sync --no-dev --frozen

# Download the Camoufox Firefox binary at build time so it is available at runtime
RUN uv run camoufox fetch

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port 8000"]
