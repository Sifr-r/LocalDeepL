# OmniScribe API Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the OmniScribe HTTP/WebSocket API on a Cordis-style Python plugin harness, restoring OCR + jobs + WebSocket progress + state persistence + health + config endpoints against the route shape the frontend already expects.

**Architecture:** Three layers — a small `omniscribe.harness` package (Context, Service, Event, EffectScope, Loader) that is a faithful Python port of Cordis's primitives; a `omniscribe.plugins` package with nine single-purpose plugins (runtime, logging, state_backend, artifacts, jobs, progress, providers, health, ocr); and `omniscribe.server` which mounts the harness in FastAPI's lifespan and includes the plugin-registered routers. Boot configuration is a `cordis.yml` plugin tree with patch layering.

**Tech Stack:** Python 3.11+, FastAPI, pydantic v2, pyyaml, sqlite3 (stdlib), pytest, pytest-asyncio (auto mode). Uses `contextvars.ContextVar` for plugin-id tracking. No external Cordis port — hand-written port, no dependency.

**Spec:** `docs/superpowers/specs/2026-08-23-omniscribe-api-rebuild-design.md`

---

## File Structure

### New files

```
src/omniscribe/harness/
  __init__.py            # re-exports Context, Plugin, Service, Event
  errors.py              # ServiceNotFoundError, ContextDisposedError, PluginLoadError
  service.py             # Service Protocol marker + Protocol[T] helper
  events.py              # Event base + SessionEvent + AgentEvent + CapabilityEvent
  effects.py             # EffectRef + EffectScope
  context.py             # Context (services, events, effects, lifecycle, router mount)
  plugin.py              # Plugin base class
  config.py              # pydantic Schema helpers + ${VAR:-default} expansion
  loader.py              # Loader: YAML + patches + env overrides + validation + mount

src/omniscribe/plugins/
  __init__.py
  logging.py             # Structured logging config
  runtime.py             # Settings holder + cleanup loop + HarnessReady emission
  state_backend.py       # StateBackend Protocol + Memory + SQLite impls + plugin
  artifacts.py           # ArtifactStore composite (delegates to state)
  jobs.py                # JobQueue Protocol + InMemoryJobQueue worker + plugin
  progress.py            # ProgressService + WS handler with cross-loop marshaling
  providers.py           # ProviderManager (catalog + discovery, settings-only)
  health.py              # /api/health, /api/healthz, /ready, /readyz
  ocr/
    __init__.py
    plugin.py            # OCRServiceImpl + router registration
    schemas.py           # Pydantic request/response models
    pipeline_bridge.py   # request -> OCRPipeline.run adapter
    events.py            # JobQueued, JobStarted, ProgressFrame, JobCompleted, JobFailed, JobCancelled

src/omniscribe/config/
  cordis.yml             # default plugin tree
  cordis.patch.yml.example

tests/harness/
  __init__.py
  test_errors.py
  test_service.py
  test_events.py
  test_effects.py
  test_context.py
  test_plugin_base.py
  test_config.py
  test_loader.py

tests/plugins/
  __init__.py
  test_logging_plugin.py
  test_runtime_plugin.py
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
  __init__.py
  test_process_sync.py
  test_process_async.py
  test_process_status.py
  test_jobs_endpoints.py
  test_progress_session.py
  test_progress_ws.py
  test_health_endpoints.py
  test_config_endpoints.py
  test_openapi_schema.py
```

### Modified files

- `src/omniscribe/server.py` — replace clean-slate shell with harness loader + lifespan.
- `src/omniscribe/config.py` — keep RuntimeSettings; add `cordis_config_path` + `cordis_patch_paths`.
- `pyproject.toml` — verify `pyyaml>=6.0` is present (no change if it is).
- `tests/conftest.py` — add `harness_ctx` fixture that loads a temp `cordis.yml` against in-memory state.
- `AGENTS.md` — update Key Files, Core Paths, Plugin Context Migration Status, Conventions, Web Notes, Known Tech Debt.
- `ARCHITECTURE.md` — add Plugin Tree section; refresh the diagram.
- `CHANGELOG.md` — "Rebuilt API on Cordis-style plugin harness" entry.
- `tests/openapi.json` — regenerated from the running app (delete first, then `pytest tests/routers/test_openapi_schema.py` writes the new one).

### Deleted files

- `tests/api/` (entire tree, per the test-strategy decision in the spec).

---

## Conventions used throughout this plan

- TDD order: failing test → run to verify failure → implementation → run to verify pass → commit.
- pytest-asyncio is in auto mode; write `async def test_...` without `@pytest.mark.asyncio`.
- All file paths are repo-relative; the absolute root is `d:\OmniScribe`.
- Commit messages follow the project's `type(scope): summary` convention.
- Each phase ends with a verification command run from the repo root: `uv run pytest tests/harness tests/plugins -x` (phases 1-6) or `uv run pytest -m "not slow"` (phase 7+).
- `cd` is avoided — every command uses absolute paths.
- PowerShell: do NOT chain with `&&`. Use `;` to separate commands or split into separate calls.

---

## Execution mode

Per user direction this plan is **compact**: full code for the harness foundation
(Phase 1 — everything else depends on its exact shapes), condensed task specs
for Phases 2–9 (file paths, signatures, key logic, verification commands; the
spec document carries the full protocol/route details). Every task still ends
with tests green + a commit.

---

## Phase 1: Plugin Harness Foundation

Build `omniscribe/harness/` — errors, Service, events, effects, Context, Plugin base.

**Phase verification:** `uv run pytest tests/harness -x ; uv run ruff check src/omniscribe/harness tests/harness ; uv run mypy src/omniscribe/harness`

### Task 1: Errors module

**Files:** Create `src/omniscribe/harness/__init__.py`, `src/omniscribe/harness/errors.py`; Test `tests/harness/__init__.py`, `tests/harness/test_errors.py`

- [ ] Write `tests/harness/test_errors.py` asserting: all four classes subclass `HarnessError`; `ServiceNotFoundError("OCRService").protocol_name == "OCRService"`; `ContextDisposedError("unload").operation == "unload"`; `PluginLoadError(row_id="ocr", reason="missing dependency: state_backend")` exposes `.row_id`/`.reason`; each is catchable as `HarnessError`.
- [ ] Run `uv run pytest tests/harness/test_errors.py -v` — expect FAIL (module missing).
- [ ] Implement:

```python
# src/omniscribe/harness/errors.py
"""Exception hierarchy for the plugin harness."""
from __future__ import annotations


class HarnessError(Exception):
    """Base class for every exception the harness raises."""


class ServiceNotFoundError(HarnessError, LookupError):
    def __init__(self, protocol_name: str) -> None:
        self.protocol_name = protocol_name
        super().__init__(f"no service registered for protocol {protocol_name!r}")


class ContextDisposedError(HarnessError, RuntimeError):
    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"context is disposed; cannot {operation}")


class PluginLoadError(HarnessError, RuntimeError):
    def __init__(self, *, row_id: str, reason: str) -> None:
        self.row_id = row_id
        self.reason = reason
        super().__init__(f"plugin {row_id!r} failed to load: {reason}")
```

`__init__.py` re-exports all four names via `__all__`.
- [ ] Run tests — PASS. Commit `feat(harness): add HarnessError hierarchy`.

### Task 2: Service marker

**Files:** Create `src/omniscribe/harness/service.py`; Test `tests/harness/test_service.py`

- [ ] Test: a `@runtime_checkable` Protocol subclass of `Service` matches duck-typed instances via `isinstance`; `service_protocol("Counter", ("increment", "value"))` returns a runtime-checkable Protocol class with `__name__ == "Counter"` whose duck-typed instances pass `isinstance`.
- [ ] Run — FAIL. Implement `Service(Protocol)` marker + `service_protocol(name, methods)` building a runtime-checkable Protocol via `types.new_class` with stub annotations; re-export from `__init__.py`.
- [ ] Run — PASS. Commit `feat(harness): add Service Protocol marker`.

### Task 3: Event bases

**Files:** Create `src/omniscribe/harness/events.py`; Test `tests/harness/test_events.py`

- [ ] Test: `Event` is a frozen dataclass base; `SessionEvent`, `AgentEvent`, `CapabilityEvent` all subclass `Event` and are distinct; frozen dataclass subclasses hash/compare by value.
- [ ] Run — FAIL. Implement:

```python
# src/omniscribe/harness/events.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """Base class for every event the bus dispatches."""


class SessionEvent(Event):
    """Durable fact appended to the session log."""


class AgentEvent(Event):
    """Live progress frame."""


class CapabilityEvent(Event):
    """Seam policy / adapter event."""
```

- [ ] Run — PASS. Commit `feat(harness): add Event domain bases`.

### Task 4: EffectRef + EffectScope

**Files:** Create `src/omniscribe/harness/effects.py`; Test `tests/harness/test_effects.py`

- [ ] Test: `EffectRef` is a frozen dataclass with `plugin_id`/`kind`/`key`; `EffectScope.add` + `aclose()` runs cleanups in LIFO order; async cleanups are awaited; `aclose()` is idempotent; `add` after close raises; an `effect_scope()` async context manager helper runs cleanups on exit.
- [ ] Run — FAIL. Implement `EffectRef` (frozen dataclass), `EffectScope` with `_cleanups: list[Cleanup]` where `Cleanup = Callable[[], Awaitable[None] | None]`, `aclose()` popping from the tail and awaiting coroutine results, and an `@asynccontextmanager` `effect_scope()` helper.
- [ ] Run — PASS. Commit `feat(harness): add EffectRef and EffectScope`.

### Task 5: Context — services

**Files:** Create `src/omniscribe/harness/context.py`; Test `tests/harness/test_context.py`

- [ ] Test: `ctx.service(Proto, instance)` then `ctx.inject(Proto)` returns the same instance; `ctx.has(Proto)` correct; `ctx.inject` unregistered raises `ServiceNotFoundError` carrying the Protocol name; re-registering the same Protocol raises `ValueError`; after `ctx.dispose()`, `ctx.service(...)` raises `ContextDisposedError`.
- [ ] Run — FAIL. Implement `Context` with `_services: dict[type, Any]`, a module-level `_current_plugin_id: contextvars.ContextVar[str | None]`, `service()` recording an `EffectRef(kind="service", key=protocol)` under the current plugin id (default `"<root>"`), `inject()`/`has()`, and `dispose()` setting `_disposed`.
- [ ] Run — PASS. Commit `feat(harness): add Context service registry`.

### Task 6: Context — events, effects, router mount

**Files:** Modify `src/omniscribe/harness/context.py`; Test extend `tests/harness/test_context.py`

- [ ] Test: `ctx.on(E, handler)` + `await ctx.emit(E(...))` invokes handler; exact-type matching (a handler registered for a domain base is NOT invoked when a concrete subclass event is emitted); two handlers run concurrently; a raising handler is logged but does not break others; `ctx.effect(cleanup)` cleanups run in LIFO on dispose; `ctx.mount_router(router)` + `ctx.routes()` returns mount order; `on`/`effect`/`mount_router` after dispose raise `ContextDisposedError`.
- [ ] Run — FAIL. Implement `_listeners: dict[type, list[EventHandler]]` (`EventHandler = Callable[[Event], Awaitable[None] | None]`), `emit()` gathering with `return_exceptions=True` and logging failures via `logging.getLogger("omniscribe.harness")` (sync handlers called inline, coroutines gathered), `_effects: list[tuple[str, Cleanup]]`, `_routers: list[Any]` (typed `Any` so the harness imports without the web extra).
- [ ] Run — PASS. Commit `feat(harness): add Context events, effects, router mount`.

### Task 7: Context — plugin lifecycle

**Files:** Modify `src/omniscribe/harness/context.py`; Test extend `tests/harness/test_context.py`

- [ ] Test: `await ctx.plugin(instance, config={...})` sets `plugin.id`/`plugin.config` and calls `apply(ctx)`; registrations inside `apply` are attributed to the plugin id; `ctx.unload(id)` removes exactly that plugin's services/effects/listeners/routers (LIFO cleanup order), leaving other plugins intact; `dispose()` unloads every plugin in reverse mount order, awaiting each cleanup exactly once; second `dispose()` is a no-op.
- [ ] Run — FAIL. Implement `plugin()` setting the `_current_plugin_id` contextvar around `apply`, tracking `_plugin_order` + `_plugin_effects: dict[str, list[EffectRef]]`; `unload()` reversing that plugin's refs by kind (service → drop from `_services`; effect → await cleanup; listener → remove handler; router → drop from `_routers`); `dispose()` iterating `reversed(_plugin_order)` then clearing everything.
- [ ] Run — PASS. Commit `feat(harness): add Context plugin lifecycle with reversible effects`.

### Task 8: Plugin base class

**Files:** Create `src/omniscribe/harness/plugin.py`; Test `tests/harness/test_plugin_base.py`

- [ ] Test: `Plugin` defaults (`id == ""`, `config == {}`, `Schema is None`); default `apply`/`dispose` are awaitable no-ops; subclass `apply` receives the Context.
- [ ] Run — FAIL. Implement:

```python
# src/omniscribe/harness/plugin.py
from __future__ import annotations
from typing import TYPE_CHECKING, Any, ClassVar
from pydantic import BaseModel

if TYPE_CHECKING:
    from omniscribe.harness.context import Context


class Plugin:
    """Base class for every harness plugin."""

    id: str = ""
    config: dict[str, Any] = {}
    Schema: ClassVar[type[BaseModel] | None] = None

    async def apply(self, ctx: "Context") -> None: ...
    async def dispose(self) -> None: ...
```

- [ ] Run — PASS. Commit `feat(harness): add Plugin base class`.

Finally update `src/omniscribe/harness/__init__.py` to re-export `Context`, `Plugin`, `Loader` (added in Phase 2), and commit `feat(harness): finalize package exports`.

---

## Phase 2: Loader

**Files:** Create `src/omniscribe/harness/config.py`, `src/omniscribe/harness/loader.py`; Tests `tests/harness/test_config.py`, `tests/harness/test_loader.py`

### Task 9: Env expansion (`config.py`)

- [ ] Test `expand_env("${VAR:-default}", row_id="x")`: unset var → `"default"`; set var → value; no `${...}` → unchanged; `${VAR}` unset with no default → `PluginLoadError`; non-string leaves recurse structurally through dicts/lists.
- [ ] Implement `expand_env(value: Any, *, row_id: str) -> Any` with regex `\$\{([A-Z0-9_]+)(?::-([^}]*))?\}` applied recursively to strings inside dicts/lists.
- [ ] Commit `feat(harness): add ${VAR:-default} env expansion`.

### Task 10: YAML row parsing + deep merge (`loader.py`)

- [ ] Test: `parse_rows(yaml_text)` returns `list[PluginRow]` (`@dataclass PluginRow(id: str, use: str, config: dict[str, Any])`); missing `id`/`use` → `PluginLoadError`; `deep_merge(base, patch)` merges keyed by `id` — later fields override, missing fields inherited, lists replaced, new ids appended.
- [ ] Implement with `yaml.safe_load`; validate row shape before construction.
- [ ] Commit `feat(harness): add cordis.yml row parsing and patch deep-merge`.

### Task 11: Plugin lookup + schema validation + Loader.load

- [ ] Test: `resolve_plugin("module.path:attr")` imports and returns the attribute; bad module/attr → `PluginLoadError`; validation instantiates `plugin_class.Schema(**row.config)` when set and stores the validated dict; full `await Loader(ctx).load(base_path, patch_paths=())` mounts rows in declared order (temp dir + cordis.yml mounting two trivial in-test plugins that register services; assert both injectable and order preserved); `OMNISCRIBE_PLUGIN_<ID>__<FIELD>` env overrides apply (uppercased id/field, `__` separator, value coerced by Schema field type).
- [ ] Implement `Loader`: read base → apply patches in order → expand env → resolve class → validate → `await ctx.plugin(instance, config=validated)`; wrap every failure in `PluginLoadError(row_id=...)`; log one INFO line listing mounted plugin ids in order.
- [ ] Commit `feat(harness): add Loader with plugin lookup, schema validation, mount order`.

---

## Phase 3: Logging + Runtime Plugins

### Task 12: Logging plugin (`plugins/logging.py`)

- [ ] Test: mounting with `config={"format": "text", "level": "INFO"}` invokes the `omniscribe.utils.structured_logging` configure path (monkeypatch to observe); registers no service (side-effect plugin).
- [ ] Implement `LoggingPlugin(Plugin)` with pydantic `Schema(format: Literal["text","json"]="text", level: str="INFO")`; module-level `plugin = LoggingPlugin()` factory attribute (every plugin module exposes `plugin`).
- [ ] Commit `feat(plugins): add logging plugin`.

### Task 13: Runtime plugin (`plugins/runtime.py`)

- [ ] Test: registers `RuntimeService` (Protocol: `settings`, `ready: bool`, `mark_ready()`, `async shutdown()`) on ctx; cleanup loop task starts as an effect (monkeypatch sleep + prune to observe one iteration); emits `HarnessReady(SessionEvent)` on `mark_ready()`; unload cancels the loop task.
- [ ] Implement with `Schema(cleanup_interval_seconds: int = 60, artifact_ttl_seconds: int = 86400, channel_ttl_seconds: int = 600)`; cleanup loop injects `StateBackend` lazily (debug-log skip when absent so the plugin mounts standalone in tests).
- [ ] Commit `feat(plugins): add runtime plugin with cleanup loop`.

---

## Phase 4: State Backend

**Files:** Create `src/omniscribe/plugins/state_backend.py`; Tests `tests/plugins/test_state_backend_memory.py`, `test_state_backend_sqlite.py`, `test_state_backend_plugin.py`

### Task 14: Records + StateBackend Protocol

- [ ] Define in `state_backend.py`: `JobStatus = Literal["queued","running","complete","error","cancelled"]`; frozen dataclasses `ArtifactRecord(id, token, owner_job_id, content_type, blob_path, created_at, ttl_seconds)`, `JobRecord(job_id, status, request_meta: dict[str, Any], result_artifact_id: str | None, created_at, updated_at, error: str | None)`, `ChannelRecord(channel_id, session_token, job_id, created_at)`; the `StateBackend` Protocol exactly per the spec (artifact put/get/delete/prune; job upsert/get/list/clear/delete; channel put/get/consume/delete/prune).
- [ ] Commit `feat(state): add StateBackend Protocol and record types`.

### Task 15: MemoryStateBackend

- [ ] Test every Protocol method: artifact put/get/delete round-trip; wrong token → None; `prune_expired_artifacts(now)` removes only expired rows and returns the count; job upsert/get/list(limit)/clear/delete; channel put/get/consume (one-shot: second consume → None)/delete/prune.
- [ ] Implement with dicts + one `asyncio.Lock`; blobs in a dict capped at 256 MB (`ValueError` on exceed).
- [ ] Commit `feat(state): add MemoryStateBackend`.

### Task 16: SQLiteStateBackend

- [ ] Test the same surface with `tmp_path` db + artifact dir: schema auto-created, `PRAGMA journal_mode=WAL`; blobs written to `<artifact_dir>/<id>.bin` and deleted with the artifact; persistence across close/reopen.
- [ ] Implement stdlib `sqlite3` via `asyncio.to_thread`, one connection behind a lock; three tables per the spec's Persistence section; blob bytes never stored in the DB.
- [ ] Commit `feat(state): add SQLiteStateBackend`.

### Task 17: state_backend plugin factory

- [ ] Test: `{"backend": "memory"}` registers the Memory impl under `StateBackend`; sqlite config registers the SQLite impl; `backend="redis"` → clear `ValueError` naming the allowed set; empty sqlite path resolves to `<artifact_dir>/omniscribe-state.db` (monkeypatch the artifact dir).
- [ ] Implement `StateBackendPlugin(Plugin)` + `plugin` attribute; `Schema(backend: Literal["memory","sqlite"] = "memory", sqlite_path: str = "")`.
- [ ] Commit `feat(plugins): add state_backend plugin`.

---

## Phase 5: Storage Plugins

### Task 18: Artifacts plugin (`plugins/artifacts.py`)

- [ ] Test: `put(blob, content_type=..., owner_job_id=...)` returns `ArtifactHandle(id, token)` (token shape matches `secrets.token_urlsafe(32)`); `get` round-trips bytes; wrong token → None; `delete` removes; every `put` emits `ArtifactCreated(SessionEvent)` carrying the artifact id.
- [ ] Implement `ArtifactStore` Protocol + impl delegating to the injected `StateBackend`; ids via `uuid.uuid4().hex`.
- [ ] Commit `feat(plugins): add artifacts plugin`.

### Task 19: JobQueue + InMemoryJobQueue (`plugins/jobs.py`)

- [ ] Test: `submit(request)` → `JobHandle(job_id, status_url)` + a `queued` record in state; the worker claims it, runs the injected runner, stores the result artifact, marks `complete`; a raising runner → `error` with message stored; `cancel(job_id)` on a queued job → `cancelled` before it runs; `status/result/list/clear` delegate to state.
- [ ] Implement `JobQueue` Protocol (spec signatures) + `InMemoryJobQueue` with `asyncio.Queue` + one worker task started as an effect; runner injected as `Callable[[OCRRequest], Awaitable[OCRResult]]` so tests fake OCR; shutdown effect cancels the worker and marks pending jobs `cancelled`.
- [ ] Commit `feat(plugins): add in-memory single-worker job queue`.

### Task 20: ProgressService + WS handler (`plugins/progress.py`)

- [ ] Test (service): `open_channel()` → `ChannelHandle(channel_id, session_token)` persisted via state; `broadcast(channel_id, frame)` fans out to connected sockets and returns the count; `cancel(channel_id)` flips the cancelled flag.
- [ ] Test (handler via `TestClient.websocket_connect` on a mini FastAPI app): valid `?token=` connects and receives a broadcast frame; wrong token → close code 4401; client `{"type":"cancel"}` frame flips the flag; foreign-loop sends are marshaled onto the accept loop (record the accept loop on connect; `asyncio.run_coroutine_threadsafe` for sends from other loops — the cross-loop marshaling contract).
- [ ] Implement `ProgressService` Protocol + impl + router: POST `/api/progress/session`, WS `/api/progress/ws/{channel_id}`, POST `/api/progress/cancel/{channel_id}`; frame vocabulary exactly per the spec's WebSocket protocol section; per-channel `frame_cap` from `Schema(frame_cap: int = 1000)`.
- [ ] Commit `feat(plugins): add progress plugin with cross-loop WS marshaling`.

---

## Phase 6: HTTP Plugins

### Task 21: Providers plugin (`plugins/providers.py`)

- [ ] Test: `list_providers()` builds from `omniscribe.core.llm.providers.PROVIDER_TEMPLATES`; `get_active()` reflects `RuntimeSettings` (`llm_api_base`, `llm_model`); `discover_models(provider_name)` calls the provider's `/v1/models` via httpx (monkeypatched) honoring `discovery_timeout_seconds`; `set_active` writes back into settings.
- [ ] Implement `ProviderManager` Protocol + settings-only impl + `plugin`; no disk persistence (follow-up spec).
- [ ] Commit `feat(plugins): add providers plugin`.

### Task 22: Health plugin (`plugins/health.py`)

- [ ] Test (TestClient): GET `/api/health`, `/api/healthz` → 200 `{"status":"ok"}` always; GET `/ready`, `/readyz` → 503 `{"status":"starting"}` until `RuntimeService.mark_ready()`, then 200 `{"status":"ready"}`.
- [ ] Implement router factory + `plugin` calling `ctx.mount_router(...)`.
- [ ] Commit `feat(plugins): add health plugin`.

### Task 23: OCR schemas (`plugins/ocr/schemas.py`)

- [ ] Test: `OCRRequest` parses the FormData field set the frontend sends (`model`, `api_base`, `api_key`, `pipeline_mode`, `dense_mode`, `spellcheck`, `document_processors` CSV, `preprocess_pages` + the five per-page toggles, `progress_channel`, `progress_token`, `quality_loop_enabled`, `quality_target` 0.5–1.0, `quality_max_retries` 0–5); out-of-range `quality_target` → pydantic ValidationError; `AsyncSubmitResponse(job_id, status_url)` + `JobStatusResponse` match the frontend's `OcrJobStatusResponse` shape.
- [ ] Commit `feat(ocr): add OCR request/response schemas`.

### Task 24: Pipeline bridge (`plugins/ocr/pipeline_bridge.py`)

- [ ] Test: `build_pipeline(settings, request)` returns a configured `OCRPipeline` (assert `document_processors`, page preprocessor on/off per toggles, quality repair options per fields); `run_pipeline(pipeline, file_bytes, filename, on_progress)` adapts core callbacks into `ProgressFrame` events (monkeypatch `OCRPipeline.run`).
- [ ] Commit `feat(ocr): add pipeline bridge`.

### Task 25: OCR events (`plugins/ocr/events.py`)

- [ ] Define frozen dataclasses `JobQueued`, `JobStarted`, `ProgressFrame` (AgentEvent), `JobCompleted`, `JobFailed`, `JobCancelled` subclassing the right domain bases; test construction + field access.
- [ ] Commit `feat(ocr): add job event types`.

### Task 26: OCR plugin + router (`plugins/ocr/plugin.py`)

- [ ] Test (TestClient on a harness-loaded mini app with a fake pipeline): POST `/api/process` → PDF blob + artifact headers; POST `/api/process/async` → `{job_id, status_url}`; GET `/api/process/status/{job_id}` → record / 404 unknown; GET `/api/jobs` lists, DELETE `/api/jobs` clears; GET `/api/jobs/{job_id}/result?token=` → blob / 403 wrong token / 404 unknown / 409 errored; POST `/api/jobs/{job_id}/cancel`; GET/PUT `/api/config/ocr` round-trips the non-secret config; upload over `max_upload_mb` → 413; GET `/api/process/{job_id}/events` streams job events (SSE).
- [ ] Implement `OCRService` Protocol + `OCRServiceImpl` (wraps the bridge; `run_async` submits to the injected `JobQueue`; emits Task-25 events at each transition; forwards `ProgressFrame`s to `ProgressService.broadcast` when the request carried a `progress_channel`) + `build_ocr_router()` with every route from the spec's route table.
- [ ] Commit `feat(plugins): add OCR plugin with full route surface`.

---

## Phase 7: Boot Integration

### Task 27: cordis.yml + patch example

- [ ] Create `src/omniscribe/config/cordis.yml` exactly per the spec's Boot configuration section (nine rows: runtime, logging, state_backend, artifacts, jobs, progress, providers, health, ocr) + `cordis.patch.yml.example` showing one config override.
- [ ] Test: `Loader` loads the shipped file into a Context with all nine services injectable (monkeypatch httpx where providers discovers).
- [ ] Commit `feat(config): add default cordis.yml plugin tree`.

### Task 28: config.py additions

- [ ] Add to `RuntimeSettings`: `cordis_config_path: Path` (default `<package>/config/cordis.yml`), `cordis_patch_paths: tuple[Path, ...]` (default `(<artifact_dir>/cordis.patch.yml,)` filtered to files that exist); env overrides `OMNISCRIBE_CORDIS_CONFIG`, `OMNISCRIBE_CORDIS_PATCH`. Test defaults + overrides.
- [ ] Commit `feat(config): add cordis config path settings`.

### Task 29: server.py lifespan + create_app

- [ ] Replace the clean-slate shell: lifespan loads settings, validates them (`_validate_runtime_settings` kept), calls `Loader(...).load(...)`, stores ctx on `app.state.context`, includes `ctx.routes()`, calls `RuntimeService.mark_ready()`, and disposes on shutdown. Keep `/` static index, `LazyASGIApp`, CLI `main`, `_load_optional_module` guards.
- [ ] Test (TestClient + in-memory state): `/api/health` 200; `/api/process/status/unknown` 404; lifespan dispose runs effect cleanups (observe via a test plugin); bad `OMNISCRIBE_STATE_BACKEND` fails `create_app()` boot with a clear message.
- [ ] Commit `feat(server): mount Cordis-style harness in FastAPI lifespan`.

---

## Phase 8: Test Cleanup + Fixtures

### Task 30: Delete tests/api/ + conftest fixtures

- [ ] `git rm -r tests/api`; strip now-dead imports/fixtures referencing the old app from `tests/conftest.py`.
- [ ] Add `harness_ctx` fixture to `tests/conftest.py`: writes a temp `cordis.yml` (same nine rows, `state_backend: memory`, tiny TTLs), loads it into a fresh Context, yields it, disposes after. Add `api_client` fixture building a TestClient on `create_app()` with `OMNISCRIBE_CORDIS_CONFIG` pointed at the temp file.
- [ ] Run the fast gate: `uv run ruff check src tests ; uv run ruff format src tests --check ; uv run mypy src ; uv run pytest -m "not slow"`.
- [ ] Commit `test: remove legacy api tests, add harness fixtures`.

### Task 31: Router tests + openapi.json

- [ ] Port the Task 20/22/26 TestClient tests into `tests/routers/` using the `api_client` fixture (test_process_sync, test_process_async, test_process_status, test_jobs_endpoints, test_progress_session, test_progress_ws, test_health_endpoints, test_config_endpoints).
- [ ] `tests/routers/test_openapi_schema.py` writes `tests/openapi.json` when missing and diffs otherwise; delete the stale file first, run once to regenerate.
- [ ] Commit `test: add router tests and regenerate openapi.json`.

---

## Phase 9: Documentation

### Task 32: AGENTS.md + ARCHITECTURE.md + CHANGELOG.md

- [ ] AGENTS.md: add `src/omniscribe/harness/` + `src/omniscribe/plugins/` rows to Key Files and Core Paths; replace the "Plugin Context Migration Status" section with the new nine-plugin tree table; update Web Notes (quality-loop env seeds, model pre-flight, WS marshaling now in `plugins/progress.py`); update Known Tech Debt (single-worker in-memory queue, redis + multi-worker deferred); bump the last-updated stamp.
- [ ] ARCHITECTURE.md: add a "Plugin Tree" section with the boot-order diagram + per-plugin responsibilities; refresh the pipeline-paths caption (API layer now plugin-mounted).
- [ ] CHANGELOG.md: new entry "Rebuilt API on Cordis-style plugin harness" (routes restored, deferred capabilities, state-backend env contract).
- [ ] Commit `docs: update AGENTS/ARCHITECTURE/CHANGELOG for plugin-harness rebuild`.

---

## Final Verification

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

Then manually: boot `uv run omniscribe-server --port 8000`, confirm `/api/health` → `{"status":"ok"}` and the boot log lists nine mounted plugins in order; then the SQLite persistence check (`OMNISCRIBE_STATE_BACKEND=sqlite`, submit an async job, restart, confirm the job record survives).
