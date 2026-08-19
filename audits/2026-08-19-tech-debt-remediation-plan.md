# Tech-Debt Secondary-Validation Remediation Plan

**Date:** 2026-08-19
**Companion to:** `audits/2026-08-19-secondary-validation-pass.md` (30 findings, 18 detailed)
**Cadence:** Per user preference ("consult me before each phase"), each phase below has an explicit "go" gate. Terse "go" = confirmation.
**Branch state:** `main`, 4 commits ahead of origin, many uncommitted modifications (mid-flight work). Plan accounts for current uncommitted state.

## TL;DR

The 2026-08-17 primary audit + 2026-08-18 residual sweep remediated most CRITICAL/HIGH findings. The secondary pass (today) found 30 new build-up findings + 6 residuals still OPEN. Six phases below, sequenced by **impact × effort ÷ regression risk**, with explicit "go" gates between each. Phase 1 is doc-only + a 5-line CLI fix; recommended as the first "go".

---

## Findings at a glance

### Primary-audit residuals still OPEN (6)

| ID | Sev | Title | One-line fix |
|---|---|---|---|
| D1-08 | P3 | `ReadingOrderProcessor._sort_key` None guard | `bbox = b.bbox or (0,0,0,0)` |
| D2-04 | P2 | RateLimitMiddleware sweep is sync, not amortized | `asyncio.TimerHandle` for sweep |
| D2-06 | P2 | `_PinnedIPTransport` hand-rolled parser | subclass `httpcore.AsyncBaseTransport` |
| D2-12 | P2 | `asyncio.QueueFull` unhandled in SSE push | try/except with drop-oldest |
| D4-04 | P2 | SQLite lock contention untested | add `ThreadPoolExecutor` test |
| D5-02 | P2 | Dockerfile `chown` after COPY inflates image | `COPY --chown=app:app` |

### New build-up the primary audit missed (top 10 of 24)

| ID | Sev | Title |
|---|---|---|
| F1 | P1 | `document_exporters/` is a 100-LOC stub; real exporters live in `core/docx_writer.py` etc. |
| F2 | P1 | `api/plugin/` (1,600 LOC, 14 files) is undocumented in AGENTS.md/ARCHITECTURE.md; 3/5 seams unregistered |
| F3 | P1 | `omniscribe-migrate-lexicon --verify-only` returns exit 2 on a valid empty store |
| F10 | P2 | Dual-write shim swallows `Exception` (masks projection bugs) |
| F12 | P2 | No e2e test that `server.create_app()` wires the plugin context |
| F15 | P2 | `JobHistoryProjection.list()` is O(N log N) per `/api/jobs` GET (no cache) |
| F16 | P2 | `ArtifactStoreProjection.get()` re-folds the entire log per call (no cache) |
| F18 | P2 | CHANGELOG.md not refreshed for 2026-08-17 → 2026-08-19 work |
| F19 | P2 | README.md / DEPLOYMENT.md don't mention `omniscribe-migrate-lexicon` |
| F25 | P2 | `a11y.test.ts` no `axe-core` integration (D4-14 still PARTIAL) |

(Full table in the audit companion; 30 findings total.)

---

## Phases

Each phase ends with a "go" gate. I'll stop, recap, and wait for the next "go".

### Phase 1 — Documentation drift + trivial CLI bug (1 PR, ~half day)

**Why first:** zero code risk, closes 5 findings, surfaces the new infrastructure to operators.

| # | File:Line | Change |
|---|---|---|
| F1 | `ARCHITECTURE.md:61` | Rewrite to "thin Protocol+ABC shim; implementations co-located in `core/docx_writer.py`, `core/docx_tree_writer.py`, `core/html_writer.py`" |
| F2 | `AGENTS.md` (new section after Extension Points) | Add "Plugin context migration status" listing 5 seams + boot-registration state |
| F18 | `CHANGELOG.md` Unreleased | Add 2026-08-17 → 2026-08-19 cluster (plugin context, document_exporters, migrate-lexicon CLI, a11y.test.ts, download.ts, projections) |
| F19 | `README.md` + `DEPLOYMENT.md` | Add `omniscribe-migrate-lexicon` to the install / upgrade / troubleshooting sections |
| F3 | `cli/migrate_lexicon.py:139-145` | Fix exit-code logic: only return 2 on count mismatch; treat empty-but-consistent as exit 0. Add `--strict` flag. |
| F29 | `cli/migrate_lexicon.py:141` | Remove the unreachable `if … and report.skipped: return 0` branch |

**Acceptance:**
- `mypy src` clean
- `ruff check src` clean
- New test: `tests/cli/test_migrate_lexicon_exit_codes.py` covers exit 0 (skip), exit 0 (verified empty), exit 0 (success), exit 1 (error), exit 2 (--strict + mismatch)
- `pytest -m "not slow"` green

**Risk:** trivial

---

### Phase 2 — New-infrastructure hardening (1 PR, 1-2 days)

**Why second:** the new plugin context infrastructure is the highest *operational* risk in the codebase. Close the most fragile seams before more code lands on top of them.

| # | File:Line | Change |
|---|---|---|
| F10 | `api/services/artifacts.py:175-199` | Narrow `except Exception` to `(ServiceNotFoundError, ContextDisposedError)`; let `KeyError`/`AttributeError`/`TypeError` propagate |
| F12 | `tests/api/test_server_boot_wiring.py` (new) | 30-line e2e: `server.create_app()` → assert `get_plugin_context()` is live, `get_job_queue()` is `state.ocr_job_queue`, `get_text_artifact_store()` is None |
| F15 | `api/plugin/projections.py:164-197` | Add `self._list_cache` keyed on log version (monotonic counter); invalidate on every `log.append` |
| F16 | `api/plugin/projections.py:331-354` | Same cache strategy for `get()`; or change API to `list()`-then-filter at call sites |
| F14 | `api/plugin/providers.py:43,74,105,144,183` | Standardize on `<backend_kind>` (local / memory / sqlite / redis); add a docstring in `runtime.py:1-50` codifying the convention |
| F28 | `api/tasks.py` (Celery) | Call `aclose_shared_client()` in worker `worker_shutdown` signal (long-running workers) |

**Acceptance:**
- New test: `test_artifact_dual_write_propagates_programming_bugs` (intentionally raise in projection → confirm `KeyError` reaches caller)
- New test: `test_job_history_projection_caches_until_log_version_increments`
- New test: `test_artifact_store_projection_get_uses_cache`
- New test: `test_server_boot_wiring` (the e2e)
- `pytest -m "not slow"` green; perf smoke: `/api/jobs` GET < 50 ms with 1000 jobs in log

**Risk:** medium — touches the new infra, but tests above catch regressions

---

### Phase 3 — Primary-audit residual close-out (1 PR, 2-3 days)

**Why third:** clean up the items the 2026-08-17 audit flagged but the 2026-08-18 sweep didn't reach. Most are small; D2-06 is moderate.

| # | File:Line | Change |
|---|---|---|
| D2-12 | `api/routers/events.py:71-78` | Drop-oldest on `QueueFull`: `try: queue.get_nowait(); except QueueEmpty: pass` then `queue.put_nowait(frame)`; only catch `QueueFull` |
| D4-04 | `tests/test_state_backend_sqlite.py` (new test) | `test_concurrent_writers_dont_block_under_wal`: 4 threads × 50 puts, assert all complete in < 5 s |
| D5-02 | `Dockerfile:81-88` | Replace `COPY . /app` + `RUN chown -R app:app /app` with `COPY --chown=app:app . /app` |
| D1-08 | `core/processors/reading_order.py:38` | `bbox = b.bbox or (0.0, 0.0, 0.0, 0.0)`; add test for `bbox=None` |
| D2-06 | `api/services/http_fetch.py:65-184` | Subclass `httpcore.AsyncBaseTransport`; override `handle_async_request` to use pinned IP via `asyncio.open_connection`. Defer gzip/chunked to a follow-up if blocking. |
| D2-04 | `api/services/security_middleware.py:729-771` | Move sweep to `asyncio.TimerHandle`; first overflow request does not block |

**Acceptance:**
- All new tests pass
- Existing `pytest` green
- `mypy src` clean
- Docker image size after Phase 3: confirm `docker images omniscribe:latest` shrunk by 500 MB+ (D5-02 win)
- D2-06: a new test exercises a chunked+gzip response from a local stub server

**Risk:** medium — D2-06 is the only non-trivial refactor; D5-02 is in the build chain

---

### Phase 4 — Test debt + a11y + diag folder (1-2 PRs, 1-2 days)

**Why fourth:** close the testing gaps now that the new infra has stabilized.

| # | File:Line | Change |
|---|---|---|
| F24 | `tests/_diag/` → `scripts/diagnostics/` | Move 3 files; delete the `tests/_diag/` folder; drop the `collect_ignore_glob` line from `conftest.py` |
| F25 | `frontend/src/__tests__/a11y.test.ts` + `package.json` | Add `vitest-axe` + `@axe-core/playwright`; wire into `npm test`; replace manual `role=` checks with axe scans on top-level pages |
| F26 | `tests/test_phase2_remediations.py` → 7 files | Split into `test_phase2_F1.1.py`, `test_phase2_F1.2.py`, … by primary-audit finding ID; 1:1 traceability |
| (D4-09) | `tests/test_scripts_smoke.py:40` | Update for LanceDB; drop `chromadb` reference |
| (D4-11) | `.pre-commit-config.yaml` + `test.yml` | `mypy src tests` (extend coverage to tests dir) |
| (D4-12) | `test.yml:119` | Add `--cov-fail-under=80` (or pick a floor) |

**Acceptance:**
- `pytest -m "not slow"` green; `npm test` green
- `npm run build` clean
- `_diag` folder gone; `tests/conftest.py:92-94` no longer has the fragile exclude
- `vitest-axe` runs in `frontend/src/__tests__/a11y.test.ts`; CI fails on axe violations

**Risk:** low (test-only)

---

### Phase 5 — Dep hygiene + operational debt (1 PR, half day)

**Why fifth:** quick wins, low risk, but lower priority than the new-infra hardening.

| # | File:Line | Change |
|---|---|---|
| F17 | `pyproject.toml:34` | Run the surya import test; if `surya.common.s3` no longer triggers the `ModuleNotFoundError`, drop `requests>=2.31`; update AGENTS.md:208 / ARCHITECTURE.md:507,702 |
| F20 | `pyproject.toml:38` | Loosen numpy upper bound: `numpy>=2.0,<2.5.0` (or `numpy>=2.0`); re-run `uv lock` |
| F21 | `frontend/package.json:22` | Align `@types/node` with `test.yml:80` Node 20 → `@types/node ^20.0.0` |
| F22 | `install.sh` | Add Docker / Redis reachability check (mirror `install.ps1:131`) |
| F23 | `start_app.vbs:18-44` | Add `start_app.log` rotation: 10 MB max, keep 3 backups, rename `start_app.log.1` on size overflow |
| F30 | `start_app.vbs` | Adaptive backoff: start at 100 ms, double on each miss, cap at 2 s |

**Acceptance:**
- `uv lock` resolves cleanly
- `npm run build` clean
- `install.sh` exits 0 on a Docker-less box with a clear message
- `start_app.log` rotation tested manually

**Risk:** low

---

### Phase 6 — Plugin context migration completion (deferred to a separate plan)

**Why deferred:** bigger refactor with backwards-compat implications; deserves its own design doc.

| # | File:Line | Change |
|---|---|---|
| F11 | `api/plugin/runtime.py:50-72` | Move `PLUGIN_CONTEXT_ENABLED` from module constant to `ConfigStore`-backed runtime toggle |
| F13 | `api/plugin/providers.py:43-71` | Provider-owned disposal effect; document ordering contract |
| F27 | `api/plugin/context.py:35-44` | Add `asyncio.Lock` around `mount`/`unmount`; document the threading model |
| F2 (deeper) | `server.py:117-135` | Register `ConfigStore`, `ProgressService`, `TextArtifactStore` providers OR delete the unregistered seams |

**Why deferred:** these touch the new infra at its foundation. Worth a design doc + a "single-provider-wired-at-a-time" migration plan, not bundled into the secondary validation pass.

---

## Recommended "go" order

1. **Phase 1** — doc + 5-line CLI fix. Zero code risk. Closes 5 findings.
2. **Phase 2** — new-infra hardening. Closes 6 findings, includes the boot-wiring e2e that protects everything else.
3. **Phase 3** — primary-audit residuals. Closes 6 OPEN items.
4. **Phase 4** — test debt. Closes 4-6 findings (Phase 4 + primary D4-09/11/12).
5. **Phase 5** — dep hygiene + ops. Closes 6 findings.
6. **Phase 6** — separate plan.

**Total:** ~6-9 days of work, 4-5 PRs. All in `main`, no new branches needed (you said this is personal, no shipping pressure).

---

## Phase 1 — ready to execute

If "go", I will:
1. Make the doc changes (5 files: ARCHITECTURE.md, AGENTS.md, CHANGELOG.md, README.md, DEPLOYMENT.md)
2. Fix the CLI exit-code logic (1 file: `cli/migrate_lexicon.py`)
3. Remove the dead branch (same file)
4. Add the new test file (`tests/cli/test_migrate_lexicon_exit_codes.py`)
5. Run the fast gate (`ruff check src tests`, `mypy src`, `pytest -m "not slow"`)
6. Commit on `main` with a single `docs+fix(audit-secondary-d1)` message
7. Recap and ask for "go" on Phase 2

Wait for your call.
