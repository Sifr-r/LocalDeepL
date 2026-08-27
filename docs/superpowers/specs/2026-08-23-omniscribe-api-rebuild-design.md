# OmniScribe API Rebuild on a Cordis-Style Plugin Harness

**Date:** 2026-08-23
**Status:** Approved — ready for implementation plan
**Owner:** rahin2uddin

## Context

The previous `src/omniscribe/api/` package (~50 files, ~10,000+ lines) has been
deleted. It housed the FastAPI routers, services, middleware, schema models,
Celery tasks, and a Cordis-style plugin container that was mid-migration when
the package was removed. `src/omniscribe/server.py` is now a clean-slate shell
serving only `/`, `/health`, `/healthz`, `/ready`, `/readyz`, and `/static/*`.

The `core/` package (OCR pipeline) is untouched and the build of the OCR
pipeline remains the source of truth for the OCR path. This spec rebuilds the
HTTP and WebSocket surface using **deepseek-harness** (a Cordis-based "everything
is a plugin" framework) as the architectural guide, ported faithfully into
Python idioms.

The frontend has already been updated to expect the new endpoint shape (see
`frontend/src/lib/api/client.ts`, `frontend/src/lib/services/workstationService.ts`),
and `start_app.vbs` already passes `OMNISCRIBE_STATE_BACKEND=redis|sqlite` at
boot, so the rebuild must honor those contracts.

## Goals (this iteration)

1. Ship a working OCR API on the new plugin harness: sync `/api/process`,
   async `/api/process/async`, job status, WebSocket progress, result download,
   job list/clear/cancel, and minimal health + config endpoints.
2. Establish a Cordis-style plugin harness as the single extension point for
   every future capability (translation, transcription, glossary, extraction,
   auth, etc.). The harness must support reversible effects, typed events,
   type-driven service injection, declarative YAML config, and patch layering.
3. Rebuild the StateBackend contract (memory + sqlite impls in this iteration;
   redis deferred).
4. Replace the deleted tests/api/ tree with a fresh `tests/harness/`,
   `tests/plugins/`, and `tests/routers/` structure.

## Out of scope (deferred to follow-up specs)

- Translation plugin + routes
- Transcription plugin + routes
- Glossary imports plugin + routes
- Document extraction + export plugins + routes
- Auth middleware plugin (`OMNISCRIBE_AUTH_TOKEN`)
- Rate-limit middleware plugin
- Upload-size-guard middleware plugin
- Celery async task dispatch
- Redis state backend
- External pluggy-style plugin discovery (entry-point loaded from installed
  packages)
- Frontend rebuild (the SPA bundle hash in `src/omniscribe/static/index.html`
  is currently out of sync — separate task)

## Architecture

Three layers:

### 1. Plugin harness — `src/omniscribe/harness/`

A faithful Python port of Cordis's four primitives. No decorators, no runtime
metaclass magic; everything is a plain class with a small Protocol surface.

**Context** — the shared mutable container. One per app process.

```python
class Context:
    # Services
    def service(self, protocol: type[T], instance: T) -> EffectRef: ...
    def inject(self, protocol: type[T]) -> T: ...                    # raises ServiceNotFoundError
    def has(self, protocol: type[T]) -> bool: ...

    # Events (typed broadcast)
    def on(self, event_type: type[Event], handler: EventHandler) -> EffectRef: ...
    async def emit(self, event: Event) -> None: ...                   # concurrent dispatch

    # Effects (auto-cleanup on plugin unload)
    def effect(self, cleanup: Callable[[], Awaitable[None] | None]) -> EffectRef: ...
    @asynccontextmanager
    def effect_scope(self) -> AsyncIterator[EffectScope]: ...

    # Deferred router mount (resolved by server.create_app after load_harness)
    def mount_router(self, router: APIRouter) -> EffectRef: ...
    def routes(self) -> list[APIRouter]: ...                          # snapshot for create_app

    # Lifecycle
    async def plugin(self, plugin: Plugin, *, config: dict | None = None) -> None: ...
    async def unload(self, plugin_id: str) -> None: ...               # reverses effects in LIFO
    async def dispose(self) -> None: ...                              # unload all, await cleanups
```

Every registration returns an `EffectRef` tracked under the plugin id that
registered it. Plugin id resolution uses a `contextvars.ContextVar` set by
`Context.plugin(...)` before calling the plugin's `apply(ctx)` and cleared
after — so `ctx.effect(...)`, `ctx.service(...)`, `ctx.on(...)`, and
`ctx.mount_router(...)` all attribute their registration to the current
plugin without callers having to thread the id through. `unload` walks the
plugin's effects in reverse and awaits each cleanup. `dispose` is called
from FastAPI's lifespan shutdown.

**Service** — `typing.Protocol` marker, used purely for type-driven DI. No
runtime subclassing, no decorators.

```python
class Service(Protocol): ...   # marker; concrete impls are plain classes

class OCRService(Protocol):
    async def run(self, request: OCRRequest) -> OCRResult: ...
    async def run_async(self, request: OCRRequest) -> JobHandle: ...

# Registration: ctx.service(OCRService, OCRServiceImpl(...))
# Lookup:      svc = ctx.inject(OCRService)
```

**Event** — typed event base, three domains (mirroring Cordis):

- `SessionEvent` — durable facts appended to the session log.
- `AgentEvent` — live progress frames.
- `CapabilityEvent` — seam policy/adapter events.

Listeners filter by exact event type — no string names. Broadcasts dispatch
concurrently via `asyncio.gather(return_exceptions=True)`. A listener exception
is logged but never crashes the bus.

**EffectScope** — async context manager for scoped lifetimes:

```python
async def apply(self, ctx: Context) -> None:
    channel = ProgressChannel()
    ctx.service(ProgressChannel, channel)
    async with ctx.effect_scope() as scope:
        scope.add(channel.shutdown)
        scope.add(lambda: registry.unregister(channel.id))
```

Plain `ctx.effect(cleanup)` is sugar for the same mechanism.

**Loader** — reads `cordis.yml`, applies patch layers in declared order
(base file → `<artifact_dir>/cordis.patch.yml` → `--patch <path>` CLI →
`OMNISCRIBE_PLUGIN_<ID>_<FIELD>` env overrides), expands `${VAR:-default}`
substitution, validates each row's config against the plugin's pydantic
`Schema`, and mounts in declared order. Bad config fails loud at boot, not
on first request.

**Plugin base class** — minimal:

```python
class Plugin:
    id: str                               # set by loader from row id
    Schema: type[BaseModel] | None        # optional pydantic config schema

    async def apply(self, ctx: Context) -> None: ...    # subclass overrides
    async def dispose(self) -> None: ...                # optional; default no-op
```

Plugins are looked up by `module:callable` import path. The in-tree plugins
are static; external discovery is a follow-up.

### 2. Plugin tree — `src/omniscribe/plugins/`

Nine core plugins, each single-purpose. Boot order is fixed by `cordis.yml`
and the loader refuses to mount a plugin whose `inject()` dependency is
missing.

| Plugin | Owns | ctx key |
|---|---|---|
| `runtime` | Lifespan, settings, shutdown coordination, cleanup loop | `ctx.runtime` |
| `logging` | Structured logging configured from settings | `ctx.logging` |
| `state_backend` | Artifact + job + channel persistence (memory/sqlite) | `ctx.state` |
| `artifacts` | Composite artifact store (text + metadata + export) | `ctx.artifacts` |
| `jobs` | Single-worker async job queue | `ctx.jobs` |
| `progress` | WebSocket progress channel registry | `ctx.progress` |
| `providers` | Multi-format OCR provider catalog + model discovery | `ctx.providers` |
| `health` | `/api/health`, `/api/healthz`, `/ready`, `/readyz` | `ctx.health` |
| `ocr` | HTTP→pipeline bridge; `OCRService` wraps `OCRPipeline` | `ctx.ocr` |

Each plugin's config schema is a pydantic model. Plugins register routes via
a deferred-mount effect resolved by `server.create_app` after `load_harness`
returns.

### 3. FastAPI app — `src/omniscribe/server.py`

Mounts the harness in lifespan, then resolves every plugin-registered router
as an `APIRouter` include. Static files and root pages stay at root; all
OCR routes live under `/api`.

## Plugins in detail

### State backend (`omniscribe.plugins.state_backend`)

`StateBackend` Protocol covers three domains: artifacts, jobs, progress channels.

```python
class StateBackend(Protocol):
    # Artifacts
    async def put_artifact(self, *, id: str, token: str, owner_job_id: str,
                           content_type: str, blob: bytes, ttl_seconds: int) -> None: ...
    async def get_artifact(self, id: str, token: str) -> ArtifactBlob | None: ...
    async def delete_artifact(self, id: str) -> None: ...
    async def prune_expired_artifacts(self, now: float) -> int: ...

    # Jobs
    async def upsert_job(self, record: JobRecord) -> None: ...
    async def get_job(self, job_id: str) -> JobRecord | None: ...
    async def list_jobs(self, *, limit: int = 100) -> list[JobRecord]: ...
    async def clear_jobs(self) -> int: ...
    async def delete_job(self, job_id: str) -> None: ...

    # Progress channels
    async def put_channel(self, channel_id: str, session_token: str,
                          job_id: str, ttl_seconds: int) -> None: ...
    async def get_channel(self, channel_id: str) -> ChannelRecord | None: ...
    async def consume_channel(self, channel_id: str, session_token: str) -> ChannelRecord | None: ...
    async def delete_channel(self, channel_id: str) -> None: ...
    async def prune_expired_channels(self, now: float) -> int: ...
```

Two impls in this iteration:

- `MemoryStateBackend` — three dicts + an `asyncio.Lock` per dict; blobs kept
  in memory (capped at 256 MB per artifact for safety).
- `SQLiteStateBackend` — `sqlite3` with `PRAGMA journal_mode=WAL`, three
  tables (`artifacts`, `jobs`, `progress_channels`). Blob bytes are stored on
  disk at `OMNISCRIBE_ARTIFACT_DIR/<id>.bin`; sqlite holds the path +
  metadata only (keeps the DB small and matches the deleted code's split).

Selection via `OMNISCRIBE_STATE_BACKEND=memory|sqlite` (default `memory`).
The plugin's `apply()` reads the env var, validates against `{memory, sqlite}`,
builds the impl, registers it under `StateBackend`. Bad value fails boot.
The SQLite impl requires `sqlite_path` to resolve to a writable file path;
when `backend=sqlite` and the path is empty, boot fails with a clear
`ValueError`. Default path is `<artifact_dir>/omniscribe-state.db`.

### Jobs (`omniscribe.plugins.jobs`)

```python
class JobQueue(Protocol):
    async def submit(self, request: OCRRequest) -> JobHandle: ...
    async def status(self, job_id: str) -> JobRecord | None: ...
    async def result(self, job_id: str, token: str) -> bytes | None: ...
    async def cancel(self, job_id: str) -> bool: ...
    async def list(self, *, limit: int = 100) -> list[JobRecord]: ...
    async def clear(self) -> int: ...
```

`InMemoryJobQueue` — single asyncio worker task started as an effect.
Worker transitions `queued → running → {complete | error | cancelled}`,
emitting `JobStarted`, `ProgressFrame` (per-block), `JobCompleted`,
`JobFailed`, `JobCancelled` events along the way.

Shutdown effect cancels the worker and drains pending jobs with status
`cancelled`. The single-worker shape is documented as intentional in
`AGENTS.md`'s Known Tech Debt section.

### Artifacts (`omniscribe.plugins.artifacts`)

Three stores registered as a single composite service:

```python
class ArtifactStore(Protocol):
    async def put(self, blob: bytes, *, content_type: str, owner_job_id: str,
                  ttl_seconds: int = 86_400) -> ArtifactHandle: ...
    async def get(self, id: str, token: str) -> bytes | None: ...
    async def delete(self, id: str) -> None: ...
```

`ArtifactHandle = NamedTuple(id: str, token: str)`. Token is generated via
`secrets.token_urlsafe(32)` (32 random bytes, base64url-encoded to ~43
chars). The store returns `None` from `get` on token mismatch (the route
translates to 403). Internally delegates to
`StateBackend.put_artifact / get_artifact`.

The plugin emits `ArtifactCreated` (a `SessionEvent`) on every `put`.

### Progress (`omniscribe.plugins.progress`)

`ProgressService` owns the channel registry and the WebSocket handler.
Channels are short-lived (TTL 600s) and bound to a single `session_token`.

```python
class ProgressService(Protocol):
    async def open_channel(self) -> ChannelHandle: ...                  # returns {channel_id, session_token}
    async def get_channel(self, channel_id: str) -> ChannelRecord | None: ...
    async def consume_channel(self, channel_id: str, session_token: str) -> ChannelRecord | None: ...
    async def broadcast(self, channel_id: str, frame: ProgressFrame) -> int: ...   # returns fanout count
    async def cancel(self, channel_id: str) -> bool: ...
```

The WebSocket handler at `/api/progress/ws/{channel_id}` records the accept
loop on connect and marshals any foreign-loop send back onto it via
`asyncio.run_coroutine_threadsafe` — preserves the contract documented in
`AGENTS.md`'s "Progress WebSocket cross-loop marshalling" note.

### Providers (`omniscribe.plugins.providers`)

`ProviderManager` — wraps the existing `core/llm/providers.py` and
`api/services/provider_manager.py` (deleted). Provides:

```python
class ProviderManager(Protocol):
    async def list_providers(self) -> list[ProviderInfo]: ...
    async def get_provider(self, name: str) -> ProviderInfo | None: ...
    async def discover_models(self, provider_name: str) -> list[ModelInfo]: ...
    async def set_active(self, provider_name: str, model: str) -> None: ...
    async def get_active(self) -> tuple[str, str]: ...
```

In this iteration the impl reads the provider catalog from
`core/llm/providers.PROVIDER_TEMPLATES` and the runtime settings. No disk
persistence yet — settings-only. Persistence ships with a follow-up spec.

### Health (`omniscribe.plugins.health`)

Registers four routes — `/api/health`, `/api/healthz`, `/ready`, `/readyz`.
Liveness routes return `{status: "ok"}` unconditionally; readiness routes
return `{status: "ready"}` once `ctx.runtime.ready` is set (true after
`load_harness` finishes).

### OCR (`omniscribe.plugins.ocr`)

The bridge between HTTP and `OCRPipeline`.

```python
class OCRService(Protocol):
    async def run(self, request: OCRRequest) -> OCRResult: ...
    async def run_async(self, request: OCRRequest) -> JobHandle: ...
    async def get_status(self, job_id: str) -> JobRecord | None: ...
    async def get_result(self, job_id: str, token: str) -> bytes | None: ...
    async def cancel(self, job_id: str) -> None: ...
```

`OCRServiceImpl` validates the request, builds `ProcessSettings` /
`OCRPipeline.run` config, calls the pipeline, packages the response.
`run` is sync (blocks the request coroutine); `run_async` submits to the
`JobQueue` and returns a `JobHandle{job_id, status_url}`.

The plugin owns the FastAPI router and the request/response pydantic models
in `plugins/ocr/schemas.py`.

### Runtime (`omniscribe.plugins.runtime`)

Coordinates lifespan: holds `RuntimeSettings`, owns the cleanup loop, and
emits `HarnessReady` once every plugin has mounted.

```python
async def _loop(self) -> None:
    while not self._stopping:
        await asyncio.sleep(self._cleanup_interval_seconds)
        await self._state.prune_expired_artifacts(now=time.time())
        await self._state.prune_expired_channels(now=time.time())
```

The cleanup task is the only place that owns the prune cadence. Per-store
TTLs are honored individually (artifacts 24h, channels 10m).

### Logging (`omniscribe.plugins.logging`)

Reads `OMNISCRIBE_LOG_FORMAT` and `OMNISCRIBE_LOG_LEVEL`, configures
`omniscribe.utils.structured_logging`. Resolves `${VAR:-default}` substitution
the same way the loader does.

## Route surface (this iteration)

All OCR routes mounted under `/api` by the OCR plugin's returned `APIRouter`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/health`, `/api/healthz` | `{status: "ok"}` — handled by `health` plugin |
| GET | `/ready`, `/readyz` | `{status: "ready"}` once `ctx.runtime.ready` is set |
| GET | `/api/process/status/{job_id}` | Returns `JobRecord` JSON; 404 if unknown |
| POST | `/api/process` | Sync OCR — FormData upload, returns PDF blob |
| POST | `/api/process/async` | Async OCR — returns `{job_id, status_url}` immediately |
| GET | `/api/process/{job_id}/events` | SSE stream of job events |
| GET | `/api/jobs` | List recent jobs (in-memory ring buffer) |
| DELETE | `/api/jobs` | Clear job history |
| GET | `/api/jobs/{job_id}/result` | Download the result PDF blob (token-gated) |
| POST | `/api/jobs/{job_id}/cancel` | Cooperative cancel via `JobRecord.cancelled` flag |
| POST | `/api/progress/session` | Returns `{channel_id, session_token}` |
| GET | `/api/progress/ws/{channel_id}` | WebSocket — `Authorization: Bearer <session_token>` required |
| POST | `/api/progress/cancel/{channel_id}` | HTTP cancel mirror of the WS frame |
| GET | `/api/config/ocr` | Returns the OCR plugin's resolved config (no secrets) |
| PUT | `/api/config/ocr` | Persists OCR config to `ctx.state` |

## WebSocket protocol

`/api/progress/ws/{channel_id}`:

- Handshake: client opens WS; server validates `?token=<session_token>` query
  and `Authorization: Bearer <session_token>` header; rejects 4401 on mismatch.
- Server frames (JSON):
  ```json
  {"type": "progress", "percent": 42, "stage": "ocr", "message": "Page 3/8"}
  {"type": "block_started", "page": 3, "block_id": "p3-b7"}
  {"type": "block_complete", "page": 3, "block_id": "p3-b7", "confidence": 0.94}
  {"type": "block_retry", "page": 3, "block_id": "p3-b7", "attempt": 1}
  {"type": "block_revised", "page": 3, "block_id": "p3-b7", "confidence": 0.97}
  {"type": "quality_summary", "retries": 1, "improved_blocks": 1}
  {"type": "complete", "job_id": "...", "text_artifact_id": "..."}
  {"type": "error", "job_id": "...", "message": "..."}
  {"type": "cancelled", "job_id": "..."}
  ```
- Client frame: `{"type": "cancel"}` — sets the channel's cancelled flag;
  OCRPipeline honors it at the next block boundary (matches the existing
  `OCRPipeline` cancellation contract).
- Cross-loop marshaling: server emits from the worker task's loop; client may
  be on another loop. The handler records the accept loop and marshals emits
  back onto it via `asyncio.run_coroutine_threadsafe` — same contract as the
  deleted `ConnectionManager.send`.

## Result download

`/api/jobs/{job_id}/result?token=<token>`:

- Token is the opaque artifact handle issued at `JobCompleted` time, stored
  alongside the result in `ctx.state`.
- Missing/invalid token → 403. Missing result (job still running) → 404.
  Expired (TTL passed) → 410.

## Persistence

`ctx.state` (memory or sqlite per `OMNISCRIBE_STATE_BACKEND`):

- `artifacts` table: `(id, token, owner_job_id, content_type, blob_path, created_at, ttl_seconds)`.
  For memory, blob is in-process bytes; for sqlite, blob is on disk under
  `OMNISCRIBE_ARTIFACT_DIR/<id>.bin`.
- `jobs` table: `(job_id, status, request_meta, result_artifact_id, created_at, updated_at, error)`.
- `progress_channels` table: `(channel_id, session_token, job_id, created_at)`.

## Validation and error handling

- Request schemas in `omniscribe.plugins.ocr.schemas` (pydantic). Validation
  failures return `400 {error, detail}`.
- Unknown job_id → 404. Invalid token → 403. Job in `error` state → 409 with
  `{error, status, message}`. Expired → 410.
- OCRPipeline exceptions bubble as `500 {error, detail}` (no internal stack
  traces leaked).
- Worker exception → caught in the worker loop, status set to `error`, error
  string stored, `JobFailed` emitted.
- Worker cancellation → status `cancelled`, `JobCancelled` emitted.

## Boot configuration

### `cordis.yml` (defaults shipped in the package)

```yaml
# src/omniscribe/config/cordis.yml
plugins:
  - id: runtime
    use: omniscribe.plugins.runtime:plugin
    config:
      cleanup_interval_seconds: 60
      artifact_ttl_seconds: 86400
      channel_ttl_seconds: 600

  - id: logging
    use: omniscribe.plugins.logging:plugin
    config:
      format: ${OMNISCRIBE_LOG_FORMAT:-text}
      level: ${OMNISCRIBE_LOG_LEVEL:-INFO}

  - id: state_backend
    use: omniscribe.plugins.state_backend:plugin
    config:
      backend: ${OMNISCRIBE_STATE_BACKEND:-memory}
      sqlite_path: ${OMNISCRIBE_STATE_DB_PATH:-}

  - id: artifacts
    use: omniscribe.plugins.artifacts:plugin

  - id: jobs
    use: omniscribe.plugins.jobs:plugin
    config:
      worker_count: 1

  - id: progress
    use: omniscribe.plugins.progress:plugin
    config:
      frame_cap: 1000

  - id: providers
    use: omniscribe.plugins.providers:plugin
    config:
      discovery_timeout_seconds: 5

  - id: health
    use: omniscribe.plugins.health:plugin

  - id: ocr
    use: omniscribe.plugins.ocr:plugin
    config:
      max_upload_mb: 64
      quality_loop_enabled: ${OMNISCRIBE_QUALITY_LOOP:-true}
      quality_target: ${OMNISCRIBE_QUALITY_TARGET:-0.85}
      quality_max_retries: ${OMNISCRIBE_QUALITY_MAX_RETRIES:-2}
```

### Patch layering

Applied in order, each layer deep-merges with the prior layer's row keyed by
`id` (later fields override earlier fields; missing fields are inherited;
lists are replaced, not merged):

1. Base file (`src/omniscribe/config/cordis.yml`).
2. `<artifact_dir>/cordis.patch.yml` if present (operator-local overrides).
3. `--patch <path>` CLI argument (one-shot override, e.g. for tests).
4. `OMNISCRIBE_PLUGIN_<ID>_<FIELD>` env overrides at runtime. The field
   path uses `__` as a separator (`OMNISCRIBE_PLUGIN_RUNTIME__CLEANUP_INTERVAL_SECONDS=120`
   sets `runtime.config.cleanup_interval_seconds` to `120`). Values are
   coerced to the type declared in the plugin's pydantic `Schema`.

A row's `use` field can also be replaced to swap the plugin implementation
itself. The merged result is validated against the resolved plugin's
`Schema` and the loader refuses to mount if validation fails.

## Boot sequence

```python
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    _validate_runtime_settings(settings)
    ctx = await load_harness(settings)         # reads cordis.yml + patches + env overrides
    app.state.context = ctx
    try:
        yield
    finally:
        await ctx.dispose()                     # reverses every effect in LIFO order

def create_app() -> ASGIApplication:
    ...
    @asynccontextmanager
    async def lifespan(app): ...

    web_app = fastapi.FastAPI(lifespan=lifespan)

    # Deferred router mounts (registered as effects at plugin apply time)
    for route in ctx.routes():
        web_app.include_router(route)

    return web_app
```

## Files

### New

```
src/omniscribe/harness/
  __init__.py
  context.py            # Context, EffectRef, ServiceNotFoundError, ContextDisposedError
  service.py            # Service Protocol marker
  events.py             # SessionEvent, AgentEvent, CapabilityEvent, Event base
  effects.py            # EffectScope, effect registration
  config.py             # pydantic Schema helpers, env expansion
  loader.py             # YAML loader + patch resolution
  plugin.py             # Plugin base class
  errors.py             # exceptions

src/omniscribe/plugins/
  __init__.py
  runtime.py            # lifespan + cleanup loop
  logging.py            # structured logging
  state_backend.py      # StateBackend Protocol + Memory + SQLite impls
  artifacts.py          # ArtifactStore composite
  jobs.py               # JobQueue + InMemoryJobQueue worker
  progress.py           # ProgressService + WS handler
  providers.py          # ProviderManager (catalog + discovery, settings-only)
  health.py             # /api/health, /api/healthz, /ready, /readyz
  ocr/
    __init__.py
    plugin.py           # OCRServiceImpl + router registration
    schemas.py          # Pydantic request/response models
    pipeline_bridge.py  # request → OCRPipeline.run adapter
    events.py           # JobQueued, JobStarted, ProgressFrame, JobCompleted, JobFailed, JobCancelled

src/omniscribe/config/
  cordis.yml            # default plugin tree
  cordis.patch.yml.example  # example operator-local patch (gitignored real one)

tests/harness/
  test_context.py
  test_events.py
  test_effects.py
  test_loader.py
  test_plugin_base.py

tests/plugins/
  test_runtime_plugin.py
  test_logging_plugin.py
  test_state_backend_plugin.py
  test_state_backend_memory.py
  test_state_backend_sqlite.py
  test_artifacts_plugin.py
  test_jobs_plugin.py
  test_progress_plugin.py
  test_providers_plugin.py
  test_health_plugin.py
  test_ocr_plugin.py

tests/routers/
  test_process_sync.py
  test_process_async.py
  test_process_status.py
  test_jobs_endpoints.py
  test_progress_ws.py
  test_progress_session.py
  test_health_endpoints.py
  test_config_endpoints.py
  test_openapi_schema.py
```

### Modified

- `src/omniscribe/server.py` — replace the clean-slate shell with the harness
  loader + lifespan.
- `src/omniscribe/config.py` — keep `RuntimeSettings`; add `cordis_config_path`,
  `cordis_patch_paths`, and helpers for harness-level settings.
- `pyproject.toml` — verify `pyyaml>=6.0` is present.
- `tests/conftest.py` — add a `harness_ctx` fixture that loads a temp
  `cordis.yml` pointing at in-memory state.
- `AGENTS.md` — update "Key Files", "Core Paths", "Plugin Context Migration
  Status", "Conventions", "Web Notes", "Known Tech Debt", "See Also".
- `ARCHITECTURE.md` — add a Plugin Tree section, update the diagram, list
  plugin responsibilities.
- `CHANGELOG.md` — "Rebuilt API on Cordis-style plugin harness" entry.
- `tests/openapi.json` — regenerate.

### Deleted

- `tests/api/` (entire tree).

## Tests strategy

- `tests/harness/` — unit tests for `Context`, `Service` Protocol resolution,
  `events` dispatch, `effects` cleanup LIFO ordering, `loader` YAML/patch
  resolution, `Plugin` base contract.
- `tests/plugins/` — per-plugin tests. Each plugin test loads the harness with
  a minimal `cordis.yml` and asserts on the registered services, emitted
  events, and observable side effects. SQLite state tests use `tmp_path`
  fixture for the DB file.
- `tests/routers/` — FastAPI `TestClient` tests against a fixture-loaded
  harness. End-to-end happy paths for each route, plus the failure paths
  spelled out above (404/403/409/410/500).
- The `harness_ctx` fixture in `tests/conftest.py` is the single boundary
  that wires everything for plugin + router tests.

## Migration risk and rollback

- The deleted API had no users outside the frontend. The frontend changes in
  the working tree already point at the route shape we're rebuilding.
- If something goes wrong mid-rebuild, `git stash` on the rebuild work and
  `git checkout HEAD -- src/omniscribe/server.py pyproject.toml` restores
  the clean-slate shell.
- The frontend bundle hash in `src/omniscribe/static/index.html` is currently
  out of sync; resolving that is a separate task.

## Acceptance criteria

1. `uv run pytest -m "not slow"` passes.
2. `uv run ruff check src tests` and `uv run ruff format src tests --check`
   pass.
3. `uv run mypy src` passes.
4. `uv run omniscribe-server --port 8000` boots and serves `/api/health`,
   `/api/process`, `/api/process/async`, `/api/process/status/{job_id}`,
   `/api/progress/session`, `/api/progress/ws/{channel_id}`, `/api/jobs`,
   `/api/jobs/{job_id}/result`.
5. `OMNISCRIBE_STATE_BACKEND=sqlite uv run omniscribe-server --port 8001`
   boots the SQLite backend without error; restarting the process preserves
   jobs and artifacts.
6. The boot log line lists the nine mounted plugins in order.
7. Bad `OMNISCRIBE_STATE_BACKEND` value fails boot with a clear error.
8. The WebSocket handler rejects unauthorized connections with 4401.
9. Cancellation via the WS frame or `/api/progress/cancel/{channel_id}` flips
   the job status to `cancelled` at the next block boundary.
10. Removing one row from `cordis.yml` causes boot to fail with a clear
    "missing dependency" error if a downstream plugin needs it.
