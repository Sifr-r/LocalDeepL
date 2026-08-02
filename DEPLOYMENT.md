# Deployment Guide

This document walks through deploying LocalDeepL in three common
profiles. **Start at the top, stop at the profile that matches your
use case.** The local-desktop default is correct for almost every
user; only step up to LAN / public-internet when you actually need
to.

## Profile 1: Local Desktop (Default)

You're running LocalDeepL on your own laptop. You open the browser to
`http://localhost:8000` and use it.

```bash
uv sync --extra web
uv run local-deepl-server --port 8000
```

That's it. No auth, no reverse proxy, no Docker. The Settings tab
points at `http://localhost:1234/v1` (LM Studio) by default; start
LM Studio, load a model, OCR.

**What you get:**

- All guards on (rate limit, upload cap, SSRF, placeholder-token
  rejection) but **no** bearer-token auth. Any process that can
  reach `localhost:8000` is trusted.
- Documents stay on disk until cleaned up by the startup sweep
  (`M6`).
- The VLM endpoint defaults to LM Studio on `localhost:1234`; if
  you point it at a third-party provider, see "Third-party VLM"
  below.

## Profile 2: LAN / Trusted Network

You have a small home-lab or office server. You want to reach it from
your laptop on the same Wi-Fi.

```bash
export LOCAL_DEEPL_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export ALLOW_SSRF_LOCAL=false
export LOCAL_DEEPL_MAX_UPLOAD_MB=2048
export LOCAL_DEEPL_RATE_LIMIT_PER_MIN=30
uv run local-deepl-server --host 0.0.0.0 --port 8000
```

Add the bearer token to the Settings tab's "API Token" field on each
client machine. The frontend stores it in `localStorage` so it
persists across reloads (per-origin only).

**What changed from profile 1:**

- `LOCAL_DEEPL_AUTH_TOKEN` is required for every HTTP route. The
  WebSocket handshake also requires the per-channel session token
  (`X-Session-Token`).
- `ALLOW_SSRF_LOCAL=false` blocks the URL fetcher from reaching
  `localhost` / private IPs. Only public URLs work.
- The upload cap drops to 2 GB and the rate limit to 30/min — adjust
  to taste.

## Profile 3: Public Internet (Reverse Proxy)

You're hosting LocalDeepL on a VPS or behind a domain. **Do not skip
the reverse proxy** — LocalDeepL ships no TLS termination and you do
not want credentials in cleartext on a public IP.

The reference deployment uses [Caddy](https://caddyserver.com/) for
TLS + basic auth fallback + automatic HTTPS. nginx or Traefik work
the same way.

### Caddyfile

```caddy
localdeepl.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```

### docker-compose.yml

```yaml
services:
  api:
    image: ghcr.io/sifr-r/localdeepl:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"   # M9: localhost only
    environment:
      LOCAL_DEEPL_AUTH_TOKEN: "${LOCAL_DEEPL_AUTH_TOKEN:?required}"
      ALLOW_SSRF_LOCAL: "false"
      LOCAL_DEEPL_MAX_UPLOAD_MB: "1024"
      LOCAL_DEEPL_RATE_LIMIT_PER_MIN: "30"
      LLM_API_BASE: "${LLM_API_BASE:-http://host.docker.internal:1234/v1}"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

The `healthcheck` block (M11) lets Docker restart the container on
silent crashes; configure your orchestrator accordingly.

### Generate a Token

```bash
export LOCAL_DEEPL_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
echo "$LOCAL_DEEPL_AUTH_TOKEN" >> ~/.config/localdeepl/token
```

The placeholder-check (M10) refuses to start if the value is the
example `change-me-in-prod` or any other known placeholder.

### Per-service tokens (optional)

If you want OCR and translation to accept different tokens (e.g. a
read-only OCR key for an internal script):

```bash
export LOCAL_DEEPL_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
export LOCAL_DEEPL_TRANSLATION_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
```

Routes under `/api/process*`, `/api/models/ocr*`, `/api/config/ocr*`
require the OCR token (or fall back to the global token). Routes
under `/api/translate*`, `/api/extract*`, `/api/export*`,
`/api/glossary*` require the translation token. All other routes
require the global token.

## Third-party VLM (OpenAI / Anthropic / Groq)

To send OCR images to a hosted VLM instead of LM Studio:

1. Set `LLM_API_BASE` to the provider's OpenAI-compatible endpoint
   (e.g. `https://api.openai.com/v1`).
2. Set `LLM_API_KEY` to your provider key.
3. Set `LLM_MODEL` to the model ID you have access to (e.g.
   `gpt-4o-mini`).

The Settings tab also exposes per-service auth tokens so you can
configure OCR and translation backends independently.

**Privacy warning:** documents and extracted text leave your machine
when you point at a third-party endpoint. Review the provider's
data-retention policy before uploading sensitive material.

## Async Translation (Celery + Redis)

The synchronous `/api/translate` endpoint works without any extra
infrastructure. To use `/api/translate/async` (which survives worker
restarts and exposes long-poll status):

```bash
uv sync --extra async-translation --extra memory
docker compose --profile async up -d   # adds the celery worker
```

Set `REDIS_URL=redis://redis:6379/0` and the worker connects
automatically. See `compose.yaml` for the full layout.

## Backup & Recovery

LocalDeepL keeps all job artifacts in process memory
(`api/routers/state.py`). **A restart loses history.** There is no
on-disk job database in the current release.

If you need durable history, the only path is to swap
`LocalStateBackend` for a Redis-backed `StateBackend`. That is a
deliberate single-file change — see `api/services/state_backend.py`
for the protocol.

## Upgrading

1. `uv sync` (or `docker compose pull`)
2. `uv run local-deepl-server` (or `docker compose up -d`)
3. Visit `/api/health` to confirm the new version
4. Review the [CHANGELOG](CHANGELOG.md) for breaking changes

The settings tab persists user preferences via `localStorage`, not
server-side state. A version upgrade does not lose user settings.

## Uninstall

```bash
# Local install
uv pip uninstall local-deepl

# Docker
docker compose down --rmi all --volumes
```

Job artifacts in `/tmp/ocr_*` are removed by the startup sweep
(M6); manual cleanup is rarely needed.

## See Also

- [SECURITY.md](SECURITY.md) — threat model, hardening checklist,
  vulnerability disclosure
- [ARCHITECTURE.md](ARCHITECTURE.md) — component map and API
  surface
- [AGENTS.md](AGENTS.md) — contributor guide and full env-var
  reference