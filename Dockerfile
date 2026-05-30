# syntax=docker/dockerfile:1

# -------------------------
# Build stage
# -------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

ARG TORCH_VERSION=2.11.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

# Install build dependencies (only needed for building wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install into system site-packages (/usr/local)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^torch==' requirements.txt > requirements.notorch.txt \
    && python -m pip install -r requirements.notorch.txt \
    && python -m pip install --index-url ${TORCH_INDEX_URL} torch==${TORCH_VERSION}


# -------------------------
# Runtime stage
# -------------------------
FROM python:3.11-slim

WORKDIR /app

ARG AGRI_EMBEDDING_MODEL=intfloat/multilingual-e5-small
ARG PRELOAD_AGRI_MODEL=false
ARG TORCH_VERSION=2.11.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

# Install runtime OS dependencies (PDF + OCR)
# tesseract-ocr-all: the default OCR bundle is the full EU language set
# (ALL_OCR_LANGS), so eng-only fails on non-English PDFs (e.g. Greek ->
# "Failed loading language 'ell'"). Swap to specific packs if you want a leaner image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-all \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV AGRI_EMBEDDING_MODEL=${AGRI_EMBEDDING_MODEL}
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Copy installed Python deps from builder (system-wide)
COPY --from=builder /usr/local /usr/local

# Pre-download the agriculture embedding model so first inference is warm.
RUN --mount=type=cache,target=/app/.cache/huggingface \
    mkdir -p /app/.cache/huggingface \
    && if [ "${PRELOAD_AGRI_MODEL}" = "true" ]; then \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${AGRI_EMBEDDING_MODEL}', device='cpu')"; \
       else \
        echo 'Skipping agriculture embedding predownload'; \
       fi

# Copy application code
COPY app.py .
COPY docint/ ./docint/
COPY data_model/ ./data_model/
COPY visualisations/ ./visualisations/

# Create non-root user for security
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/.cache/huggingface \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck: /health is intentionally unauthenticated for local/container probes.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Run the application (module form avoids PATH/script issues)
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
