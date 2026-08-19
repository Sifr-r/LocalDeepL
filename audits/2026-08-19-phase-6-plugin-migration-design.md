# Phase 6 — Plugin Context Migration Completion: Design Doc

**Date:** 2026-08-19
**Scope:** Close audit-secondary F2-deeper, F11, F13, F27 in one cohesive phase.
**Companion:** `audits/2026-08-19-secondary-validation-pass.md` (findings #2, #11, #13, #27).
**Status:** design — awaiting user "go" before any code change.

---

## TL;DR

Four findings, one cohesive change. Boot the three remaining seams (ConfigStore / ProgressService / TextArtifactStore×3), make the `PLUGIN_CONTEXT_ENABLED` flag a `ConfigStore`-backed runtime toggle, add `threading.RLock` to the `PluginContext` mutation surface, and document the disposal-ordering contract.

Single PR, ~1 day, low–medium risk. Touches the new infra at its foundation; all four items are needed to land before a future `CeleryJobQueue` provider can be wired without foot-guns.

---

## Background — what each finding really is

### F2 (deeper) — three of five seams unregistered at boot

`server.py:117-135` registers only `JobQueue` and `SessionLog` providers. The three other seams (`ConfigStore`, `ProgressService`, `TextArtifactStore`) are defined in `seams.py`, re-exported in `__init__.py`, and have provider functions in `providers.py` — but boot never calls `plugin_ctx.mount(...)` for them. Every consumer that does `get_text_artifact_store()` gets `None` and falls through to `state.text_artifacts`.

**Why deferred:** the `Phase 1` documentation in `AGENTS.md` already lists the 5 seams + their boot state. The actual wiring was deferred because the providers all need F11 (runtime toggle) to coexist with the env-var-driven path.

**Design choice — register at boot, opt-in via the flag:**
- In `server.py:117-135`, mount the three remaining providers right after the existing two
- `ConfigStore` — pass `state.config_store` (already populated by the StateBackend factory in `state.py`)
- `ProgressService` — pass `state.progress_service` (the existing singleton, stateless — safe to share)
- `TextArtifactStore` — mount THREE providers under the canonical domain names: `text` (passes `state.text_artifacts`), `metadata` (passes `state.metadata_artifacts`), `export` (passes `state.export_artifacts`)
- The boot mounts are unconditional (same as the existing two); the `PLUGIN_CONTEXT_ENABLED` flag only gates consumer *behavior*, not provider *registration*

**Why not delete the three seams (the other option in the audit):** the providers and seams are already coded, tested, and documented. Deleting them is a regression — the next time someone needs `get_config_store()` they'll reinvent them. Cost of wiring is ~6 lines in `server.py`; cost of deletion-and-reinvention is much higher.

### F11 — `PLUGIN_CONTEXT_ENABLED` is a module constant, not runtime-togglable

`runtime.py:65` reads the env var at import. The flag is fixed for the life of the process. An operator who wants to flip the flag at runtime has to restart the server.

**Design choice — ConfigStore-backed, env-var-seeded, hot-reloadable:**

```python
# runtime.py (new lookup chain)
def is_plugin_context_enabled() -> bool:
    """Read in priority order: ConfigStore override → env-var-cached → False."""
    store = get_config_store()  # new helper, may return None
    if store is not None:
        snapshot = store.get_snapshot()
        if "plugin_context_enabled" in snapshot:
            return bool(snapshot["plugin_context_enabled"])
    # Fall back to the env-var-cached module constant.
    return PLUGIN_CONTEXT_ENABLED
```

Concretely:
- The env var `OMNISCRIBE_PLUGIN_CONTEXT` continues to seed the module-level `PLUGIN_CONTEXT_ENABLED` at import (no behavior change for existing operators)
- At boot, after the `ConfigStore` provider is mounted, the server reads the env-var default and writes it to `ConfigStore.update({"plugin_context_enabled": <bool>})` if no key exists yet
- `is_plugin_context_enabled()` becomes a function that consults the store first, then the module constant
- The existing `set_plugin_context_enabled(value)` test helper is kept for tests that want to bypass the store
- `/api/config` POST handlers can now flip the flag; the next `is_plugin_context_enabled()` call returns the new value

**Why not move the flag entirely to `ConfigStore`:** env vars are the standard Kubernetes/Docker deployment knob. Removing the env var would break the existing operator workflow. Layering the store on top preserves both.

**Why this is a Phase 6 item, not a Phase 2 item:** the design requires F2-deeper (ConfigStore provider must be mounted) to work. Wiring F2 and F11 together in one phase avoids a "register but the flag ignores it" intermediate state.

### F13 — `plugin_ctx.dispose()` ordering vs queue lifecycle

`server.py:149-161`:
```python
finally:
    await _stop_artifact_cleanup(cleanup_task)
    await state.ocr_job_queue.stop()
    ...
    set_plugin_context(None)
    plugin_ctx.dispose()
```

For the current `local_job_queue_provider(queue=state.ocr_job_queue, name="local")`, the disposer returned by `register(JobQueue, ...)` only *unregisters* the service entry — it doesn't call `impl.stop()`. The `stop()` happens explicitly in the lifespan finally-block, BEFORE `plugin_ctx.dispose()`. This is the right order for the local queue because the lifespan block owns the queue.

For a future `CeleryJobQueue` provider that wraps a worker task, the natural pattern is: the provider owns the worker lifecycle; the provider's disposer should call `worker.shutdown()`. The lifespan block can't know which queue variant is mounted.

**Design choice — provider-owned disposal via `ctx.effect(...)`:**

Extend the provider signature so each provider can register its OWN teardown effect. The effect runs as part of `ctx.dispose()` in LIFO order, alongside the service-unregister effect. The lifespan finally-block stops calling `state.ocr_job_queue.stop()` directly for the local case; it just calls `plugin_ctx.dispose()` and the provider's teardown handles the rest.

```python
# providers.py (local_job_queue_provider, new shape)
def local_job_queue_provider(
    queue: OCRJobQueue | None = None, *, name: str = "local",
) -> Callable[[PluginContext], Callable[[], None]]:
    impl = queue if queue is not None else OCRJobQueue()

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        unregister = ctx.register(JobQueue, impl, name=name)
        # Provider-owned teardown: stop the worker BEFORE the service
        # entry is removed. ctx.effect() registers this on the same
        # EffectScope as the unregister disposer, in registration order;
        # dispose() runs them in LIFO order — so the stop fires first,
        # then the unregister. No half-disposed state.
        def _stop() -> None:
            # Disposers are sync, but the queue's stop is async; we
            # hand the future to the lifespan's finally block via a
            # thread-safe queue OR we make the disposer a coroutine
            # (see below).
            ...

        ctx.effect(_stop)
        return unregister
    return _plugin
```

The `Disposer = Callable[[], None]` signature is a problem for async teardown. Two options:

**Option A — sync wrapper that drives the coroutine:**
```python
def _stop() -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # The lifespan finally block is already awaiting ctx.dispose()
            # in a sync fashion; we can't await here. Schedule the stop
            # on the next loop iteration and let the lifespan block
            # `await` it after ctx.dispose() returns.
            ...
```
This is racy and ugly.

**Option B — make the disposer a coroutine, update `EffectScope.dispose()` to handle both:**
```python
# effects.py
Disposer = Callable[[], None | Awaitable[None]]

async def dispose(self) -> None:
    while self._stack:
        disposer = self._stack.pop()
        result = disposer()
        if inspect.iscoroutine(result):
            await result
```

This is the correct shape but ripples through every existing disposer. Most are sync no-ops; the change is opt-in.

**Decision: Option B, with backwards compat.** Existing sync disposers continue to work; new providers can return a coroutine. `EffectScope.dispose()` becomes `async def`. `PluginContext.dispose()` becomes `async def`. The lifespan finally-block awaits it. Every existing test that calls `ctx.dispose()` synchronously gets a `RuntimeWarning` (sync `dispose()` on an async surface) but the test passes because there are no coroutine disposers in those tests.

**Documented ordering contract:**
- Disposers run in LIFO order across all effects registered on the context (including service unregisters, plugin disposers, and provider-owned effects)
- Service unregister fires AFTER provider-owned teardown (because provider-owned effect is registered after the service, and LIFO unwinds in reverse)
- The lifespan finally-block's `await plugin_ctx.dispose()` is the canonical teardown; any explicit `state.<service>.stop()` call in the lifespan is a layering violation that should be migrated to a provider-owned effect

### F27 — `PluginContext` mutation is not thread-safe

`context.py:35-44` acknowledges this in the docstring. The contract is "mount during boot, query during request, dispose at shutdown." For that contract, only the mutation path (register, unregister, swap, on, off, mount) needs locking; reads are atomic-enough on CPython dicts.

**Design choice — `threading.RLock` on the mutation surface:**

```python
# context.py
import threading

class PluginContext:
    def __init__(self, name: str = "root") -> None:
        ...
        self._lock = threading.RLock()  # RLock for nested mount-during-mount

    def register(self, ...) -> Disposer:
        with self._lock:
            self._assert_not_disposed("register")
            ...
            return self._effects.effect(lambda: self._services.pop(key, None))

    def unregister(self, ...) -> bool:
        with self._lock:
            self._assert_not_disposed("unregister")
            return self._services.pop((definition, name), None) is not None

    def swap(self, ...) -> Disposer:
        with self._lock:
            ...
    def on(self, ...) -> Disposer:
        with self._lock:
            ...
    def off(self, ...) -> bool:
        with self._lock:
            ...
    def mount(self, plugin: Any) -> Disposer:
        with self._lock:
            ...
    async def dispose(self) -> None:  # now async
        with self._lock:
            if self._disposed:
                return
            self._disposed = True
            await self._effects.dispose()  # now async
            self._services.clear()
            self._listeners.clear()
```

Reads (`get`, `has`, `service_names`, `listeners`, `emit`, `parallel`, `serial`, `waterfall`, `_maybe_log_event`) are NOT locked. This is deliberate — the read path is the hot path (every request handler hits `get_*` helpers), and adding a lock there would be a regression. CPython's GIL makes dict reads atomic; the read can race with an in-progress mount and either see the pre- or post-mount state, both of which are well-defined for the boot-only-mutation contract.

**Why `threading.RLock` not `asyncio.Lock`:** the audit calls out "thread-safe" not "async-safe". A `threading.RLock` protects against real OS-thread concurrency (e.g. a thread-pool that drives boot in parallel with the FastAPI startup), which is the actual concern. The `asyncio` event loop is single-threaded; an `asyncio.Lock` would protect against `await`-point interleaving within one loop, which isn't the threat model.

**Test:** a new `test_phase6_thread_safe_register_during_dispatch` test that spawns 4 threads × 50 `register` calls each (different `name=` keys) while a 5th thread loops over `get` / `has` / `emit`. Asserts no exception, no inconsistent state, and the final registry has all 200 entries.

---

## File-by-file change list

| File | Change |
|---|---|
| `src/omniscribe/server.py:117-135` | Mount the three remaining providers after the existing two; remove the explicit `state.ocr_job_queue.stop()` call from the lifespan finally-block (let the provider's disposer handle it) |
| `src/omniscribe/api/plugin/runtime.py:65,89,124-138` | Refactor `is_plugin_context_enabled()` to consult `ConfigStore` first; add a `get_config_store()` typed helper (it already exists in F2 wiring — confirm) |
| `src/omniscribe/api/plugin/providers.py:43-71, 74-102, 105-144, 189-240` | Each provider now returns a coroutine disposer for its async teardown; register the teardown via `ctx.effect(...)` alongside the service unregister |
| `src/omniscribe/api/plugin/context.py:97-103, 127-198, 200-252, 280-327, 492-510, 514-529` | Add `self._lock = threading.RLock()`; wrap the seven mutation methods in `with self._lock:`; make `dispose()` `async def`; update the threading-model docstring |
| `src/omniscribe/api/plugin/effects.py` | `Disposer` type now `Callable[[], None \| Awaitable[None]]`; `EffectScope.dispose()` becomes `async def` and `await`s coroutine disposers |
| `src/omniscribe/api/routers/config.py` | When the ConfigStore is first mounted, seed the `plugin_context_enabled` key from the env-var constant (one-shot) so the store is the single source of truth after the first request |
| `src/omniscribe/api/routers/state.py` | (no change) — the existing `state.config_store` / `state.progress_service` / `state.text_artifacts` etc. are unchanged; the new providers just expose them under the seam Protocol |
| `tests/api/plugin/test_phase6_*.py` (new) | 4 new test files: boot-wiring regression (already added in Phase 2 — confirm), provider-owned disposal ordering, `is_plugin_context_enabled` lookup chain, thread-safe mutation |
| `tests/api/plugin/test_phase2_remediations.py` (or per-F split file) | Update any test that calls `ctx.dispose()` synchronously to `await ctx.dispose()` |
| `AGENTS.md` "Plugin Context Migration Status" | Update the table: 5/5 seams REGISTERED, runtime toggle now ConfigStore-backed |
| `ARCHITECTURE.md` | Add a one-paragraph note on the disposal-ordering contract and the threading model |

---

## Order of execution

1. **F2-deeper first** — wire the three remaining providers. This is the smallest change and gives us the ConfigStore seam that F11 needs.
2. **F11 second** — make `is_plugin_context_enabled` ConfigStore-backed. Requires the ConfigStore provider to be mounted; depends on F2.
3. **F27 third** — add the `threading.RLock` and update `dispose()` to `async def`. Independent of F2/F11 but ripples to every test that calls `ctx.dispose()`.
4. **F13 fourth** — make providers own their teardown. Depends on `ctx.effect()` being usable alongside the new lock and the async `dispose()`.

Each step is a separate commit. Validation gate runs after F27 (because the dispose signature change forces a sweep) and again after F13 (because the new provider shape forces a sweep).

---

## Acceptance criteria

- **Boot wiring** — `server.create_app()` mounts all 5 seams; `get_config_store()` / `get_progress_service()` / `get_text_artifact_store(name="text"\|"metadata"\|"export")` all return non-None live instances
- **Runtime toggle** — setting `ConfigStore["plugin_context_enabled"] = False` at runtime is observed by the next `is_plugin_context_enabled()` call; the env var still seeds the initial value; `OMNISCRIBE_PLUGIN_CONTEXT=false` continues to work
- **Provider disposal** — `await plugin_ctx.dispose()` stops the local queue's worker before removing the service entry; the lifespan finally-block no longer references `state.ocr_job_queue.stop()` directly
- **Thread safety** — 4 threads × 50 `register` calls + 1 reader thread × 1000 ops complete without exception; final registry has all 200 entries
- **Existing tests** — every existing `ctx.dispose()` call site updated to `await ctx.dispose()`; `pytest -m "not slow"` green; `pytest tests/api/plugin/` green
- **Doc update** — `AGENTS.md` "Plugin Context Migration Status" table shows 5/5 REGISTERED with the new toggle + disposal + locking notes

---

## Out of scope (deferred)

- **`/api/config` POST route** — adding a UI form to toggle the flag is a frontend task; this phase only changes the read path
- **`CeleryJobQueue` provider** — the new disposal contract is *for* this future provider, but writing the provider itself is a separate phase
- **Multi-worker config broadcast** — currently the in-memory `ConfigStore` is per-process; the SQLite/Redis backends already broadcast. A test that asserts the toggle is visible across two uvicorn workers belongs in the SQLite/Redis backend phases
- **Move `state.config_store` ownership out of `state.py`** — the new seam just exposes the existing singleton; the singleton itself stays where it is. A full refactor of `state.py` to remove the module-level aliases is a separate cleanup

---

## Risk

**Low–medium.** The biggest risk is the `dispose() → async dispose()` ripple, which touches every test that calls `ctx.dispose()`. Mitigated by:
- The signature change is mechanical (sync → `await`)
- The runtime behavior is unchanged for any disposer that's not a coroutine
- A new test exercises both the sync and async paths explicitly

The boot-wiring change is trivial. The ConfigStore-toggle change has a small risk of regression on the existing env-var workflow, mitigated by the priority order (store wins, env var seeds, no breakage).

No data migration. No backwards-incompatible operator-facing change. No public API removal.

---

## Recommendation

Run as a single Phase 6 PR, with internal commits per the order above so `git bisect` stays useful. The four findings are interrelated and shipping them together is cheaper than four PRs.
