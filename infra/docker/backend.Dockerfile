# syntax=docker/dockerfile:1.7
# Multi-stage: a fat development image with dev tooling, and a slim runtime
# image that runs as a non-root user.

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq5 curl \
 && rm -rf /var/lib/apt/lists/*


FROM base AS deps
COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/README.md /app/README.md
# Install dependencies before the source so a code change does not invalidate
# the dependency layer.
RUN pip install --upgrade pip && pip install -e ".[dev]"


FROM deps AS development
COPY backend /app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


FROM base AS runtime
COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/README.md /app/README.md
RUN pip install --upgrade pip && pip install .
COPY backend /app
RUN adduser --disabled-password --gecos "" --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1
# Migrations are a separate job in production, so the container starts clean.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
