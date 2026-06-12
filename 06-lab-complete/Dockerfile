# ============================================================
# Production Dockerfile — VinUni AI Handbook Chatbot
# Day06 (Flask + FAISS + LangChain + Gemini) → Railway deployment
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# System deps required by unstructured (PDF parsing)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        poppler-utils \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/      ./agent/
COPY tools/      ./tools/
COPY data/       ./data/
COPY css/        ./css/
COPY images/     ./images/
COPY index.html  ./index.html
COPY main.py     ./main.py

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8080

# Railway injects $PORT; gunicorn is more production-ready than Flask dev server
CMD ["sh", "-c", "gunicorn main:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120"]
