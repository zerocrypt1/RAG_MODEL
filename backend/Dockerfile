# ─────────────────────────────────────────────────────────
# RAG PDF App — Backend Dockerfile
# Build:  docker build -t rag-backend .
# Run:    docker run -p 5000:5000 --env-file .env rag-backend
# ─────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System dependencies for FAISS, psycopg2, and PDF parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies ───────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────
COPY . .

# ── Directories ───────────────────────────────────────────
RUN mkdir -p /tmp/vector_stores \
    && mkdir -p /app/instance          # SQLite db location

# ── Non-root user (security best practice) ───────────────
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app /tmp/vector_stores
USER appuser

# ── Port ─────────────────────────────────────────────────
EXPOSE 5000

# ── Healthcheck ───────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# ── Run ───────────────────────────────────────────────────
# 4 workers, 120-second timeout (RAG can take a while on first load)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "run:app"]