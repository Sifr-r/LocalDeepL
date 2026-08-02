# Multi-stage Dockerfile for the OmniScribe web app.
#
# Two stages:
#   1. ``runtime-base`` installs ``uv`` and the pinned dependency set.
#   2. ``app`` copies the project source and runs the server.
#
# Extras baked in: ``web`` (FastAPI / uvicorn) + ``async-translation``
# (Celery + Redis + LangGraph) so the same image is usable for both the
# API service and the worker. Drop ``--extra async-translation`` from
# the ``uv sync`` line if you only need the synchronous HTTP surface.
#
# For GPU / CUDA support: replace the base with
# ``nvidia/cuda:...runtime-cudnn*`` and install ``torch`` matching the
# CUDA major version. Out of scope for this template.

FROM python:3.12-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# ``uv`` from the official standalone binary keeps the image smaller
# than pip-installing it. The slice below is the recommended one.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

WORKDIR /app

# Copy dependency manifest first so the install layer is cacheable
# independent of the source tree.
COPY pyproject.toml uv.lock ./
RUN mkdir -p /app/src/omniscribe \
 && touch /app/src/omniscribe/__init__.py \
 && uv sync --extra web --extra async-translation --no-install-project

# Copy the project source and complete the install.
COPY src ./src
RUN uv sync --extra web --extra async-translation

# Drop root for runtime. The official Python slim image ships a
# ``nonroot`` user, but we create our own so the path is stable.
RUN groupadd --system app && useradd --system --gid app --uid 1001 app \
 && chown -R app:app /app
USER app

EXPOSE 8000

# Default: bind on all interfaces so the container is reachable from
# the host on non-loopback adapters. Use ``--host 127.0.0.1`` when
# running behind a reverse proxy that does not need LAN exposure.
CMD ["omniscribe-server", "--host", "0.0.0.0", "--port", "8000"]
