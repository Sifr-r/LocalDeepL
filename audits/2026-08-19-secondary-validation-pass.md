# OmniScribe Secondary Validation Pass — Tech-Debt Build-Up & Residual Findings

**Date:** 2026-08-19
**Scope:** Tech debt the 2026-08-17 (5-domain) + 2026-08-18 (residual sweep) audits likely missed. **Read-only** — no code was modified.
**Method:** Targeted read of all remediation-introduced surface (plugin context, document_exporters, migrate-lexicon CLI, new tests, a11y/download utils, state backends, install scripts), residual verification of every CRITICAL/HIGH finding in the primary audit, cross-cutting integration checks, operational-debt walk.
**Companion document:** `audits/2026-08-19-tech-debt-remediation-plan.md` (sequenced phases).

---

## Executive Summary

1. **The new `api/plugin/` module (1,600+ LOC, 14 files) ships without a single line of user-facing documentation** — AGENTS.md and ARCHITECTURE.md both miss it. Five Protocol-based seams are defined; only 2 of 5 are actually registered at boot. Two parallel "look-up-by-Protocol vs import-singleton" code paths exist side-by-side with no migration timeline.
2. **`document_exporters/` is a 100-line stub package** that ARCHITECTURE.md describes as a "Pluggable document exporter abstraction layer". All three real exporters (DOCX, tree-DOCX, HTML) live outside the package in `core/docx_writer.py`, `core/docx_tree_writer.py`, `core/html_writer.py`. ARCHITECTURE.md:61 overstates the shape.
3. **The `omniscribe-migrate-lexicon` CLI has a real exit-code bug** (line 144 of `cli/migrate_lexicon.py`): `--verify-only` returns exit code 2 for a valid empty `lexicon.lance` (no glossaries migrated, not skipped). Operators scripting around the CLI will see false-positive failures.
4. **Residual of D2-04, D2-06, D2-12, D4-04, D5-02, D1-08 all OPEN** — primary-audit items the remediation sweep either bypassed or only partially addressed. Three of these (D2-12, D4-04, D1-08) have had zero remediation commits in the diff.
5. **Significant test debt on the new remediation tests themselves** — the dual-write shim catches all exceptions silently, `test_phase2_remediations.py` packs 7 fixes into one file (regression traceability loss), and `a11y.test.ts` does manual `role=`/`aria-` checks but no `axe-core` integration (the audit's D4-14/F4.9 is still PARTIAL at best).

---

## Findings table (sorted by severity)

| # | Title | Sev | Domain | State |
|---|-------|-----|--------|-------|
| 1 | `document_exporters/` package is a 100-LOC stub — implementations live outside | P1 | Core Pipeline | NEW BUILD-UP |
| 2 | `api/plugin/` ships undocumented and 3 of 5 seams unregistered at boot | P1 | API | NEW BUILD-UP |
| 3 | `omniscribe-migrate-lexicon` `--verify-only` returns exit 2 on empty valid store | P1 | DevOps | NEW BUILD-UP |
| 4 | D2-04 `RateLimitMiddleware` sweep is unbounded-amortized, not amortized | P2 | API/Security | PARTIAL |
| 5 | D2-06 `_PinnedIPTransport` still hand-rolled — no chunked/gzip/HTTP/2 | P2 | API/Security | PARTIAL |
| 6 | D2-12 `asyncio.QueueFull` unhandled in SSE push callback | P2 | API | OPEN (unaddressed) |
| 7 | D4-04 SQLiteStateBackend concurrent-writer test never added | P2 | Testing | OPEN |
| 8 | D1-08 ReadingOrderProcessor._sort_key still unpacks `block.bbox` w/o None guard | P3 | Core | OPEN |
| 9 | D5-02 Dockerfile `chown -R app:app` after COPY still inflates image ~1.5-2 GB | P2 | DevOps | OPEN |
| 10 | Dual-write shim swallows `Exception` — masks bugs in projection code | P2 | API/Cross | NEW BUILD-UP |
| 11 | `PLUGIN_CONTEXT_ENABLED` env var read at import time; no runtime toggle | P2 | API | NEW BUILD-UP |
| 12 | No e2e test that `server.create_app()` actually wires the plugin context | P2 | Testing | NEW BUILD-UP |
| 13 | `plugin_ctx.dispose()` ordering: queue's task lives longer than the context | P3 | API | NEW BUILD-UP |
| 14 | Inconsistent service-name conventions (JobQueue="local" vs TextArtifactStore="text") | P3 | API | NEW BUILD-UP |
| 15 | `JobHistoryProjection.list()` is O(N log N) on every `/api/jobs` GET | P2 | Performance | NEW BUILD-UP |
| 16 | `ArtifactStoreProjection.get()` re-folds the entire log per artifact | P2 | Performance | NEW BUILD-UP |
| 17 | `requests>=2.31` workaround is likely dead weight (surya 0.22.x) | P3 | Dependency | OPEN |
| 18 | `CHANGELOG.md` not refreshed for 2026-08-17 → 2026-08-19 work | P2 | Documentation | NEW BUILD-UP |
| 19 | `README.md` / `DEPLOYMENT.md` don't mention the new `migrate-lexicon` CLI | P2 | Documentation | NEW BUILD-UP |
| 20 | `pyproject.toml:38` `numpy>=2.4.6,<2.5.0` — pre-release upper bound risk | P3 | Dependency | NEW BUILD-UP |
| 21 | `frontend/package.json:22` `@types/node ^26.2.0` mismatched with Node 20 floor | P3 | Frontend/Dep | NEW BUILD-UP |
| 22 | `install.sh` doesn't check Docker / parity gap with `install.ps1` | P3 | DevOps | NEW BUILD-UP |
| 23 | `start_app.vbs` `start_app.log` grows unbounded, no rotation | P3 | DevOps | NEW BUILD-UP |
| 24 | `tests/_diag/` still on disk; fragile exclusion via conftest only | P3 | Testing | OPEN |
| 25 | `a11y.test.ts` does no `axe-core`/`vitest-axe` integration (D4-14 still PARTIAL) | P2 | Testing/A11y | PARTIAL |
| 26 | `test_phase2_remediations.py` packs 7 fixes in one file (regression traceability) | P3 | Testing | NEW BUILD-UP |
| 27 | `PluginContext` mutation is not thread-safe — docstring acknowledges this | P3 | API | NEW BUILD-UP |
| 28 | `multi_format_client.py` shared httpx client never closed in Celery workers | P3 | Performance | NEW BUILD-UP |
| 29 | Dead-code branch in `migrate_lexicon.py` exit-code logic (line 141) | P4 | DevOps | NEW BUILD-UP |
| 30 | `start_app.vbs` polls at 100 ms with no adaptive backoff | P4 | Performance | OPEN |

---

## Per-finding detail (top 18; remaining 12 in `Recommended remediation sequencing`)

### 1. `document_exporters/` is a stub package — implementations live elsewhere [P1, Core Pipeline, NEW BUILD-UP]

`src/omniscribe/core/document_exporters/` contains exactly one file: `base_exporter.py` (a 100-line Protocol + ABC). The three actual implementations are:
- `core/docx_writer.py:23` `DocxMarkdownExporter(BaseDocumentExporter)`
- `core/docx_tree_writer.py:25` `DocxTreeExporter(BaseDocumentExporter)`
- `core/html_writer.py:34` `HtmlExporter(BaseDocumentExporter)`

`ARCHITECTURE.md:61` claims this directory is a "Pluggable document exporter abstraction layer for converting DocumentResult and DocumentTree to target formats." That description is misleading — the package is a 100-LOC shim. Anyone told to "add a Markdown exporter" would naturally add `document_exporters/markdown.py`, which doesn't fit the actual seam location pattern.

**Why it was missed.** The 2026-08-17 D1 sweep categorizes this as "structural" and would only flag a missing file; the audit doesn't appear to have checked that the abstraction *is the abstraction*.

**Evidence chain:** `src/omniscribe/core/document_exporters/__init__.py:9-13`; `src/omniscribe/core/document_exporters/base_exporter.py:1-80`; `src/omniscribe/core/docx_writer.py:14,23`; `src/omniscribe/core/docx_tree_writer.py:19,25`; `src/omniscribe/core/html_writer.py:23,34`; `ARCHITECTURE.md:61`.

**Suggested remediation.** Either move the three exporters into `core/document_exporters/{docx,tree_docx,html}.py` so the package matches its name, or rewrite `ARCHITECTURE.md:61` to reflect that the package is a thin Protocol+ABC and the implementations are co-located with the existing top-level `core/docx_writer.py` etc. Pick one and document the choice.

---

### 2. `api/plugin/` ships undocumented; only 2 of 5 seams registered at boot [P1, API, NEW BUILD-UP]

`src/omniscribe/api/plugin/` is 14 files / ~1,600 LOC introducing a Cordis-inspired "everything is a plugin" container with 5 Protocol-based seams (`JobQueue`, `ProgressService`, `ConfigStore`, `TextArtifactStore`, `SessionLog` in `seams.py:50-198`). Boot wiring in `server.py:117-135` registers only:
- `JobQueue` ("local")
- `SessionLog` ("memory")
- an audit recorder

So `ConfigStore`, `ProgressService`, and `TextArtifactStore` seams are defined, advertised in `__all__`, and re-exported through `runtime.py:get_*_service()` helpers — but never have a provider registered. A consumer calling `get_text_artifact_store()` always gets `None` and silently falls through to the legacy singleton.

Meanwhile, `AGENTS.md:149-160` and `ARCHITECTURE.md` do not mention the plugin package at all. The migration-window semantics (look up by Protocol, fall back to singleton) are only documented in `runtime.py:8-13` and the seams docstrings.

**Why it was missed.** The audit's "Cross-cutting" lens didn't run — the new code lives in a directory that no audit section profiles. A migration-status page in AGENTS.md would have surfaced this immediately.

**Evidence chain:** `src/omniscribe/api/plugin/__init__.py:24-92`; `src/omniscribe/api/plugin/seams.py:50-198`; `src/omniscribe/api/plugin/runtime.py:133-195`; `src/omniscribe/server.py:117-135`; `src/omniscribe/api/routers/state.py:1-77` (still primary access path); absence in `AGENTS.md` (grep returns 0 hits for `api/plugin|PluginContext|seam|dual-write`).

**Suggested remediation.** Either (a) add a "Plugin context migration status" section to `AGENTS.md` listing the 5 seams + their current boot-registration state + a target date for the legacy singleton cutover; or (b) delete the 3 unregistered seams until they're actually wired. Option (a) is correct — the new infra is solid; only the documentation is missing.

---

### 3. `omniscribe-migrate-lexicon --verify-only` returns exit 2 on empty valid store [P1, DevOps, NEW BUILD-UP]

`src/omniscribe/cli/migrate_lexicon.py:139-145`:

```python
if report.error: return 1
if report.verified and report.error is None and report.skipped: return 0
if report.verified and report.glossaries_migrated == 0 and not report.skipped: return 2
return 0
```

The third branch returns exit 2 (intended as "verify-only detected a problem") when `glossaries_migrated == 0`. But a brand-new install that has run a no-op migration, or one where the user has explicitly deleted every glossary, has `lexicon.lance` with 0 glossaries. That's a valid state, not a problem. An operator scripting `if omniscribe-migrate-lexicon --verify-only; then …` will get a false-positive failure.

**Why it was missed.** The `--verify-only` happy path was never tested in a fixture (only the `skip_reason="no lexicon.lance to verify"` case returns 0). The bug requires an actually-empty `lexicon.lance` to trigger.

**Evidence chain:** `src/omniscribe/cli/migrate_lexicon.py:139-145`; `src/omniscribe/core/lexicon/migration.py:466-500` (`_verify_migration`); `tests/api/plugin/test_dual_write_shim.py` (no `--verify-only` exit-code test).

**Suggested remediation.** Treat `glossaries_migrated == 0` as exit 0 when `len(lexicon.lance)` is consistent with the backup manifest. Concretely, only return exit 2 if there's a count mismatch between the live store and the manifest. A second-best quick fix: only return 2 if the user passes `--strict` explicitly.

---

### 4. D2-04 `RateLimitMiddleware` sweep is O(N) on overflow, not amortized [P2, API/Security, PARTIAL]

Audit fix in `security_middleware.py:756-770` adds `MAX_TRACKED_IPS` cap. The cleanup is fine on the steady-state path, but the sweeper at line 758-770 runs *inside the same request that triggers the overflow*. For 10,001 unique IPs in 60 s, request 10,001 takes the full O(N) sweep; the operator's p99 latency spikes. A real attacker rotating IPs can pin p99 at the sweep time.

**Why it was missed.** The primary audit D2-04 only flagged the "unbounded growth" half; it didn't profile the "sweep amortized vs synchronous" question.

**Evidence chain:** `src/omniscribe/api/services/security_middleware.py:729-771`; `MAX_TRACKED_IPS` constant.

**Suggested remediation.** Move the sweep to a background task with `asyncio.create_task` or use a periodic `asyncio.TimerHandle`. The first request past the cap can take a small hit; subsequent ones are bounded by the cap.

---

### 5. D2-06 `_PinnedIPTransport` still hand-rolled — no chunked/gzip/HTTP/2 [P2, API/Security, PARTIAL]

`src/omniscribe/api/services/http_fetch.py:49-184` is a hand-rolled HTTP/1.1 parser. It does not handle:
- `Transfer-Encoding: chunked` (line 130 reads raw bytes and joins)
- `Content-Encoding: gzip` (line 131 returns the raw compressed bytes; downstream parsers crash)
- HTTP/2 (not implemented; forced `HTTP/1.1` at line 97)
- Multiple responses on a keep-alive socket (mitigated by `Connection: close` at line 102, but loses the perf win)

The audit recommended "use `httpx`/`httpcore` streaming transport with custom socket resolver." The actual fix is keeping the hand-rolled parser and wrapping it in an `httpx.AsyncBaseTransport`. A CDN like jsdelivr that returns chunked gzipped text for a glossary import will deliver the raw `b"1f8b…"` payload; downstream consumers will fail with a JSON parse error.

**Why it was missed.** A glossary URL fixture that exercises the chunked/gzip path was not in the test suite.

**Evidence chain:** `src/omniscribe/api/services/http_fetch.py:65-184`; `tests/api/test_glossary_imports.py` (no chunked/gzip fixture).

**Suggested remediation.** Replace `_PinnedIPTransport._parse_response` with a thin `httpx.Response` builder over the same raw bytes, but go one layer deeper: subclass `httpcore.AsyncBaseTransport` and override `handle_async_request` to use the pinned IP via `asyncio.open_connection`, then let `httpx` do parsing. The hand-rolled parser is a maintenance bomb.

---

### 6. D2-12 `asyncio.QueueFull` unhandled in SSE push [P2, API, OPEN]

`src/omniscribe/api/routers/events.py:76-78`:
```python
def push(frame):
    loop.call_soon_threadsafe(queue.put_nowait, frame)
```

`_FRAME_QUEUE_MAXSIZE` is bounded (per the docstring at line 64-67, with `broker.unsubscribe` cleanup). When a slow SSE consumer falls behind, `put_nowait` raises `QueueFull` inside the threadsafe callback. The exception has no handler; it propagates into uvicorn's event loop and is silently swallowed. The audit's recommended "drop oldest frame on queue full" was not done.

**Why it was missed.** A slow-consumer test fixture (a TestClient that doesn't read the stream) was never added.

**Evidence chain:** `src/omniscribe/api/routers/events.py:71-78, 83-110`.

**Suggested remediation.** Wrap the `put_nowait` in a try/except that does `try: queue.get_nowait(); queue.put_nowait(frame); except (QueueFull, QueueEmpty): pass` — drop-oldest semantics. Or grow the queue (worse; unbounded memory).

---

### 7. D4-04 SQLite lock contention — never tested [P2, Testing, OPEN]

`src/omniscribe/api/services/state_backend_sqlite.py:124-136` opens a new connection per call with `WAL` + 30 s timeout — the production fix is correct. But `tests/test_state_backend_sqlite.py` (14 tests) never spawns two concurrent writers. The `timeout=30.0` value has no test that proves it works; a regression to the default 5 s timeout (or removing `WAL` in a future refactor) would not be caught.

**Why it was missed.** D4 was filed as MEDIUM in the primary audit; the M-4 commit covered most of D4 but the SQLite concurrency test was not in the diff.

**Evidence chain:** `src/omniscribe/api/services/state_backend_sqlite.py:124-136`; `tests/test_state_backend_sqlite.py` (no `concurrent`/`ThreadPoolExecutor`/`threading` matches).

**Suggested remediation.** Add a `test_concurrent_writers_dont_block_under_wal` test using `concurrent.futures.ThreadPoolExecutor(max_workers=4)` and 50 put() calls. Assert all complete within 5 s.

---

### 8. D1-08 `ReadingOrderProcessor._sort_key` still unpacks `block.bbox` w/o None guard [P3, Core, OPEN]

`src/omniscribe/core/processors/reading_order.py:38`. A `Block` with `bbox is None` would raise `TypeError: cannot unpack non-iterable NoneType object`. The `MAY_DELETE` contract processors upstream can produce empty boxes; the sort key path is unprotected. A one-line guard would close it.

**Why it was missed.** Filed as LOW; remediation sweep prioritized MEDIUM and above.

**Evidence chain:** `src/omniscribe/core/processors/reading_order.py:38`; `audits/2026-08-17-domain-1-core-pipeline.md:8` (D1-08).

**Suggested remediation.** Change `_sort_key` to: `def _sort_key(b: Block) -> tuple: bbox = b.bbox or (0.0, 0.0, 0.0, 0.0); return bbox[1], bbox[0], bbox[3], bbox[2]`. Add a test for the `bbox=None` case.

---

### 9. D5-02 `Dockerfile` `RUN chown -R app:app /app` after COPY still inflates image [P2, DevOps, OPEN]

`Dockerfile:81-88`. The `chown` after `COPY . /app` creates an additional OverlayFS layer because the .venv copy has uid=gid=0; the recursive chown creates a new layer. The audit's recommended `COPY --chown=app:app` is a one-line change that shaves ~500 MB-1 GB off the runtime image. The D5 sweep commit (`M-5`) was on the list of pending phases in the 2026-08-17 audit; it does not appear to have landed.

**Why it was missed.** M-5 was the lowest-priority cluster; the audit sweep prioritized D1/D2/D3.

**Evidence chain:** `Dockerfile:81-88`; `audits/2026-08-18-domain-5-devops-config.md` (M-5 not in fixed list).

**Suggested remediation.** `COPY --chown=app:app . /app` instead of `COPY . /app` + `RUN chown -R`. One-line diff, large savings.

---

### 10. Dual-write shim swallows ALL exceptions, not just expected ones [P2, API/Cross, NEW BUILD-UP]

`src/omniscribe/api/services/artifacts.py:175-199`:
```python
try:
    ...
    ctx.emit("artifact.created", **payload)
except Exception:
    logger.exception(...)
```

The `except Exception` catches programming bugs in `ArtifactStoreProjection._apply` (e.g. a future refactor that crashes on `payload.get("token")`) just as gracefully as a missing plugin context. A bug in the projection code would silently drop every artifact creation event, leaving the user with an unexplained empty "recent artifacts" view, and no error trail beyond the exception log.

**Why it was missed.** The dual-write shim's `try/except` is the right pattern for "the primary write must never be blocked by a best-effort emit," but the failure mode was not differentiated.

**Evidence chain:** `src/omniscribe/api/services/artifacts.py:175-199`; `src/omniscribe/api/plugin/projections.py:373-399` (no tests catch a projection bug; `test_put_without_plugin_context_does_not_raise` only covers the `ctx is None` case).

**Suggested remediation.** Narrow the catch: `except (ServiceNotFoundError, ContextDisposedError) as exc: ...`. Let `KeyError`/`AttributeError`/`TypeError` propagate so a programming bug is caught at the call site.

---

### 11. `PLUGIN_CONTEXT_ENABLED` env var read at import time; no runtime toggle [P2, API, NEW BUILD-UP]

`src/omniscribe/api/plugin/runtime.py:65`: `PLUGIN_CONTEXT_ENABLED: bool = is_plugin_context_enabled()`. The flag is fixed at import. `set_plugin_context_enabled` is documented as "tests only." An operator who wants to enable the new path at runtime (e.g. via `/api/config` POST) has no API; they have to restart the server with the env var.

**Why it was missed.** Migration windows are usually short — the audit didn't anticipate the "long migration window" case where operators want to toggle the path per environment.

**Evidence chain:** `src/omniscribe/api/plugin/runtime.py:50-72`; `src/omniscribe/api/services/config_store.py` (ConfigStore is the natural place for this knob but is not wired).

**Suggested remediation.** Add a `plugin_context_enabled: bool` field to `ConfigStore` (read by the `OMNISCRIBE_PLUGIN_CONTEXT` env seed), and re-evaluate `PLUGIN_CONTEXT_ENABLED` on every `ConfigStore.get()` call. Or accept the import-time-only constraint and document it in AGENTS.md.

---

### 12. No e2e test that `server.create_app()` actually wires the plugin context [P2, Testing, NEW BUILD-UP]

`tests/api/plugin/test_phase5_seams.py` and `test_phase7_lookup_helpers.py` test the protocol + the lookup helpers, but no test instantiates `server.create_app()` and asserts:
- `get_plugin_context()` returns a live context
- `get_job_queue()` returns `state.ocr_job_queue` (the same instance, not a copy)
- `get_text_artifact_store()` returns None (the "registered" smoke test for an un-registered seam)

A boot-time wiring bug (e.g. someone deletes `plugin_ctx.mount(local_job_queue_provider(...))`) would be caught only when an operator hits a 404 on a job in production.

**Why it was missed.** The new tests were added at the unit level; the integration test (boot the app, look up the service) was missed.

**Evidence chain:** `src/omniscribe/server.py:117-135`; `tests/api/plugin/` (12 files; no `test_create_app_wires_plugin_context.py` or equivalent).

**Suggested remediation.** Add a 30-line test that calls `server.create_app()` and asserts the four lookups above. Place in `tests/api/test_server_boot_wiring.py`.

---

### 13. `plugin_ctx.dispose()` ordering vs queue lifecycle [P3, API, NEW BUILD-UP]

`src/omniscribe/server.py:149-161`:
```python
finally:
    await _stop_artifact_cleanup(cleanup_task)
    await state.ocr_job_queue.stop()
    ...
    set_plugin_context(None)
    plugin_ctx.dispose()
```

The `local_job_queue_provider(queue=state.ocr_job_queue)` registers the SAME instance under the seam. When the context disposes, it removes the registry entry but the queue instance continues to live (it's owned by `state.ocr_job_queue`). Then `state.ocr_job_queue.stop()` was already called above. The order is fine for the local queue. But for a future `CeleryJobQueue` provider that spawns its own worker task, the provider's disposer would be called *after* the queue's `stop()` (because the lifespan finally-block runs in reverse). This is a foot-gun for the next person to add a Celery provider.

**Why it was missed.** The current local-queue wiring is robust; the future-Celery case wasn't profiled.

**Evidence chain:** `src/omniscribe/server.py:149-161`; `src/omniscribe/api/plugin/providers.py:43-71`; `src/omniscribe/api/services/ocr_jobs.py` (the actual queue).

**Suggested remediation.** Document the disposal order in `providers.py` or, better, have each provider register its own `effect` with the context for clean teardown.

---

### 14. Inconsistent service-name conventions [P3, API, NEW BUILD-UP]

- `JobQueue` registered as `"local"` (`providers.py:46`)
- `SessionLog` as `"memory"` (`providers.py:78`)
- `ConfigStore` as `"default"` (`providers.py:148`)
- `TextArtifactStore` as `"default"` AND as `"text"/"metadata"/"export"` for the three concrete stores (`providers.py:186`)

A future diagnostic that lists `(definition, name)` pairs will return a confusing mix. Pick one convention: either `default` for the in-process canonical, or `<backend_kind>` (local/memory/sqlite/redis). The runtime helpers in `runtime.py:133-195` use the same mixed convention.

**Why it was missed.** A documentation drift, not a code bug.

**Evidence chain:** `src/omniscribe/api/plugin/providers.py:43,74,105,144,183`; `src/omniscribe/api/plugin/runtime.py:133-195`.

**Suggested remediation.** Standardize on one convention. Document the choice in `runtime.py:1-50`.

---

### 15. `JobHistoryProjection.list()` is O(N log N) on every `/api/jobs` GET [P2, Performance, NEW BUILD-UP]

`src/omniscribe/api/plugin/projections.py:164-197` calls `_fold_all()` (which walks the entire session log for the 4 OCR job kinds), then sorts by `__sort_key + __position`, then returns the capped slice. Every call to `/api/jobs` (and any other consumer of `JobHistoryProjection.list()`) re-walks and re-sorts. No cache. With 1000 jobs × 5 events per job = 5000 log events, a single GET does 5000 log reads + 1000 dict merges + 1000 sorts.

The legacy `JobHistory` was a `deque(maxlen=1000)` — appends were O(1), reads were O(N) but N=1000 and a single slice reversal. The new projection is O(N log N) with N growing with the log.

**Why it was missed.** No performance regression test exists for the projection.

**Evidence chain:** `src/omniscribe/api/plugin/projections.py:164-197, 199-222`; `src/omniscribe/api/routers/jobs.py` (consumer; the GET hits `list()`).

**Suggested remediation.** Cache the most recent list result keyed on log version (an incrementing counter appended on every log write). Invalidate on the next emit.

---

### 16. `ArtifactStoreProjection.get()` re-folds the entire log per artifact [P2, Performance, NEW BUILD-UP]

`src/omniscribe/api/plugin/projections.py:343-354`:
```python
def get(self, artifact_id):
    rec = self._fold_all().get(artifact_id)  # ← full log walk
```

A UI listing 50 artifacts in a sidebar (50 × `get()` calls) does 50 full log walks. The `list()` method shares the same `_fold_all` — it would be one walk for the whole list, but `get()` does it per call.

**Why it was missed.** The projection's API surface was designed without a "lookup by id" performance contract; the legacy `TextArtifactStore.get` was O(1) (dict lookup).

**Evidence chain:** `src/omniscribe/api/plugin/projections.py:331-354, 356-371`.

**Suggested remediation.** Add an instance-level cache: `self._cache: dict[str, dict] | None = None`, invalidated on `log.append`. Or change the API to `list()`-then-filter at the call site.

---

### 17. `requests>=2.31` workaround is likely dead weight [P3, Dependency, OPEN]

`pyproject.toml:34` and `AGENTS.md:208` both note that `surya-ocr 0.17.x` imports `requests` in `surya/common/s3.py` without declaring it. Current pin is `surya-ocr>=0.22.1` — five minor versions later. The audit should have re-verified whether surya still has the issue. A `uv pip show surya-ocr` / `python -c "import surya.common.s3"` check would settle it in 10 seconds.

**Why it was missed.** The M-1 cluster (Domain 1) had many other priorities; this is LOW-impact.

**Evidence chain:** `pyproject.toml:28,34`; `AGENTS.md:208`; `ARCHITECTURE.md:507,702` (the "follow-up" note).

**Suggested remediation.** Run the surya import test; if `surya.common.s3` no longer triggers the `ModuleNotFoundError`, drop the `requests>=2.31` line and update AGENTS.md/ARCHITECTURE.md. If it still does, re-evaluate the pin and check whether surya ships its own.

---

### 18. `CHANGELOG.md` not refreshed for 2026-08-17 → 2026-08-19 work [P2, Documentation, NEW BUILD-UP]

`CHANGELOG.md` last entry is the `Unreleased` section. The plugin context, document_exporters package, migrate-lexicon CLI, a11y.test.ts, download.ts, dual-write shim, JobHistory/ArtifactStore projections, and `omniscribe-migrate-lexicon` console script all shipped in the 2026-08-17 → 2026-08-19 window. None are in CHANGELOG. The `git log` would show the commits; the release notes would not.

**Why it was missed.** CHANGELOG maintenance is conventionally a release-time task, but the audit flagged AGENTS.md/ARCHITECTURE.md drift specifically.

**Evidence chain:** `CHANGELOG.md:7-200` (last `## [Unreleased]` entries date to 2026-08-15); absence of plugin context / migrate-lexicon / document_exporters in the changelog; the corresponding source files exist.

**Suggested remediation.** Add a 2026-08-17 → 2026-08-19 cluster to `## [Unreleased]` covering the 8 new files / 2 new test files / 1 new console script.

---

## Findings 19–30 (one-line each, for the table-only reader)

19. **`README.md` and `DEPLOYMENT.md` don't mention `omniscribe-migrate-lexicon`** — operators who don't read CHANGELOG won't know the CLI exists. The CLI is the only retry path for a failed auto-migration. P2, Documentation, NEW BUILD-UP.
20. **`pyproject.toml:38` `numpy>=2.4.6,<2.5.0`** — pre-release upper bound. The `opencv-python-headless` dep in the `preprocessing` extra has its own numpy tree; the resolver may fail. P3, Dependency, NEW BUILD-UP.
21. **`frontend/package.json:22` `@types/node ^26.2.0`** — pinned to Node 26 line, but `test.yml:80` uses `node-version: 20`. Mismatch. P3, Frontend/Dep, NEW BUILD-UP.
22. **`install.sh` has no Docker check** (unlike `install.ps1:131`). Linux users following the install script get no hint about Docker / Redis. P3, DevOps, NEW BUILD-UP.
23. **`start_app.vbs` `start_app.log` opens with `ForAppending=True` (line 21)** — grows unbounded across re-boots. No rotation, no max-size cap. P3, DevOps, NEW BUILD-UP.
24. **`tests/_diag/` (3 files) still on disk** — `conftest.py:92-94` excludes via `collect_ignore_glob`. A new contributor "fixing" the conftest removes the ignore line and breaks fast tier. Should be moved to `scripts/diagnostics/`. P3, Testing, OPEN.
25. **`a11y.test.ts` does no `axe-core` integration** — only manual `role=`/`aria-` checks. Audit's D4-14/F4.9 ("Frontend lacks automated accessibility checks in CI") is PARTIAL at best. P2, Testing/A11y, PARTIAL.
26. **`test_phase2_remediations.py` packs 7 fixes in one file** (191 lines). A regression in one fix kills the test signal for the others. P3, Testing, NEW BUILD-UP.
27. **`PluginContext` mutation is not thread-safe** — `context.py:35-44` docstring acknowledges this. A future bug will manifest as silent test failures. P3, API, NEW BUILD-UP.
28. **`multi_format_client.py` shared httpx client** — `aclose_shared_client` is called in `server.py:154-156` lifespan, but a Celery worker never calls it. A long-running worker holds a stale httpx client across event-loop boundaries. P3, Performance, NEW BUILD-UP.
29. **Dead-code branch in `migrate_lexicon.py:141`** — `if report.verified and report.error is None and report.skipped: return 0` is unreachable (line 144 only fires when `not report.skipped`). P4, DevOps, NEW BUILD-UP.
30. **`start_app.vbs` polls at 100 ms** (`POLL_INTERVAL_MS = 100`, line 19) with no adaptive backoff. On a slow disk, 3-4 commands × 100 ms × up to 30 s = significant wakeup load. P4, Performance, OPEN.

---

## Evidence index (file:line)

(All citations are 2026-08-19 current code state on `main`.)

- `src/omniscribe/core/document_exporters/__init__.py:9-13` — stub package
- `src/omniscribe/core/document_exporters/base_exporter.py:1-80` — sole file
- `src/omniscribe/api/plugin/__init__.py:24-92` — 14-file package
- `src/omniscribe/api/plugin/seams.py:50-198` — 5 Protocol seams
- `src/omniscribe/api/plugin/runtime.py:50-195` — env-var flag, lookup helpers
- `src/omniscribe/api/plugin/providers.py:43-234` — only 2 of 5 actually registerable
- `src/omniscribe/api/plugin/projections.py:121-399` — perf issue + dual-write dependency
- `src/omniscribe/server.py:117-161` — boot wiring, dispose ordering
- `src/omniscribe/cli/migrate_lexicon.py:139-145` — exit-code bug
- `src/omniscribe/core/lexicon/migration.py:466-500` — verify-only happy path
- `src/omniscribe/api/services/security_middleware.py:280-340, 729-771` — D2-01 + D2-04 partial
- `src/omniscribe/api/services/http_fetch.py:65-184` — D2-06 hand-rolled parser
- `src/omniscribe/api/routers/events.py:71-110` — D2-12 unhandled QueueFull
- `src/omniscribe/api/services/state_backend_sqlite.py:124-340` — D4-04 untested
- `src/omniscribe/api/services/state_backend_redis.py:43-187` — D2-10 partial
- `src/omniscribe/api/services/artifacts.py:175-199` — dual-write shim exception swallow
- `src/omniscribe/core/grounded/prompted.py:446-471` — D1-03 fixed (cancels in `finally`)
- `src/omniscribe/core/pdf/embedder.py:530-558` — D1-07 fixed (separate `new_doc`)
- `src/omniscribe/core/processors/reading_order.py:38` — D1-08 still open
- `Dockerfile:81-88` — D5-02 still open
- `pyproject.toml:28,34,38,44-82,123-125` — dependency / script surface
- `frontend/package.json:22,34` — Node/Vite pin drift
- `tests/conftest.py:92-94` — `_diag/` exclusion
- `tests/test_phase2_remediations.py:1-191` — 7 fixes in one file
- `tests/test_distributed_ocr_tasks.py:1-400` — Celery task unit tests
- `tests/api/plugin/` — 12 unit-test files; no boot-wiring e2e
- `tests/test_state_backend_sqlite.py` — no concurrent-writer test
- `frontend/src/__tests__/a11y.test.ts:1-166` — no axe-core integration
- `frontend/src/lib/utils/download.ts:30-44` — revokeDelay contract
- `frontend/src/lib/utils/__tests__/download.test.ts:1-69` — partial coverage
- `install.sh:30-156` — no Docker check
- `install.ps1:1-183` — Docker check at line 131
- `start_app.vbs:18-44` — log unbounded, poll rate
- `AGENTS.md:88,149-160,204-210` — known tech debt section
- `ARCHITECTURE.md:61,389-427,770` — table extraction historical reference; `document_exporters` overstatement
- `CHANGELOG.md:1-200` — last entry 2026-08-15

---

**END OF REPORT**
