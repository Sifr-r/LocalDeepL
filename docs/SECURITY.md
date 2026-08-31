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
   upload size parsing check, sanitised filenames, validated VLM
   responses.
2. **LAN / trusted-network** — the workstation runs on a private LAN
   behind a firewall. The threat is a curious housemate. Guards:
   planned bearer auth on every route (except `/health`, `/healthz`,
   `/ready`, `/readyz`), per-route token scoping, rate limiting,
   audit-friendly logs. *(Note: ASGI bearer auth and rate-limit
   middlewares are currently deferred capabilities in the Cordis harness
   rebuild; see AGENTS.md).*
3. **Public-internet** — the workstation runs behind a reverse proxy on
   a public IP. The threat is the open internet. **All LAN guards plus:**
   `ALLOW_SSRF_LOCAL=false`, strong random `OMNISCRIBE_AUTH_TOKEN`,
   pinned Docker base images, dedicated process user, no shell access.

OmniScribe ships sensible defaults for profile (1). Operators exposing
the server MUST review the [Deployment Guide](DEPLOYMENT.md) and
explicitly opt into profile (2) or (3) by setting the relevant env vars.

## Security Features

> [!NOTE]
> Following the Cordis plugin harness rebuild, ASGI bearer authentication
> (`OMNISCRIBE_AUTH_TOKEN`), rate limiting, and `MaxUploadSizeMiddleware`
> are currently deferred capabilities. The settings remain declared in
> `config.py` as configuration scaffolding for the forthcoming middleware
> plugins. The current active middleware is CORS.

| Layer                  | Guard                              | Default             | Override                                |
| ---------------------- | ---------------------------------- | ------------------- | --------------------------------------- |
| HTTP auth *(deferred)* | `OMNISCRIBE_AUTH_TOKEN`           | Unset (open)        | Set to a 32+ char random secret (scaffolding for deferred auth plugin) |
| Transcription config auth | `OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN` | Unset | Currently surfaces as a masked preview in `/api/config/transcription`; will be enforced by the deferred auth middleware |
| Upload size            | `OMNISCRIBE_MAX_UPLOAD_MB`        | 10 GB (10240 MB)    | Lower for public deployments (enforced at upload parse) |
| Rate limit *(deferred)* | `OMNISCRIBE_RATE_LIMIT_PER_MIN`   | 60 req/min/IP       | Lower for public deployments (scaffolding for deferred rate-limit plugin) |
| SSRF (URL fetcher)     | `ALLOW_SSRF_LOCAL`                 | `false` (code default) | Shipped `.env.example` sets `true` for local development; keep `false` for non-local exposure |
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

- Clickjacking on the bundled web UI when the operator has not configured
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

## Platform Notes

### Windows Defender false positive on `arrow_substrait.dll`

The optional `[lexicon]` extra pulls in `lancedb`, which transitively
ships Apache Arrow's SubstraIT DLL (`arrow_substrait.dll`,
~6-8 MB native binary). On a small fraction of Windows hosts
Microsoft Defender flags this DLL as `Trojan:Win32/Wacatac.B!ml`
or similar on first install. **This is a known false positive** —
the same DLL ships in the official Apache Arrow PyPI wheel and
the signature verifies against the Arrow maintainers' certificate
in every case we have reproduced.

**What to do** (in order of preference):

1. **Update Defender** (Windows Security → Virus & threat
   protection → Check for updates). The false-positive signature
   is updated within days of Arrow's release. Reinstall
   `omniscribe[lexicon]` after the update.
2. **Add an exclusion** (Windows Security → Virus & threat
   protection → Threat protection settings → Exclusions → Add or
   remove an exclusion → Folder) for the venv site-packages
   directory that contains `arrow_substrait.dll`. Typical path:
   `.venv\Lib\site-packages\pyarrow\arrow_substrait.dll`. This
   does NOT reduce OmniScribe's security posture — the exclusion
   is scoped to a single bundled library, not the entire venv.
3. **Run in a container** (`docker compose up`) — the multi-stage
   `Dockerfile` builds on a clean Debian base, so Defender's host
   heuristic does not fire.

This is a host-OS-level false positive, not an OmniScribe code
defect. We do not patch around it in `omniscribe[lexicon]`
because the workaround (vendoring our own Arrow copy, or stripping
SubstraIT support from lancedb) would carry a real maintenance
burden. The list above is the documented mitigation. If a
_clearly genuine_ malicious arrow_substrait.dll is ever identified
in the official Apache Arrow PyPI release, this section will be
amended; for now the false positive is the only known issue.

## Hardening Checklist

Before exposing OmniScribe beyond `localhost`:

- [ ] Set `OMNISCRIBE_AUTH_TOKEN` to a 32+ char random secret
- [ ] Set `ALLOW_SSRF_LOCAL=false`
- [ ] Set `OMNISCRIBE_MAX_UPLOAD_MB` to a reasonable value for your
      network (e.g. 1024 MB)
- [ ] Set `OMNISCRIBE_RATE_LIMIT_PER_MIN` low enough to bound abuse
      (e.g. 30)
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

_Last updated: 2026-08-31_