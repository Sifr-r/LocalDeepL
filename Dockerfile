# Multi-stage Dockerfile for the OmniScribe web app.
#
# Two stages:
#   1. ``builder`` installs ``uv`` and syncs the pinned dependency set
#      + the project itself into ``/app/.venv``.
#   2. ``runtime`` copies ``/app/.venv`` from the builder; the final
#      image has no uv toolchain, no build tools, and no build cache.
#
# Defense-in-depth: the runtime image runs as a non-root ``app`` user
# (uid 1001) and binds the default web port 8000.
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
# library/python:3.14-slim. Lookup performed against
# registry-1.docker.io/v2/library/python/manifests/3.14-slim
# (Content-Type: application/vnd.oci.image.index.v1+json,
#  self-digest re-lookup consistent). Satisfies the digest-pinning
# requirement in SECURITY.md (M7).
# ---- builder stage ----
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# ``uv`` from the official standalone binary keeps the image smaller
# than pip-installing it. ``UV_VERSION`` pins the installer payload
# (audit P1-7): without it the build fetches whatever ``latest`` is,
# a moving supply-chain target. Bump deliberately, in lockstep with
# the developer toolchain.
#
# Sprint 5 / H-1 audit fix: download the installer to disk and run it
# from disk so the build fails loud on a partial download (vs.
# ``curl | sh`` which would silently pipe a half-fetched payload to
# ``sh``). ``test -s`` guards against an empty file; a non-2xx would
# also fail because the installer script exits 1.
ARG UV_VERSION=0.11.16
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" -o /tmp/uv.tar.gz \
 && test -s /tmp/uv.tar.gz \
 && tar -xzf /tmp/uv.tar.gz -C /tmp \
 && install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv \
 && install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uvx /usr/local/bin/uvx \
 && rm -rf /tmp/uv.tar.gz /tmp/uv-x86_64-unknown-linux-gnu \
 && rm -rf /root/.cache

WORKDIR /app

# Copy dependency manifest first so the install layer is cacheable
# independent of the source tree. ``--locked`` (audit P1-7) installs
# exactly the committed uv.lock set instead of re-resolving.
# ``LICENSE`` and ``README.md`` are required by hatchling during the
# project install (see ``pyproject.toml``: ``license = { file = "LICENSE" }``
# and ``readme = "README.md"``).
COPY pyproject.toml uv.lock LICENSE README.md ./
RUN mkdir -p /app/src/omniscribe \
 && touch /app/src/omniscribe/__init__.py \
 && uv sync --locked --extra web --extra async-translation --extra preprocessing --extra lexicon --no-install-project

# Copy the project source and complete the install.
COPY src ./src
RUN uv sync --locked --extra web --extra async-translation --extra preprocessing --extra lexicon \
 && rm -rf /root/.cache

# ---- runtime stage ----
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

# Drop root for runtime. The official Python slim image ships a
# ``nonroot`` user, but we create our own so the path is stable.
# ``--system`` mirrors the pre-P1-7 user (uid 1001, no interactive
# shell — the CMD is the long-running web server, not a login).
RUN groupadd --system app && useradd --system --gid app --uid 1001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Sprint 5 / H-2 audit fix: install tini as PID 1 so SIGTERM reaches
# the Python process group. Without tini, uvicorn is PID 1 inside
# the container and its default SIGTERM handler exits abruptly
# without draining WebSocket clients / running the FastAPI lifespan
# shutdown. tini is ~30 KB and well-trusted; the official Debian
# package is the simplest source. Must run as root before dropping privileges.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*

# Copy the venv and source from the builder with non-root ownership.
# D5-02 audit fix: using --chown=app:app directly avoids a redundant
# RUN chown -R layer that duplicates the ~1.5GB venv in Docker storage.
COPY --chown=app:app --from=builder /app/.venv /app/.venv
COPY --chown=app:app --from=builder /app/src ./src
COPY --chown=app:app --from=builder /app/pyproject.toml /app/uv.lock ./

RUN mkdir -p /app/data && chown -R app:app /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/data/hf

USER app

EXPOSE 8000

# F5-03 / F5-04 audit fix: ``HEALTHCHECK`` is set at the Dockerfile
# level (not just in ``compose.yaml``) so non-Compose orchestrators
# (Kubernetes liveness probes, plain Docker ``--health-cmd``,
# Nomad, ECS task definitions) can detect a half-broken process.
# The probe hits ``/api/health`` — the cheap no-I/O endpoint in
# ``src/omniscribe/plugins/health.py`` — and uses Python's
# stdlib ``urllib`` so no extra apt packages are needed (matches
# the same probe the ``compose.yaml`` ``api`` service uses).
# ``--start-period`` is generous (30s) because the first request
# to a cold container pays the model-load + import-graph setup
# cost on the synchronous OCR path.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

# Default: bind on all interfaces so the container is reachable from
# the host on non-loopback adapters. Use ``--host 127.0.0.1`` when
# running behind a reverse proxy that does not need LAN exposure.
# ``tini`` forwards SIGTERM to the web server for a clean shutdown.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["omniscribe-server", "--host", "0.0.0.0", "--port", "8000"]
