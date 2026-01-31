FROM python:3.12.8-slim AS base

WORKDIR /app

# Install system deps for audio (no PortAudio needed - telephony uses WebSocket)
RUN apt-get update && apt-get install -y     libsndfile1     ffmpeg     && rm -rf /var/lib/apt/lists/*

# Install uv - pin specific version for reproducibility
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (--frozen ensures uv.lock is used exactly)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY config/ ./config/

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
