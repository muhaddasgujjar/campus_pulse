# syntax=docker/dockerfile:1
# Campus Pulse AI API image (OPS-1). Build context: apps/api
#   docker build -f infra/Dockerfile -t campus-pulse-api apps/api
# Targets Render free (512 MB RAM): one uvicorn worker, no ML libraries, non-root user.

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.12.23

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---- build: resolve and install dependencies into /opt/venv ----
FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- runtime: slim image with only the venv and the app code ----
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz\", timeout=2)"]
# Render injects PORT. One worker keeps memory inside the 512 MB free plan.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT}\" --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
