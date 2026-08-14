# Security Policy

OmniScribe is a self-hosted OCR + translation workstation. The default
profile is **local-desktop single-user**, where every guard described here
is essentially "defence in depth" against a future deployment mistake.
Switching the server to a multi-user or LAN-reachable profile is
intentional — the guards below are what make that switch safe.

## Reporting a Vulnerability

Email **`ahnafnafee@gmail.com`** with:

- A short title
- Repro steps (or a script)
- Affected component / endpoint
- Impact assessment (what can an attacker reach)

PGP key: not published — for sensitive reports, request the fingerprint
in your first email and we will reply out-of-band. We aim to acknowledge
within **3 business days** and triage within **10 business days**.

Please do **not** open a public GitHub issue for unreleased fixes.

## Supported Versions

| Branch       | Status            | Security fixes |
| ------------ | ----------------- | -------------- |
| `main`       | Active development | Yes           |
| Last release | Best-effort        | Yes, on request |

There is no long-term-support branch. The release cadence tracks feature
work; security-only patches ship as point releases on `main` tagged with
`security/`.

## Threat Model

OmniScribe is engineered for three threat profiles, in increasing
strictness:

1. **Local single-user (default)** — the workstation runs on
   `localhost`. The threat is a malicious file you are OCR-ing. Guards:
   `MaxUploadSizeMiddleware`, sanitised filenames, validated VLM
   responses.
2. **LAN / trusted-network** — the workstation runs on a private LAN
   behind a firewall. The threat is a curious housemate. Guards: bearer
   auth on every route (except `/health`, `/healthz`, `/ready`,
   `/readyz`), per-route token scoping, rate limiting, audit-friendly
   logs.
3. **Public-internet** — the workstation runs behind a reverse proxy on
   a public IP. The threat is the open internet. **All LAN guards plus:**
   `ALLOW_SSRF_LOCAL=false`, strong random `OMNISCRIBE_AUTH_TOKEN`,
   pinned Docker base images, dedicated process user, no shell access.

OmniScribe ships sensible defaults for profile (1). Operators exposing
the server MUST review the [Deployment Guide](DEPLOYMENT.md) and
explicitly opt into profile (2) or (3) by setting the relevant env vars.

## Security Features

| Layer                  | Guard                              | Default             | Override                                |
| ---------------------- | ---------------------------------- | ------------------- | --------------------------------------- |
| HTTP auth              | `OMNISCRIBE_AUTH_TOKEN`           | Unset (open)        | Set to a 32+ char random secret         |
| Per-service auth       | `OMNISCRIBE_OCR_AUTH_TOKEN`, `OMNISCRIBE_TRANSLATION_AUTH_TOKEN`, `OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN` | Unset | Set when OCR, translation, or transcription should accept different tokens |
| Upload size            | `OMNISCRIBE_MAX_UPLOAD_MB`        | 10 GB               | Lower for public deployments            |
| Rate limit             | `OMNISCRIBE_RATE_LIMIT_PER_MIN`   | 60 req/min/IP       | Lower for public deployments            |
| Trusted reverse proxies | `OMNISCRIBE_TRUSTED_PROXIES`    | Unset (peer IP only) | Comma-separated CIDR list; X-Forwarded-For is honoured only when the ASGI peer is inside one of these ranges |
| SSRF (URL fetcher)     | `ALLOW_SSRF_LOCAL`                 | `true`              | Set `false` for any non-local exposure  |
| CORS                   | `OMNISCRIBE_CORS_ORIGINS`          | localhost-only      | Comma-separated allow-list for cross-origin browser clients |
| VLM resilience         | `OMNISCRIBE_LLM_MAX_RETRIES`, `OMNISCRIBE_LLM_RETRY_BASE_DELAY`, `OMNISCRIBE_CB_FAILURE_THRESHOLD`, `OMNISCRIBE_CB_COOLDOWN` | retries=2, base=1.0s, failures=5, cooldown=30s | Higher to ride out a flaky provider; lower to fail fast |
| Auth placeholder reject| startup `RuntimeError`             | n/a                 | Always on                               |
| Token strength         | `min_length=32` Pydantic constraint | Always on          | n/a                                      |

See [AGENTS.md](AGENTS.md) for the full env-var catalogue.

## Out-of-Scope

We do not run a hosted service. Issues that only affect operators who
choose to expose OmniScribe to the public internet are still in scope
but the fix may ship as documentation guidance rather than a code
patch — public-internet hardening is fundamentally an operator
responsibility.

We do not consider the following vulnerabilities:

- Clickjacking on the Svelte UI when the operator has not configured
  `X-Frame-Options` / `Content-Security-Policy` at their reverse proxy.
- Local file disclosure via XSS in the operator's reverse-proxy error
  page (we ship no error UI).
- VLM hallucination that an operator chose to trust blindly.

## Vulnerability Disclosures (Historical)

This section is the public log of acknowledged-and-fixed issues. New
entries appear with the next release tag.

| Date       | Component           | CVE         | Description                                     |
| ---------- | ------------------- | ----------- | ----------------------------------------------- |
| _none yet_ |                     |             |                                                 |

## Cryptography

- **Token storage:** none. Auth tokens live in process env only; they
  are not persisted to disk, logged, or written to the job history.
- **Token comparison:** `secrets.compare_digest` (constant-time) on every
  bearer auth path. WebSocket handshake compares channel tokens the
  same way.
- **Token generation:** `secrets.token_urlsafe` (24–32 bytes of
  entropy) for progress channel IDs and session tokens.
- **Cancel mechanism:** `POST /api/progress/cancel/{channel_id}` and
  inbound `{"type":"cancel"}` WebSocket frames set an in-process
  `asyncio.Event` per `channel_id`. The OCR / translate worker checks
  this flag between blocks; a process kill mid-run silently aborts
  any unsent cancellation (no on-disk durability). No HMAC or shared
  secret is involved — the auth boundary is the bearer token on the
  HTTP route and the channel session token on the WebSocket
  handshake.
- **TLS:** not terminated by OmniScribe itself. Operators MUST front
  the service with a reverse proxy (Caddy / nginx / Traefik) for
  HTTPS in any non-local deployment.
- **Outbound TLS:** httpx with default cert verification. urllib
  fallback uses the stdlib's `ssl.create_default_context()`.

## Privacy

OmniScribe is local-first. The OCR pipeline sends **only** the page
images you upload to the configured VLM endpoint. By default that is
LM Studio on `http://localhost:1234/v1` — no data leaves the
machine.

If you configure a third-party endpoint (e.g. OpenAI, Anthropic,
Groq), your images and extracted text will be sent to that endpoint.
We surface this in the Settings tab; the choice is yours.

We do not collect telemetry. We do not embed analytics. We do not
phone home.

## Hardening Checklist

Before exposing OmniScribe beyond `localhost`:

- [ ] Set `OMNISCRIBE_AUTH_TOKEN` to a 32+ char random secret
- [ ] Set `ALLOW_SSRF_LOCAL=false`
- [ ] Set `OMNISCRIBE_MAX_UPLOAD_MB` to a reasonable value for your
      network (e.g. 1024 MB)
- [ ] Set `OMNISCRIBE_RATE_LIMIT_PER_MIN` low enough to bound abuse
      (e.g. 30)
- [ ] If fronted by a reverse proxy, set `OMNISCRIBE_TRUSTED_PROXIES`
      to the proxy's CIDR (e.g. `10.0.0.0/24`) so the rate limiter sees
      the real client IP, not the proxy's
- [ ] Front the service with a reverse proxy enforcing HTTPS +
      `Strict-Transport-Security`
- [ ] Run the server as a dedicated unprivileged user
- [ ] Pin the Docker base image to a digest (`M7`)
- [ ] Review the env in `.env.example` for any value you would prefer
      different from the default

## See Also

- [README.md](README.md) — feature overview, install, web workspace
- [CHANGELOG.md](CHANGELOG.md) — version history and breaking changes
- [ARCHITECTURE.md](ARCHITECTURE.md) — component map and API surface
- [DEPLOYMENT.md](DEPLOYMENT.md) — local / LAN / public-internet deployment profiles
- [AGENTS.md](AGENTS.md) — contributor guide and full env-var reference

_Last updated: 2026-08-12_