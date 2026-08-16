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

# Pinned: 2026-08-16 to a verified Docker Hub OCI image-index digest for
# library/python:3.12-slim. Lookup performed against
# registry-1.docker.io/v2/library/python/manifests/3.12-slim
# (Content-Type: application/vnd.oci.image.index.v1+json,
#  self-digest re-lookup consistent). Satisfies the digest-pinning
# requirement in SECURITY.md (M7).
FROM python:3.12-slim@sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65 AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# ``uv`` from the official standalone binary keeps the image smaller
# than pip-installing it. ``UV_VERSION`` pins the installer payload
# (audit P1-7): without it the build fetches whatever ``latest`` is,
# a moving supply-chain target. Bump deliberately, in lockstep with
# the developer toolchain.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_VERSION=0.11.16 sh

WORKDIR /app

# Copy dependency manifest first so the install layer is cacheable
# independent of the source tree. ``--locked`` (audit P1-7) installs
# exactly the committed uv.lock set instead of re-resolving.
COPY pyproject.toml uv.lock ./
RUN mkdir -p /app/src/omniscribe \
 && touch /app/src/omniscribe/__init__.py \
 && uv sync --locked --extra web --extra async-translation --extra preprocessing --no-install-project

# Copy the project source and complete the install.
COPY src ./src
RUN uv sync --locked --extra web --extra async-translation --extra preprocessing

# Drop root for runtime. The official Python slim image ships a
# ``nonroot`` user, but we create our own so the path is stable.
RUN groupadd --system app && useradd --system --gid app --uid 1001 app \
 && chown -R app:app /app
USER app

EXPOSE 8000

# Surface the uv-managed venv bin directory on PATH so the bare
# ``omniscribe-server`` / ``celery`` entrypoints resolve at runtime
# (uv installs to /app/.venv per UV_PROJECT_ENVIRONMENT above, but
# does not add it to PATH for us).
ENV PATH="/app/.venv/bin:$PATH"

# Default: bind on all interfaces so the container is reachable from
# the host on non-loopback adapters. Use ``--host 127.0.0.1`` when
# running behind a reverse proxy that does not need LAN exposure.
CMD ["omniscribe-server", "--host", "0.0.0.0", "--port", "8000"]
