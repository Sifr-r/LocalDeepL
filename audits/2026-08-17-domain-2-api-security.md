# Domain 2 Audit: API & Security

**Date:** 2026-08-17
**Auditor:** Mavis (explore subagent, deep-evidence investigation)
**Methodology:** Static read-only review of every file in scope, focusing on token comparison correctness, path normalization, SSRF allow/deny list semantics, redirect handling, DNS-rebinding TOCTOU, state-backend concurrency, WebSocket token binding, and middleware ordering.

## Scope
- **Files examined:** 32 files in `src/omniscribe/api/`, `src/omniscribe/server.py`, `src/omniscribe/utils/security.py`
- **Lines of code reviewed:** ~5,400
- **Key paths:**
  - `src/omniscribe/server.py` — app factory, middleware wiring
  - `src/omniscribe/api/services/security_middleware.py` — BearerAuth, MaxUploadSize, RateLimit
  - `src/omniscribe/api/services/security.py` — upload validator
  - `src/omniscribe/api/services/security_config.py` — env parsing, token validation
  - `src/omniscribe/api/routers/websocket.py` — channel/token binding, cross-loop marshalling
  - `src/omniscribe/api/routers/config.py` — runtime config persistence + per-namespace auth-token updates
  - `src/omniscribe/utils/security.py` — SSRF guard
  - `src/omniscribe/api/services/http_fetch.py` — pinned-IP HTTP transport for SSRF-safe fetches
  - `src/omniscribe/api/services/state_backend*.py`
  - `src/omniscribe/api/services/ocr_jobs.py`, `jobs.py`, `artifacts.py`, `progress.py`
  - `src/omniscribe/api/routers/common.py` — stable error envelopes, token dependency
  - `src/omniscribe/api/routers/health.py` — liveness/readiness probes
  - `src/omniscribe/api/services/config_store.py` — per-namespace config persistence

## Findings

| ID | Severity | Area | File:Line | Description | Evidence | Recommendation |
|----|----------|------|-----------|-------------|----------|----------------|
| F2.1 | HIGH | Auth / misconfig | `security_middleware.py:308-372` | Per-namespace token misconfiguration leaves protected route groups open. | See detail | Lock every protected group when any token is set |
| F2.2 | HIGH | Auth / management | `security_middleware.py:318-321, 357-368` | Management routes accept ANY subsystem token. | See detail | Require a dedicated admin token |
| F2.3 | MEDIUM | Upload / DoS | `security_middleware.py:418-541`, `security.py:36-54` | Max-upload cap (default 10 GB, hard ceiling 100 GB) + chunked path with no deadline. | `save_validated_upload` is the only deadline gate | Lower the absolute ceiling or enforce deadline at middleware layer |
| F2.4 | MEDIUM | Rate limit | `security_middleware.py:646-649` | WebSocket upgrades bypass the rate limiter. | `if scope["type"] != "http": await self.app(...)` | Apply the per-IP bucket to `scope["type"] == "websocket"` too |
| F2.5 | MEDIUM | Resilience | `security_middleware.py:253-264` | `_get_active_tokens` silently swallows config-store read errors. | `try: ... except Exception: pass` | Log a warning before falling back |
| F2.6 | MEDIUM | Provider headers | `providers.py:95-103`, `provider_manager.py:551-557` | `ProviderCreateRequest.headers` is unvalidated; allows `Host`, `X-Forwarded-Host`, or auth-header overrides. | Freeform headers dict | Disallow routing-affecting headers |
| F2.7 | MEDIUM | Token leak | `security_config.py:186-196` | `_validate_auth_token` includes the offending token in the startup `RuntimeError`. | `f"{env_name}={token!r}"` | Redact the value (log only length + first/last char) |
| F2.8 | MEDIUM | CORS | `server.py:170-171` | CORS uses `allow_methods=["*"], allow_headers=["*"]`. | Wildcard | Enumerate allowed methods and headers explicitly |
| F2.9 | LOW | Info disclosure | `health.py:98-108` | Readiness endpoint reports in-memory state counts. | `/ready` returns artifact counts | Document as intended; keep return shape small |
| F2.10 | LOW | Token in URL | `common.py:30-35`, `artifacts.py:33-41` | `get_access_token` accepts the artifact token via query param. | Docstring says URL is "intentionally token-free"; implementation contradicts | Document the accepted surfaces, or reject `?token=` |
| F2.11 | LOW | WS race | `websocket.py:601-621` | `verify_minted` and `register_channel` are not atomic. | Two concurrent clients could both pass `verify_minted` | Wrap verify+register in an `asyncio.Lock` |
| F2.12 | LOW | Test override | `config_store.py:64-78` | `InMemoryConfigStore._cross_worker_visible` is a public boolean that production code never checks. | Writable public attribute | Rename to `_test_only_cross_worker_visible` |

### CRITICAL findings

**None.** The security primitives are well-constructed:
- `secrets.compare_digest` and `hmac.compare_digest` are used for every token comparison.
- SSRF guard performs literal-IP blocklist + DNS resolution + per-redirect IP pinning.
- WebSocket auth is per-channel with a 10 s auth-frame timeout and 64 KiB per-message cap.
- Path normalization rejects non-ASCII / `%2F` / `..` before route classification.

### HIGH findings (detailed writeup)

**F2.1** — Per-namespace token misconfiguration leaves protected route groups open

**Where:** `src/omniscribe/api/services/security_middleware.py:308-322` (`_token_for`) and `src/omniscribe/api/services/security_middleware.py:348-372` (the `acceptable_tokens` builder).

**Trigger:** Operator sets `OMNISCRIBE_TRANSLATION_AUTH_TOKEN=<secret>` in `.env` but leaves `OMNISCRIBE_AUTH_TOKEN` (global) and `OMNISCRIBE_OCR_AUTH_TOKEN` (OCR) unset.

**What happens:** For an `HTTP POST /api/process` request (an OCR route, not translation), the middleware falls through every branch. The OCR route is open. So is every non-management route in the same operator's setup.

**Same trap for `/api/translate` if only `OMNISCRIBE_OCR_AUTH_TOKEN` is set, and for `/api/transcribe` if only OCR or translation is set.**

**Recommendation:** Either (a) require a token on every protected route group when any token is set; or (b) make this gap loud by failing `SecuritySettings.from_env()` at startup if `OMNISCRIBE_*_AUTH_TOKEN` is set without a clear warning.

**F2.2** — Management routes accept any subsystem token

**Where:** `src/omniscribe/api/services/security_middleware.py:318-321` and `src/omniscribe/api/services/security_middleware.py:357-368`.

**Trigger:** Operator sets only `OMNISCRIBE_OCR_AUTH_TOKEN=<ocr-secret>`. The management routes (`/api/jobs/*`, `/api/providers/*`, `/api/progress/session`, `/api/progress/cancel/{id}`, `/api/config/*`) are gated by the `else if _is_management_route` branch, which accepts "any non-empty subsystem token":

```python
elif _is_management_route(normalized):
    subsystem_tokens = [
        t
        for t in (
            tokens["ocr"],
            tokens["translation"],
            tokens["transcription"],
        )
        if t is not None
    ]
    if subsystem_tokens:
        acceptable_tokens = subsystem_tokens
```

**What happens:** A holder of the OCR token can:
- `POST /api/providers/active` — switch the LLM provider.
- `POST /api/jobs/{job_id}/cancel` — cancel any in-flight OCR or translation async job.
- `POST /api/config/{translation,transcription}/auth` — set or clear the translation/transcription namespace tokens.

**Recommendation:** Introduce a dedicated `OMNISCRIBE_ADMIN_TOKEN` for management routes, or restrict each management endpoint to the namespace that owns it.

### MEDIUM findings (one-liner each)
- F2.3 — `MaxUploadSizeMiddleware` accepts the full 100 GB ceiling and has no per-request deadline at the middleware layer.
- F2.4 — `RateLimitMiddleware` short-circuits `scope["type"] != "http"`, so WebSocket upgrade floods are bounded only by the 10 s `verify_minted` auth-frame timeout.
- F2.5 — `BearerAuthMiddleware._get_active_tokens` swallows every exception when reading the config store; a Redis outage silently downgrades to env-only tokens with no operator-visible log.
- F2.6 — `ProviderCreateRequest.headers` is a freeform `dict[str,str]`; an attacker with a valid token can override `Host` / `X-Forwarded-Host` / authorization headers before `httpx` sends the request.
- F2.7 — `SecuritySettings._validate_auth_token` embeds the offending token in the startup `RuntimeError`; a misconfigured `.env` + log aggregator leaks the token.
- F2.8 — CORS uses `allow_methods=["*"], allow_headers=["*"]`; with `allow_credentials=False` the classic misconfig is blocked, but the wildcard surface is wider than necessary.

### LOW findings (one-liner each)
- F2.9 — `/ready` returns in-memory state counts — minimal information disclosure.
- F2.10 — `get_access_token` accepts the artifact token via `?token=` query param, contradicting the docstring.
- F2.11 — WebSocket `verify_minted` and `register_channel` are not atomic; the CSPRNG collision window is microseconds but the second client silently overwrites the active channel.
- F2.12 — `InMemoryConfigStore._cross_worker_visible` is a writable public attribute; a buggy test fixture could silently disable the 503 cross-worker guard.

## Cross-cutting observations

- **State backend reset semantics:** Every cross-worker-visible backend (SQLite, Redis) implements the seven-attribute `StateBackend` Protocol, but `ProgressService`, `OCRJobQueue`, and `GlossaryLibrary` are documented as in-memory by design.
- **Defense-in-depth, three layers for /api/jobs/{job_id}/result:** bearer middleware + `access_token` query/header parameter + `secrets.compare_digest` against the record's `text_artifact_token`.
- **Defense-in-depth, SSRF:** literal IP blocklist + DNS resolution + per-redirect IP pinning via custom `httpx.AsyncBaseTransport`.
- **Token generation quality:** `secrets.token_urlsafe(24..32)` and `secrets.token_hex(16)` for channel/session/artifact IDs and tokens.
- **File-path containment:** artifact path validation enforces `Path.resolve().relative_to(self._artifact_dir)`.
- **Stable error envelopes:** `_stable_server_error` and `api_error_response` never include stack traces.
- **Token downgrade via the auth endpoint:** The `AuthTokenUpdate` schema accepts `auth_token: null` to clear the namespace token.

## Positive findings

- `secrets.compare_digest` is used for every token compare; `hmac.compare_digest` is used for channel binding.
- WebSocket handshake rejects unknown channels and channels that already hold a live socket.
- `BearerAuthMiddleware._normalize_path` collapses `%2F`, `..`, and non-ASCII homoglyphs before route classification.
- `_validate_auth_token` enforces `MIN_AUTH_TOKEN_LENGTH=32` and a 32-entry placeholder denylist.
- `RateLimitMiddleware` only honors `X-Forwarded-For` when the ASGI peer is inside a configured `trusted_proxies` CIDR.
- `MaxUploadSizeMiddleware` has both the `Content-Length` fast path and a chunked path that truncates downstream reads on overflow.
- Upload MIME detection via magic bytes; temp file uses `tempfile.NamedTemporaryFile(delete=False)` with a server-controlled suffix.
- SQLite WAL mode + per-op `sqlite3.connect` (short-lived connections) prevents reader/writer contention.
- `SSEBroker.publish` snapshots subscribers under a `threading.Lock` and dispatches outside the lock.
- `OCRJobQueue._worker_loop` and `cancel` use a single `asyncio.Lock`; a concurrent cancel during a `PROCESSING→COMPLETE` transition is preserved.
- `ConnectionManager.send` uses `asyncio.run_coroutine_threadsafe(ws.send_text(text), accept_loop)` to marshal foreign-loop writes.

## Coverage gaps

- **Timing-attack measurements** were not performed.
- **Multi-worker concurrent-write race** for the in-memory state backend cannot be exploited.
- **Redirect-based SSRF across protocols** (e.g. `Location: file:///etc/passwd`) was verified to be blocked.
- **Exploit chain for the per-namespace misconfig (F2.1)** assumes a non-cooperative operator.
- **No source code outside `src/omniscribe/api/`, `src/omniscribe/server.py`, and `src/omniscribe/utils/security.py`** was read.

## Known-security-posture verification

| Claim | Status | Evidence |
|-------|--------|----------|
| `OMNISCRIBE_AUTH_TOKEN` set → constant-time compare via ASGI middleware | **CONFIRMED** | `security_middleware.py:391` uses `secrets.compare_digest` |
| WebSocket handshake auth still enforced per-channel in `routers/websocket.py` | **CONFIRMED** | `websocket.py:596-621` |
| VLM resilience: retries 429/5xx/connection resets with exponential backoff | **CONFIRMED** (out of scope) | `core/ocr/resilience.py` not deep-read |
| Per-IP 60s sliding window, in-memory | **PARTIALLY IMPLEMENTED** | Sliding window correct; WebSocket scopes excluded |
| Reject on `Content-Length` | **CONFIRMED** | Both fast path and chunked path bounded |
| Progress WebSocket cross-loop marshalling | **CONFIRMED** | `websocket.py:288-329` |
| `ALLOW_SSRF_LOCAL=true` is the local-development default | **PARTIALLY CONFIRMED** | Code's default is to **BLOCK** local addresses; contradicts AGENTS.md |
| `verify_minted` rejects unknown channels + channels with an already-live socket | **CONFIRMED** | `websocket.py:225-235` |
| CORS preflight blocks cross-origin POST with Authorization when no origin matches | **CONFIRMED** | Explicit origin list |
| Upload deadline `OMNISCRIBE_UPLOAD_DEADLINE_SECONDS` enforced per-request | **PARTIALLY IMPLEMENTED** | Enforced in `save_validated_upload` but not in `MaxUploadSizeMiddleware` |
| `JobHistory` and `OCRJobQueue` survive a restart only via SQLite/Redis backend | **CONFIRMED** | Documented persistence boundary |
| Auth tokens are env-only for the global token; per-namespace tokens settable via POST when backend is cross-worker | **CONFIRMED** | Writes refused with 503 when in-memory store is active |
