# ============================================================
# Production Dockerfile — Multi-Agent Shopping Assistant
# Day09 (LangGraph + ChromaDB + FastAPI) → Railway deployment
# Multi-stage build, < 600 MB, non-root user
# ============================================================

# ── Stage 1: Builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for chromadb / sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system deps for numpy / onnxruntime inside sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /app/.local

# Copy application code
COPY app/       ./app/
COPY rag/       ./rag/
COPY provider/  ./provider/
COPY data/      ./data/
COPY api.py     ./api.py

# Pre-populate .chroma if it exists (optional — speeds up cold start)
# COPY .chroma/  ./.chroma/

RUN chown -R agent:agent /app

USER agent

ENV PATH=/app/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Liveness check
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Railway injects $PORT; default to 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
