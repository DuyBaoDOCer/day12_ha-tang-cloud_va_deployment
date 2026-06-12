# ============================================================
# Production Dockerfile — Multi-Agent Shopping Assistant
# Day09 (LangGraph + ChromaDB + FastAPI) → Railway deployment
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

# Pre-download the sentence-transformers model during build
# so it's baked into the image (no runtime download needed)
ENV PATH=/root/.local/bin:$PATH
ENV HF_HOME=/build/hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"


# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user with a proper home directory for cache
RUN groupadd -r agent && useradd -r -g agent -m -d /home/agent agent

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /app/.local

# Copy pre-downloaded HuggingFace model cache from builder
COPY --from=builder /build/hf_cache /home/agent/.cache/huggingface

# Copy application code
COPY app/       ./app/
COPY rag/       ./rag/
COPY provider/  ./provider/
COPY data/      ./data/
COPY api.py     ./api.py

# Fix ownership: app dir + agent home (for model cache writes)
RUN chown -R agent:agent /app /home/agent

USER agent

ENV PATH=/app/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/home/agent/.cache/huggingface
ENV TRANSFORMERS_OFFLINE=1

EXPOSE 8000

# No Dockerfile HEALTHCHECK — Railway uses railway.toml healthcheckPath instead
# Railway injects $PORT; default to 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
