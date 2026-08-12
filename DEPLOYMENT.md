# Deployment Guide

This document walks through deploying OmniScribe in three common
profiles. **Start at the top, stop at the profile that matches your
use case.** The local-desktop default is correct for almost every
user; only step up to LAN / public-internet when you actually need
to.

## Profile 1: Local Desktop (Default)

You're running OmniScribe on your own laptop. You open the browser to
`http://localhost:8000` and use it.

```bash
uv sync --extra web
uv run omniscribe-server --port 8000
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
export OMNISCRIBE_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export ALLOW_SSRF_LOCAL=false
export OMNISCRIBE_MAX_UPLOAD_MB=2048
export OMNISCRIBE_RATE_LIMIT_PER_MIN=30
uv run omniscribe-server --host 0.0.0.0 --port 8000
```

Add the bearer token to the Settings tab's "API Token" field on each
client machine. The frontend stores it in `localStorage` so it
persists across reloads (per-origin only).

**What changed from profile 1:**

- `OMNISCRIBE_AUTH_TOKEN` is required for every HTTP route. The
  WebSocket handshake also requires the per-channel session token
  (`X-Session-Token`).
- `ALLOW_SSRF_LOCAL=false` blocks the URL fetcher from reaching
  `localhost` / private IPs. Only public URLs work.
- The upload cap drops to 2 GB and the rate limit to 30/min — adjust
  to taste.

## Profile 3: Public Internet (Reverse Proxy)

You're hosting OmniScribe on a VPS or behind a domain. **Do not skip
the reverse proxy** — OmniScribe ships no TLS termination and you do
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
      OMNISCRIBE_AUTH_TOKEN: "${OMNISCRIBE_AUTH_TOKEN:?required}"
      ALLOW_SSRF_LOCAL: "false"
      OMNISCRIBE_MAX_UPLOAD_MB: "1024"
      OMNISCRIBE_RATE_LIMIT_PER_MIN: "30"
      LLM_API_BASE: "${OMNISCRIBE_LLM_API_BASE:-http://host.docker.internal:1234/v1}"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

The `healthcheck` block (M11) lets Docker restart the container on
silent crashes; configure your orchestrator accordingly.

### Generate a Token

```bash
export OMNISCRIBE_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
echo "$OMNISCRIBE_AUTH_TOKEN" >> ~/.config/localdeepl/token
```

The placeholder-check (M10) refuses to start if the value is the
example `change-me-in-prod` or any other known placeholder.

### Per-service tokens (optional)

If you want OCR and translation to accept different tokens (e.g. a
read-only OCR key for an internal script):

```bash
export OMNISCRIBE_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
export OMNISCRIBE_TRANSLATION_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
```

Routes under `/api/process*`, `/api/models/ocr*`, `/api/config/ocr*`
require the OCR token (or fall back to the global token). Routes
under `/api/translate*`, `/api/extract*`, `/api/export*`,
`/api/glossary*` require the translation token. All other routes
require the global token.

## Third-party VLM (OpenAI / Anthropic / Groq)

To send OCR images to a hosted VLM instead of LM Studio:

1. Set `OMNISCRIBE_LLM_API_BASE` to the provider's OpenAI-compatible endpoint
   (e.g. `https://api.openai.com/v1`).
2. Set `OMNISCRIBE_LLM_API_KEY` to your provider key.
3. Set `OMNISCRIBE_LLM_MODEL` to the model ID you have access to (e.g.
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

## Windows Troubleshooting

If you used `install.bat` + `start_app.vbs` and the browser opens
to a blank page or never opens:

- Check `start_app.log` next to `start_app.vbs`. It has one
  timestamped line per step (uv pre-check, Docker detect, Redis
  start, Celery launch, uvicorn poll result).
- If the log says "uv is not on PATH" — the official uv installer
  adds uv to your user PATH, but the change only applies to new
  logon sessions. Log out of Windows and back in, then re-run
  the Desktop shortcut.
- If the log says "Docker is not available" — start Docker
  Desktop. Redis + Celery are skipped, the web server still
  starts, and only `/api/translate/async` is unavailable.
- If the log says "Server did not respond within 60s" — open a
  terminal in the project root and run
  `uv run --extra web uvicorn src.omniscribe.server:app --port 8000`
  directly to see uvicorn's traceback.

## Backup & Recovery

OmniScribe keeps all job artifacts in process memory
(`api/routers/state.py`). **A restart loses history.** There is no
on-disk job database in the current release.

If you need durable history, the only path is to swap
`LocalStateBackend` for a Redis-backed `StateBackend`. That is a
deliberate single-file change — see `api/services/state_backend.py`
for the protocol.

## Upgrading

1. `uv sync` (or `docker compose pull`)
2. `uv run omniscribe-server` (or `docker compose up -d`)
3. Visit `/health` to confirm the new version
4. Review the [CHANGELOG](CHANGELOG.md) for breaking changes

The settings tab persists user preferences via `localStorage`, not
server-side state. A version upgrade does not lose user settings.

## Uninstall

```bash
# Local install
uv pip uninstall omniscribe

# Docker
docker compose down --rmi all --volumes
```

Job artifacts in `/tmp/ocr_*` are removed by the startup sweep
(M6); manual cleanup is rarely needed.

## See Also

- [README.md](README.md) — feature overview, install, web workspace
- [CHANGELOG.md](CHANGELOG.md) — version history and breaking changes
- [SECURITY.md](SECURITY.md) — threat model, hardening checklist,
  vulnerability disclosure
- [ARCHITECTURE.md](ARCHITECTURE.md) — component map and API
  surface
- [AGENTS.md](AGENTS.md) — contributor guide and full env-var
  reference

_Last updated: 2026-08-12_