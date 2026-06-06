# syntax=docker/dockerfile:1

# ---- Builder stage: install dependencies into an isolated prefix ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY pyproject.toml ./
COPY backend ./backend
COPY ingestion ./ingestion
COPY README.md ./

RUN pip install --prefix=/install .

# ---- Runtime stage: minimal, non-root, no build toolchain ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_PORT=8000

# Create an unprivileged user; the app never runs as root.
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY backend ./backend
COPY ingestion ./ingestion

USER app

EXPOSE 8000

# Liveness healthcheck hits /health (NFR-009). No secrets are referenced.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else sys.exit(1)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
