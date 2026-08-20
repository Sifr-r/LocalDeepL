# OmniScribe Deep Refactor Report — Forward-Looking Structural Plan

**Date:** 2026-08-20
**Author:** Mavis (orchestrator session `mvs_11b2c7e9e984415cae7cfd4b71b3c612`)
**Status:** Design — awaiting user "go" before any code change
**Scope:** Whole-repo forward refactor plan, structural / architectural axis (NOT bug fixes)
**Companion documents:**
- `audits/2026-08-17-comprehensive-5-domain-audit.md` — primary bug-class audit (66 findings)
- `audits/2026-08-18-comprehensive-5-domain-audit.md` — refreshed after residual sweep
- `audits/2026-08-19-tech-debt-remediation-plan.md` — 6-phase remediation plan
- `audits/2026-08-19-secondary-validation-pass.md` — 30 new build-up findings
- `audits/2026-08-19-phase-6-plugin-migration-design.md` — deferred design
- `AGENTS.md` "Plugin Context Migration Status" table

---

## 1. Executive Summary

The 2026-08-17/18 audits and their four remediation phases (P0 → HIGH → MEDIUM → secondary) plus the secondary validation pass closed **64+ bug-class findings** across the stack. The 2026-08-19 secondary pass found 30 new build-up items; 24 have been addressed. The remaining OPEN items (D2-04, D2-06, D2-12, D4-04, D5-02, D1-08) are small bug fixes — not refactors.

This report covers what is **NOT** covered by the existing audits: **structural / architectural refactors** that improve code organization, abstraction boundaries, and forward velocity without changing observable behavior. They are the work that prevents the next audit from finding 30 new build-up items.

**61 findings across 4 domains**, organized by domain prefix:

| Domain | Prefix | Findings | Highest Severity |
|---|---|---|---|
| **1. Core Pipeline** | `CORE-` | 17 | P0 (1) |
| **2. API & Services** | `API-` | 16 | P1 (6) |
| **3. Frontend** | `FE-` | 15 | P1 (4) |
| **4. Tooling, Tests, Scripts** | `TOOL-` | 13 | P2 (10) |
| **Total** | | **61** | |

**Six cross-cutting themes** emerged from the 4 parallel reviews (see §3 for detail):

1. **God classes / monolithic files** are absorbing new features that should be their own modules. `HybridEngine` (1171 LOC, 7 phases), `routers/ocr.py` (1054 LOC, 7+ concerns), `routers/config.py` (882 LOC, 4 domains), `frontend/src/lib/stores/appStore.ts` (370 LOC, 9 unrelated stores).
2. **Singleton-by-module-global** is the only access path. `routers/state.py` singletons, `routers/ocr.py:75` module-level `manager`, three separate `LazySingleton` implementations in `core/aligner.py` / `core/ocr/resilience.py` / `core/ocr/multi_format_client.py`. The plugin-context migration Phase 6 is doing the work FastAPI's `Depends()` does for free.
3. **Service layer is missing for most domains**. `workstationService.ts` is the only well-shaped FE service; the 5 other view pipelines (`translation`, `extraction`, `transcription`, `glossary`, `jobs`) bypass `endpoints.ts` and call `fetchApi` directly. The `workstationService.ts` pattern is the template the others should adopt.
4. **Design-system primitives are incomplete**. `Tabs`, `Table`, `FileInput`, `Chip`, `Spinner`, `EmptyState`, `Icon` are all missing despite being documented as "the only place this pattern lives" — the team has been inventing them per-view.
5. **Retry / circuit-breaker loops are triplicated**. `core/ocr/processor.py:_chat`, `core/grounded/prompted.py:_call_with_retry`, `core/ocr/multi_format_client.py` each implement the same loop with subtle drift. A single `VLMClient` would unify them.
6. **Long-tail test/fixture drift**. `tests/conftest.py` registers 3 of 6 example PDFs; `test_integration.py:27` duplicates the list; `test_ui.py:24` hard-codes a different one. The 8 `.diag_*.py` files at the repo root re-introduce the F24 problem. The `slow_dataset` marker has zero production coverage.

---

## 2. Methodology

### What was reviewed

- **Read-only sweep** by 4 parallel `explore` agents. Each agent read ~30 source files, the relevant audit docs, the relevant tests, and the relevant build scripts.
- **Sources of evidence:**
  - `src/omniscribe/core/` (30 files), `src/omniscribe/api/` (47 files including `api/plugin/`), `src/omniscribe/utils/` (9 files), `src/omniscribe/server.py`, `src/omniscribe/pipeline.py`, `src/omniscribe/evaluation.py`, `src/omniscribe/config.py`
  - `frontend/src/lib/` (~40 .ts files, ~25 .svelte files), `frontend/DESIGN_SYSTEM.md`, `frontend/QA_REPORT.md`, `frontend/package.json`, `frontend/vite.config.*`
  - `tests/` (140+ test files), `scripts/` (25 dev scripts), `.github/workflows/` (nightly.yml + test.yml), `pyproject.toml`, `Dockerfile`, `compose.yaml`, `install.{bat,ps1,sh}`, `start_app.vbs`, `Makefile`, `.pre-commit-config.yaml`, the 8 `.diag_*.py` files at the repo root
- **Cross-referenced** with `audits/2026-08-17/18-domain-*.md` (66 bug-class findings), `audits/2026-08-19-*.md` (secondary pass + Phase 6 design), and the 23 remediation commits in `git log` to confirm what is closed.

### What is explicitly EXCLUDED from this report

- **Bug-class findings** already closed (66 + 24 = ~90 items, all addressed in remediation phases). Listed in §10 Appendix A for traceability.
- **Still-open bug items** that are not refactors: D1-08 (None bbox guard), D2-04 (RateLimit sweep amortize), D2-06 (HTTP parser chunked/gzip), D2-12 (SSE QueueFull), D4-04 (SQLite concurrency test), D5-02 (Dockerfile chown). These are 1-3 line fixes that belong in a "next bug-fix batch", not in a refactor plan.
- **Phase 6 plugin-context migration** (F2-deeper, F11, F13, F27). The design doc at `audits/2026-08-19-phase-6-plugin-migration-design.md` is the source of truth; this report references it as a dependency but does not duplicate the design.

### Severity rubric (different from bug-class audits)

| Sev | Meaning |
|---|---|
| **P0** | Blocking refactor — the current shape prevents the next feature from landing cleanly |
| **P1** | High-leverage refactor — significant forward-velocity gain; should land in the next 3 phases |
| **P2** | Worthwhile refactor — pays off across multiple future changes; schedule opportunistically |
| **P3** | Nice-to-have refactor — local code health; opportunistic or PR-adjacent |

### Effort / Risk rubric

| Tier | Effort | Risk |
|---|---|---|
| **S** | < 1 day | **Low** — internal move, behavior-preserving, covered by existing tests |
| **M** | 1-3 days | **Medium** — touches public surface or new abstraction; needs new tests |
| **L** | > 3 days | **High** — file split, async signature change, lifespan re-order; needs regression run + new tests + staged rollout |

---

## 3. Cross-Cutting Themes

These six patterns appear in 2+ domains. They are the highest-leverage refactors because landing one of them often unlocks or simplifies several findings in the same PR.

### Theme 1: God classes absorb new features instead of yielding them

| Domain | File | LOC | Phases / concerns |
|---|---|---|---|
| Core | `core/workflows/hybrid.py` (HybridEngine) | 1171 | 7 phases (convert, detect, recall×2, dense-select, ocr, refine, repair, finalize) |
| API | `routers/ocr.py` | 1054 | 7+ concerns (route + form parsing + emit + progress bridge + sync/async dispatch + 5 except arms) |
| API | `routers/config.py` | 882 | 4 domains (env parse, store CRUD, per-namespace config, model discovery) |
| FE | `stores/appStore.ts` | 370 | 9 stores (auth, config, theme, tab, toast, modal, model) + 7 namespace functions + 28-field default literal |

Each of these is the place the next feature will land. Splitting now means the next feature lands in the right module.

**Landing sequence:** `HybridEngine` (CORE-01, P0) first because it's blocking; then the 3 API/FE in parallel PRs.

### Theme 2: Singleton-by-module-global everywhere

| Domain | File | Pattern |
|---|---|---|
| API | `routers/state.py:66-77` | 7 module-level aliases over `LocalStateBackend` singleton |
| API | `routers/ocr.py:75` | `from .websocket import manager` (module-level WebSocket connection manager) |
| Core | `core/aligner.py:44-129` | `_shared_predictor` + lock + `reset_*` helper |
| Core | `core/ocr/resilience.py:357-381` | `_default_registry` + lock + reset |
| Core | `core/ocr/multi_format_client.py:27-77` | `_shared_client` + `_shared_client_loop` + lock |

The plugin-context migration (Phase 6 design) is the first half of the fix; FastAPI `Depends()` plumbing (API-05) is the second half. The two should land together.

**Landing sequence:** Phase 6 + API-05 in one PR. Consolidate the 3 core singletons (CORE-14) in a follow-up.

### Theme 3: Service layer exists for 1 of 6 view pipelines

`frontend/src/lib/services/workstationService.ts` is the only well-shaped service in the FE codebase. It owns FormData assembly, error classification, store-patch reducers, and abort-signal propagation. The other 5 view pipelines (translation, extraction, transcription, glossary, jobs) bypass `endpoints.ts` and call `fetchApi` directly with inline `<T>` casts.

**Landing sequence:** FE-01 (extract per-view services) before FE-07 (abort-signal discipline) and FE-10 (test architecture) — the new services are where the abort-signal wiring and the test surface should land.

### Theme 4: Design-system primitives are missing

`DESIGN_SYSTEM.md` documents a 12-primitive UI library, but 7 of the patterns that should be primitives are hand-rolled per-view:

- `Tabs` (3 places: TabRibbon, SettingsView, GlossaryView)
- `Table` (3 places: JobHistoryView, GlossaryView×2)
- `FileInput` (2 places: TranscriptionView, GlossaryView)
- `Chip` (1 place: SettingsView, but the QA report flagged it)
- `Spinner` (3 places: Button, TranscriptionView, ProviderModal)
- `EmptyState` (4 places: PageCanvas, JobHistory, Glossary, ProviderModal)
- `Icon` (~30 inline SVGs)

**Landing sequence:** FE-04 (Tabs) and FE-05 (Table) are the two highest-leverage primitive gaps. R6 (the other 5) is a 1-PR follow-up.

### Theme 5: Retry / circuit-breaker loop is triplicated

`core/ocr/processor.py:439-537` (`OCRProcessor._chat`) and `core/grounded/prompted.py:332-395` (`PromptedGroundedOCR._call_with_retry`) implement the same loop with the same `is_transient_error` gating, the same `min(base * 2**attempt, 8.0)` backoff, and the same warning log shape. The shared httpx client in `core/ocr/multi_format_client.py:136-262` is a third copy with no circuit breaker.

**Landing sequence:** CORE-02 (VLMClient extraction) before CORE-05 (ProviderAdapter split) — the retry loop is in one place only if both refactors land in the same PR or CORE-02 lands first.

### Theme 6: Test/fixture drift compounds over time

- `tests/conftest.py:35` registers 3 example PDFs; `test_integration.py:27` redefines the list; `test_ui.py:24` hard-codes a 4th.
- 8 `.diag_*.py` files at the repo root re-introduce the F24 problem the secondary pass just closed.
- `slow_dataset` pytest marker has 2 test files + a nightly job + a `fetch_datasets.py` stub but no production code path ever exercises it.
- `tests/openapi.json` is a 1,100+-line checked-in snapshot with no generation script in the repo.

**Landing sequence:** TOOL-01 (move `.diag_*.py`) is 20 minutes, zero risk, do it today. TOOL-02 (`slow_dataset` pruning) needs a license-review decision first.

---

## 4. Domain 1 — Core Pipeline (`src/omniscribe/core/`, `pipeline.py`, `evaluation.py`, `config.py`)

### Architectural status

- **Decoupling verification:** 🟢 Clean. Zero FastAPI imports inside `core/`. (Per the 2026-08-17 audit, still true.)
- **Phase composition:** 🟡 `HybridEngine` is a 1171-LOC god class that has absorbed 5 added phases (whitespace recall, text-layer recall, repair, trust) since the original split. The next phase will land in the same file.
- **Resilience:** 🟢 Circuit breaker present, but the retry loop is triplicated (see Theme 5).

### Finding register

| ID | Sev | Location | Summary |
|---|---|---|---|
| **CORE-01** | P0 | `core/workflows/hybrid.py:95-1171` | `HybridEngine` god class fuses 7 phases into 1171 LOC. Phase-object split recommended. |
| **CORE-02** | P1 | `core/ocr/processor.py:439-537` + `core/grounded/prompted.py:332-395` | Two near-identical retry+circuit-breaker loops; should collapse to one `VLMClient`. |
| **CORE-03** | P1 | `core/lexicon/lancedb_store.py:700-724` | `_build_where` builds SQL `WHERE` by string concat against user-controlled filter values. |
| **CORE-04** | P1 | `src/omniscribe/evaluation.py` vs `src/omniscribe/core/evaluation.py` | Two unrelated `evaluation.py` modules in different packages; same name, different responsibilities. |
| **CORE-05** | P2 | `core/ocr/multi_format_client.py:136-262` | `complete_vlm_prompt` triplicates the request/payload build path (OpenAI / Anthropic / Ollama). |
| **CORE-06** | P2 | `core/workflows/hybrid.py:531-588` vs `590-635` | `_apply_recall` and `_apply_text_layer_recall` are near-duplicate box-supplement methods. |
| **CORE-07** | P2 | `core/workflows/base.py:217-228` | `EngineBase._apply_trust` scores pages sequentially; trust layer is the critical-path tail for 200-page docs. |
| **CORE-08** | P2 | `core/text_recall.py` + `core/text_layer_recall.py` | Two parallel "box-supplement" recall sources with the same merge contract; need a `BoxRecallSource` Protocol. |
| **CORE-09** | P3 | `core/processors/base.py:50-54` | 3 regexes used only by `StructureAnalysisProcessor` live in the "base" file. Misleading location. |
| **CORE-10** | P2 | `core/glossary.py` + `core/glossary_library/` + `core/lexicon/` | 3 parallel glossary data shapes / normalization paths. Migration debt from the Phase 5 cleanup. |
| **CORE-11** | P2 | `core/workflows/base.py:339-365` + `core/postprocess.py` | `DictionaryPostProcessor` constructed per-call, not per-process; 200 PyEnchant handle allocations for a 200-page run. |
| **CORE-12** | P3 | `core/ocr/processor.py:186-216` | `OCRProcessor.__getattr__` test-compat shim makes the instance/class boundary ambiguous. |
| **CORE-13** | P3 | `core/ocr/processor.py:518-537` | Manual "context size" string match duplicates the list already in `is_transient_error`. |
| **CORE-14** | P3 | `core/aligner.py:44-129` + `core/ocr/resilience.py:357-381` + `core/ocr/multi_format_client.py:27-77` | Three separate `LazySingleton` patterns; consolidate into one `core/utils/process_singleton.py`. |
| **CORE-15** | P3 | `core/glossary_sources/__init__.py:35-44` | String-based parser dispatch via `PARSERS: dict[str, str]` of `"module.function"` paths. |
| **CORE-16** | P3 | `core/lexicon/lancedb_store.py:622-627` | Dead code: `_has_vector_index` never called. |
| **CORE-17** | P3 | `core/pdf/handler.py:38-206` | `PDFHandler` facade is a pass-through over module-level functions; `static_method` aliases add no behavior. |

### CORE-01 — `HybridEngine` god class (P0)

**Evidence:** `core/workflows/hybrid.py:95-1171`. The class owns `_convert_pages`, `_detect_layout`, `_apply_recall`, `_apply_text_layer_recall`, `_select_dense_pages`, `_ocr_pages`, `_ocr_per_box`, `_refine_pages`, `_refine_uncertain`, `_repair_pages`, `_finalize`, plus the bounded LRU decode cache.

**Problem:** Every phase added since the original split (whitespace recall, text-layer recall, repair, trust) has been inlined. The file is the only place engine logic lives, so reading any one phase requires the rest in your head. The `_decoded_cache` LRU is re-implemented inline.

**Proposed refactor:** Split into phase objects that share a small `PagePhase` Protocol. Concrete extraction: `convert/`, `detect/` (with `WhitespaceRecallSource` + `TextLayerRecallSource` as separate classes, per CORE-08), `ocr/`, `refine/`, `repair/` (already its own module), and a thin `HybridEngine` that composes them. The `_decoded_cache` moves to a `DecodedPageCache` helper.

**Effort:** L. **Risk:** High — needs regression run on `tests/test_aligner.py` and `tests/test_workflow_*`. **First step:** 1-day "extract `_ocr_per_box` to its own module" spike before the full split.

### CORE-02 — Retry / circuit-breaker loop triplicated (P1)

**Evidence:** `core/ocr/processor.py:439-537` (`OCRProcessor._chat`) and `core/grounded/prompted.py:332-395` (`PromptedGroundedOCR._call_with_retry`) implement the same loop. The shared httpx client in `multi_format_client.py` is a third copy with no circuit breaker.

**Problem:** Both implement `await circuit_breaker.check()`, `for attempt in range(max_retries + 1)`, the same `is_transient_error` gating, the same `min(base * 2**attempt, 8.0)` backoff, the same `last_exc` re-raise pattern. They diverge only in messages payload and final `LLMCallError` wrap.

**Proposed refactor:** Extract a `VLMClient` (or `VLMCaller`) class in `core/ocr/client.py` that owns the `CircuitBreakerRegistry` lookup, the retry loop, the message construction, and the `LLMCallError` shaping. `OCRProcessor._chat` and `PromptedGroundedOCR._call_with_retry` collapse to one call. The translation `call_llm` (which does its own dispatch) gets the same retry semantics for free.

**Effort:** M. **Risk:** Medium. **Depends on:** CORE-12 (the `__getattr__` shim should not exist in the new shape).

### CORE-03 — `LanceDBLexiconStore` builds SQL `WHERE` by string concat (P1)

**Evidence:** `core/lexicon/lancedb_store.py:700-714` (`_build_where`) interpolates user-controlled `query.source_lang`, `query.target_lang`, `query.domain`, `query.glossary_ids` into a LanceDB `WHERE` clause. The hand-rolled `_sql_escape` at lines 717-724 only doubles single quotes.

**Problem:** The whole `glossary_sources/sql_table.py:86-92` flow (which already uses SQLAlchemy `text()` with bound params) was deliberately hardened against this exact class of bug. The lexicon store re-introduces the same hazard against a different SQL engine.

**Proposed refactor:** Either (a) replace manual string assembly with `pyarrow.compute` boolean masks on the in-memory table (the same fallback already in `_hybrid_via_arrow`), or (b) use SQLAlchemy core (already a dep via the glossary SQL importer) with bound parameters and a thin adapter that emits LanceDB's filter syntax. Option (a) is simpler.

**Effort:** M. **Risk:** Low. **Depends on:** None — LanceDB filter API is stable.

### CORE-04 — Two unrelated `evaluation.py` modules (P1)

**Evidence:** `src/omniscribe/evaluation.py` (root) is the IoU matcher for GLM-OCR fixtures, consumed only by `scripts/confidence_*.py`. `src/omniscribe/core/evaluation.py` holds `EvaluationMetrics` + `evaluate_document` for processors.

**Problem:** Same name, different responsibilities, no shared code. `core/__init__.py:5` re-exports the core one. Future readers will not know which one a call site wants.

**Proposed refactor:** Rename root one to `src/omniscribe/confidence_eval.py` (matches the `scripts/confidence_eval.py` consumer) and re-export from the root `omniscribe/__init__.py` if convenience is needed.

**Effort:** S. **Risk:** Low. **Depends on:** None.

### Sequenced roadmap (Core)

1. **CORE-04** (S) — rename `evaluation.py` to `confidence_eval.py`. Zero behavior change. Unblocks naming.
2. **CORE-02** (M) — extract `VLMClient`. Unblocks CORE-05.
3. **CORE-12 + CORE-13** (S) — delete `__getattr__` shim and the duplicate context-size string match. Cleanup before CORE-02 lands.
4. **CORE-16** (S) — delete `_has_vector_index`. Trivial.
5. **CORE-05** (M) — `ProviderAdapter` split. Builds on CORE-02.
6. **CORE-06 + CORE-08** (M) — `BoxRecallSource` Protocol. Unblocks the next recall source.
7. **CORE-07** (S, M risk) — `asyncio.gather` in trust scoring. Add ordering-preservation test.
8. **CORE-11** (S) — `DictionaryPostProcessor` cache. Quick win.
9. **CORE-09 + CORE-15 + CORE-17** (S each) — local moves and dead-code deletion. Bundle in one PR.
10. **CORE-14** (M) — singleton consolidation. Gated on a 4th singleton appearing.
11. **CORE-03** (M) — `LanceDBLexiconStore` SQL injection. The one Core P1 left.
12. **CORE-10** (M) — 3-shape glossary consolidation. Calendared with the Phase 5 cleanup.
13. **CORE-01** (L) — `HybridEngine` split. The big one. Last because it touches everything.

---

## 5. Domain 2 — API & Services (`src/omniscribe/api/`, `server.py`, `utils/`)

### Architectural status

- **Authentication:** 🟢 Constant-time bearer auth; per-namespace auth tokens. Closed in audit remediation.
- **SSRF hardening:** 🟢 `BlockedAPIBaseError` + `_PinnedIPTransport` with chunked/gzip. Closed in audit remediation. But the call sites that emit the rejection are inconsistent (12+ sites, 3 idioms — see API-03).
- **State backends:** 🟡 Three implementations (memory, sqlite, redis) re-implement the same `TextArtifactStore` contract on different primitives.
- **Progress transports:** 🟡 WebSocket + SSE both implement progress fan-out in parallel. The comment at `server.py:247-250` confirms the WebSocket router is on borrowed time until "task 7.4".

### Finding register

| ID | Sev | Location | Summary |
|---|---|---|---|
| **API-01** | P1 | `routers/ocr.py:1-1054` | God router; 7+ concerns; 30-form-param signatures duplicated across sync/async routes. |
| **API-02** | P1 | `services/state_backend_{sqlite,redis}.py` | Three state backends each re-implement the `TextArtifactStore` contract. |
| **API-03** | P1 | `routers/` + `services/security.py:64` (4 idioms, 12 files) | Four distinct error-envelope idioms (`api_error_response`, `JSONResponse`, `HTTPException`, duplicated `_ai_error_response`). |
| **API-04** | P1 | `routers/config.py:1-882` | God config router; 4 domains in one file. |
| **API-05** | P1 | `routers/state.py:66-77` + 6 call sites | Module-level singleton state is the only access path; no `Depends()` plumbing. |
| **API-06** | P2 | 12+ SSRF-call sites across routers | SSRF guard repeated with 3 different idioms; should be a single `safe_api_base` dependency. |
| **API-07** | P2 | `routers/websocket.py` + `routers/events.py` + `services/sse_broker.py` | WebSocket and SSE both implement progress fan-out in parallel; should be a `ProgressTransport` Protocol. |
| **API-08** | P2 | `services/progress.py:105-369` (the class) + `routers/websocket.py:70` (singleton grab) | `ProgressService` is the right abstraction but reachable only through a singleton. |
| **API-09** | P2 | `routers/*` (24 routes) | OpenAPI `response_model` coverage is sparse; only 6 declarations across the whole router tree. |
| **API-10** | P2 | `routers/config.py:147-196, 261-280, 403, 425, 449` + `security_middleware.py:265-291` | `_load_config_from_store` mutates a module-level dict on every call; called from auth middleware (every request). |
| **API-11** | P2 | `routers/ocr.py:503-545, 784-825` | Two OCR routes duplicate 24 form parameters and ~150 LOC of orchestration. |
| **API-12** | P2 | 5 cleanup sites: `services/security.py:190-202` + `routers/ocr.py:707,714,753,780,996` + `services/ocr_chunked_runner.py:355-370` | Temp-file cleanup is scattered with no single owner. |
| **API-13** | P3 | `routers/glossary_imports.py:94-99, 366` | `_sync_ssrf_blocked` wraps an async call with `asyncio.run` in a thread pool. |
| **API-14** | P2 | `services/state_backend.py:78-90, 107-152, 437-489` (sqlite), `252-284` (redis) | `StateBackend` Protocol's 7-attribute shape is repeated as class annotations in 3 implementations. |
| **API-15** | P3 | `routers/common.py:17, 21` + 4 importers | `_cleanup` and `_stable_server_error` are private helpers re-imported across modules. |
| **API-16** | P2 | `server.py:120-184` | Plugin-context boot wiring lives inline in `server.create_app`; entangles state + plugin lifetimes. |

### API-01 — `routers/ocr.py` god router (P1)

**Evidence:** 1054 LOC. Routes at 503, 784, 1006. Helpers at 95, 116, 133, 208, 230, 266, 387, 474, 902.

**Problem:** File is a god-module in everything-but-name: 30-form-param route signatures, plugin event emit helpers (`_record_job`, `_emit_job_submitted`, `_emit_job_started`, `_emit_job_cancelled`), WebSocket progress bridging (`_progress_bridge`, `_warning_bridge`, `_cancel_check`, `_log_threadsafe_future_error`), in-thread pipeline driver, and 5 except arms for error-to-envelope mapping. `process_pdf` and `process_pdf_async` repeat the same 24-form-param signature verbatim (only differ in `submit` vs `await run`).

**Proposed refactor:** Extract three modules: (a) `services/ocr_emit.py` (the four `_emit_*` helpers and `_record_job`), (b) `services/ocr_progress_bridge.py` (the cross-loop progress bridge), and (c) `services/ocr_form_signature.py` (the single source of truth for form params — already done in `ocr_settings.py:_form_param_keys()`, so a `_process_form_kwargs(request, settings)` would let both routes call `collect_form_kwargs(**request._asdict())`). Then `process_pdf` and `process_pdf_async` become thin shims that share `_run_ocr_pipeline` and `_execute_ocr_pipeline` plus the form-resolver.

**Effort:** M. **Risk:** Low. **Depends on:** None (internal move).

### API-03 — Four distinct error-envelope idioms (P1)

**Evidence:** `services/security.py:64` (`api_error_response`); `routers/config.py:489, 583, 774, 788, 814, 825, 850, 861` (raw `JSONResponse(403, {"error":...})`); `routers/translation.py:185` + `routers/transcription.py:72, 208` + `routers/providers.py:99, 129` (`raise HTTPException(403, detail=SAFE_API_BASE_ERROR)`); `routers/translation.py:41` + `routers/extraction.py:37` (byte-for-byte identical `_ai_error_response` defined twice); `routers/transcription.py:229, 231, 232` (`raise HTTPException(503, detail=_CONFIG_BACKEND_INCOMPATIBLE_MESSAGE)`). Total: 116 error-return sites across 12 files.

**Problem:** Operators integrating against the API see three response shapes depending on the route: `{"error": "..."}`, FastAPI's `{"detail": "..."}` (HTTPException), and `{"error": "...", "detail": "..."}` (api_error_response with detail). The two `_ai_error_response` helpers are byte-for-byte identical, living in two routers, with no shared module.

**Proposed refactor:** Add a single `envelope.py` module that exposes `envelope(status, error, detail=None) -> JSONResponse` and an `api_error(status, error, detail=None)` shorthand. Replace every `JSONResponse(status_code=..., content={"error": ...})` and `raise HTTPException(status, detail=...)` with the helper, with the rule "HTTPException only for 422 validation; envelope for everything else". Then deprecate the duplicate `_ai_error_response` in favor of the envelope module's `ai_error_response` import. Land alongside API-09 so error responses get `responses=` annotations too.

**Effort:** M. **Risk:** Low. **Depends on:** API-09 (so the OpenAPI schema reflects the unified envelope).

### API-05 — Module-level singleton state, no `Depends()` (P1)

**Evidence:** `routers/state.py:66-77` (singleton aliases); `routers/jobs.py:43-46` (manual fallback to `state.ocr_job_queue`); `routers/ocr.py:75` (`from .websocket import manager`); `routers/ocr.py:458` (`state.text_artifacts.create`); `routers/ocr.py:998` (`state.ocr_job_queue.submit`); `routers/translation.py:50` (`state.text_artifacts.get`); `routers/artifacts.py:44` (`state.text_artifacts.get`).

**Problem:** Every router reaches into the module-level `state.*` singletons. Tests must monkeypatch `state.backend.text_artifacts` instead of injecting a fixture. Multi-tenant deployments have no way to swap backends per request. The plugin-context migration is doing exactly the work that FastAPI's `Depends()` would do for free.

**Proposed refactor:** Add a `dependencies.py` module with typed `get_backend`, `get_text_artifacts`, `get_progress_service`, `get_ocr_job_queue` callables that read from `request.app.state.backend` (set in `lifespan`). Move the 7 singletons from `state.py` to `app.state.backend` in the lifespan, and have `state.py` re-export them as `state.backend = app.state.backend` (with a fallback for non-app contexts). Call sites transition to `Depends(get_text_artifacts)` over a few PRs. The plugin-context migration window stays open during the transition.

**Effort:** L. **Risk:** Medium. **Depends on:** Phase 6 plugin-context migration (should land in parallel so the two paths share the same lifetime).

### API-09 — OpenAPI `response_model` coverage is sparse (P2)

**Evidence:** `grep response_model=` shows 6 declarations, all in `health.py` (4) and `transcription.py` (2 at lines 41, 102, 159, 195). Every other route — including the high-traffic `process_pdf`, `extract_data`, `translate_text`, `get_jobs`, `create_document_export` — returns dict/JSONResponse without a typed schema. `schemas/responses.py` already defines 25+ Pydantic response models; only a few are wired up.

**Problem:** OpenAPI consumers (TypeScript codegen, integration tests, ops dashboards) get `additionalProperties: true` for nearly every endpoint. Wire shapes are already documented in `schemas/responses.py` — they just aren't connected.

**Proposed refactor:** One-mechanical-task refactor: for every `@router.get|post|put|delete` without `response_model=`, add the appropriate `response_model=` from `schemas/responses.py`. For `StreamingResponse` / `FileResponse` routes (downloads), document with `responses={200: {"content": {"application/pdf": {}}}}`. Land alongside a default-error-response annotation so API-03's unified envelope is reflected in the schema too.

**Effort:** S. **Risk:** Low. **Depends on:** API-03 (so the error schema annotation matches the envelope).

### Sequenced roadmap (API)

1. **API-15** (S) — rename `_cleanup` / `_stable_server_error` to public names in `services/api_helpers.py`. Pure rename. Unblocks future refactors that need the helpers.
2. **API-03** (M) — unified error envelope. Foundational; unblocks API-06, API-09.
3. **API-06** (S) — `safe_api_base` dependency. Lands cleanly once API-03 is in.
4. **API-13** (S) — convert `import_glossary_from_url` to `async def`. One-route, ~5 lines. Bundle with API-06.
5. **API-04** (M) — split `routers/config.py` into 4 files. Pure file split, route URL surface unchanged.
6. **API-09** (S) — `response_model=` coverage. Mechanical. Bundle with API-04 (the new file boundaries make the audit easier).
7. **API-11** (S) — extract `_process_form` helper. Bundle with API-01 split.
8. **API-01** (M) — split `routers/ocr.py`. The big API refactor. Internal move; no behavior change.
9. **API-12** (M) — `services/temp_registry.py`. Additive; existing `cleanup_files` keeps working.
10. **API-02 + API-14** (L, M) — state backend consolidation. Bundle R2 + R14 as one PR.
11. **API-07** (L) — `ProgressTransport` Protocol. Additive.
12. **API-08** (M) — move `ProgressService` to `app.state` and the static `build_*_frame` methods to `frame_builders.py`. Depends on API-05.
13. **API-10** (M) — replace module-level dict with frozen Pydantic `RuntimeConfig`. Depends on API-05.
14. **API-05 + API-16** (L, M) — `Depends()` plumbing + lifespan `LifespanStep` decomposition. Last because everything else funnels through it. Land in parallel with Phase 6 plugin migration.

---

## 6. Domain 3 — Frontend (`frontend/src/`)

### Architectural status

- **Framework:** Svelte 5.56.9 installed, Svelte 4 idioms in use (`export let` props, `writable<T>()` stores, `createEventDispatcher`). A runes migration is a separate ~3-week project; not flagged here.
- **Design system:** 🟡 12 primitives in `lib/components/ui/`, but 7 patterns (Tabs, Table, FileInput, Chip, Spinner, EmptyState, Icon) are missing and re-implemented per-view.
- **Service layer:** 🟢 `workstationService.ts` is the template. 🟡 The other 5 view pipelines (translation, extraction, transcription, glossary, jobs) bypass it.
- **Accessibility:** 🟢 The audit-closed items (D3-01..D3-17) are all in source. vitest-axe integration landed in the secondary pass. Playwright a11y on the e2e job is the only gap.

### Finding register

| ID | Sev | Location | Summary |
|---|---|---|---|
| **FE-01** | P1 | `endpoints.ts:181-253` (exists); 10 raw `fetchApi<…>('/…')` sites in 5 views | Most views bypass the typed API + service layer. |
| **FE-02** | P1 | `TranslationView.svelte:86-101` + `ExtractionView.svelte:73-88` | `artifactsApi.getText` → flat-text resolution duplicated verbatim across 2 views. |
| **FE-03** | P1 | `SettingsView.svelte:127-450` | `SettingsView` is a 450-LOC four-way if-else chain. |
| **FE-04** | P1 | `TabRibbon.svelte:64-82` + `SettingsView.svelte:24-43, 160-192` + `GlossaryView.svelte:142-167` + `ExtractionView.svelte:181-185` | `Tabs` primitive missing — 3 places re-implement tablist markup. |
| **FE-05** | P2 | `JobHistoryView.svelte:111-181` + `GlossaryView.svelte:181-242, 256-275` | `Table` primitive missing — 2 views hand-roll `<table>` markup. |
| **FE-06** | P2 | `TranscriptionView.svelte:183-192` + `GlossaryView.svelte:329-338` + `SettingsView.svelte:255-275` + 3 spinners + 4 empty states | Missing small primitives: `FileInput`, `Chip`, `Spinner`, `EmptyState`. |
| **FE-07** | P1 | `TranslationView.svelte:193-214` + `TranscriptionView.svelte:76-79` + `TabRibbon.svelte:30-37` | `AbortSignal` discipline: 3 components leak past unmount. |
| **FE-08** | P2 | 34 `try {}` blocks in 12 files | Error→toast copy-paste; 54 `pushToast` calls. |
| **FE-09** | P2 | `appStore.ts:1-370` | `appStore.ts` is a 370-LOC kitchen-sink; should be a thin re-export surface. |
| **FE-10** | P1 | `__tests__/fixtures/` (14 files) + `__tests__/a11y.test.ts:184-309` (6 `it()` blocks) | Test architecture: 14 fixture files for a 7-view app, behavior coverage thin. |
| **FE-11** | P2 | `api.ts:302-397` (4 shapes) + `appStore.ts:103-130` (`defaultConfig`) | Four near-duplicate config response shapes in `types/api.ts`. |
| **FE-12** | P3 | `vite.config.ts:42` + `package.json` + `frontend/` no pre-commit | Build chain gaps: pdfjs is 433kB, no bundle analyzer, no FE pre-commit, no coverage. |
| **FE-13** | P3 | ~30 inline SVGs across 12 files | Inline SVG icons hand-copied — `Icon` primitive or constants file would dedup. |
| **FE-14** | P2 | `appStore.ts:307-346` (3 funcs) + `SettingsView.svelte:218-246, 303-330, 380-405` (3 ModelPickers) | Per-namespace `update*Namespace` near-identical copy-paste. |
| **FE-15** | P3 | `grep stroke-width="2"` + `grep text-\\[` | Tailwind classes with arbitrary stroke widths (per QA-2026-08-17 P2-4) and `text-[Npx]` escapes. |

### FE-01 — Most views bypass the typed API + service layer (P1)

**Evidence:** `endpoints.ts:181-253` exports `translationApi` / `transcriptionApi` / `extractionApi` / `glossaryApi` / `jobsApi` but 10 raw `fetchApi<…>('/…')` call sites ignore them: `TranslationView.svelte:110, 128, 144, 176, 197`; `TranscriptionView.svelte:76`; `ExtractionView.svelte:108`; `GlossaryView.svelte:78, 108`; `JobHistoryView.svelte:25, 44, 60`.

**Problem:** The `endpoints.ts` module exists to centralize URL paths, request shapes, and response parsing, but 5 of 7 views still call `fetchApi` directly with string paths and inline `<T>` casts. The same pattern `workstationService.ts` already established (pure service + injectable deps + typed `apply*Result` reducers) is not replicated for the other pipelines, so each view re-implements FormData construction, error→toast, and store-update logic.

**Proposed refactor:** Extract `translationService.ts` / `extractionService.ts` / `transcriptionService.ts` / `glossaryService.ts` / `jobsService.ts` mirroring `workstationService.ts`. Each owns FormData + payload assembly + error classification + store-patch reducers, so the view collapses to "wire input → call service → apply patches". `endpoints.ts` becomes the only place a URL string lives.

**Effort:** L. **Risk:** Medium. **Depends on:** FE-02 first (shared artifact-text resolver). **Uncertainty:** R1's scope is L but could grow to XL if the views' reactive `$:` blocks for `lastSyncedArtifactId` etc. are entangled with store writes. Worth scoping before committing.

### FE-03 — `SettingsView` is a 450-LOC four-way if-else chain (P1)

**Evidence:** `SettingsView.svelte:127-450` branches `{#if activeNamespace === 'ocr'}{:else if … === 'translation'}{:else if … === 'transcription'}{:else if … === 'auth'}`; each branch is a complete `Card` with its own inputs and a sub-flow for `applyPreset` / `saveConfig`.

**Problem:** Same structural problem the M6 audit already solved for `WorkstationView`. The four branches are independent views with their own state, their own payloads, and their own validation, glued together only by the shared tab strip. `saveConfig` (`SettingsView.svelte:67-114`) is a second 50-LOC if-else that re-implements the dispatch. The `handleTabKeydown` (`SettingsView.svelte:24-43`) and tab markup (`160-192`) duplicate `TabRibbon`'s arrow-key logic.

**Proposed refactor:** Split into `OcrSettingsCard.svelte`, `TranslationSettingsCard.svelte`, `TranscriptionSettingsCard.svelte`, `AuthSettingsCard.svelte` (4 focused components). Move the `saveConfig` dispatch into a `saveNamespaceConfig(namespace, cfg)` helper. Adopt FE-04 (`Tabs` primitive) and delete the per-view keydown handler.

**Effort:** M. **Risk:** Medium. **Depends on:** FE-04 (Tabs primitive).

### FE-04 — `Tabs` primitive missing (P1)

**Evidence:** `TabRibbon.svelte:64-82` + `SettingsView.svelte:24-43, 160-192` own independent `on:keydown` arrow-key handlers; `GlossaryView.svelte:142-167` and `ExtractionView.svelte:181-185` use `SegmentedControl` (which is a `role="group"`, not a tablist) for the same semantic pattern.

**Problem:** The design-system doc §4.7 documents `TabRibbon` as "the only place the active-tab pattern lives" but in practice two views have rolled their own tablist and two more have abused `SegmentedControl` to fake it. The arrow-key + roving-tabindex logic is hand-rolled twice with subtly different semantics (Settings uses "manual activation", TabRibbon uses "automatic").

**Proposed refactor:** Add `Tabs.svelte` to `ui/` with two variants: `underline` (current Settings pattern) and `pill` (current Settings/Glossary segmented pattern), with a shared `on:keydown` + roving tabindex. Migrate SettingsView, GlossaryView, ExtractionView, and TabRibbon to use it.

**Effort:** M. **Risk:** Low. **Depends on:** None.

### FE-07 — `AbortSignal` discipline: 3 components leak past unmount (P1)

**Evidence:** `TranslationView.svelte:193-214` `pollAsyncStatus` uses `setInterval` with no abort; `onDestroy` (`44-46`) calls `clearPolling` only for the local `pollTimer` — the in-flight `/translate/status/...` fetch is not cancellable. `TranscriptionView.svelte:76-79` `fetchApi` is called without `signal`. `TabRibbon.svelte:30-37` `setInterval(pingHealth, 15s)` has no abort, so it survives even component removal from a route change. `workstationService.ts:248-271` already shows the right pattern (`signal.addEventListener('abort', onAbort, { once: true })`).

**Problem:** Three separate leak paths. The most user-visible is the async translation poll: switch tabs mid-async and the polling continues until terminal state (could be 10+ minutes for a long document). This is also a hard regression for the test architecture — no test can drive a `setInterval` to verify abort behavior today because none of the views plumb signals.

**Proposed refactor:** Pick a single `createAbortController()` lifecycle helper (e.g. in `$lib/utils/`) that owns one `AbortController` per component instance, cancels on `onDestroy`, and exposes `controller.signal` for every `fetchApi` / poll / interval. Apply to the 3 sites + add a regression test that mounts a view, kicks off the operation, unmounts, and asserts no further network calls.

**Effort:** M. **Risk:** Medium. **Depends on:** None — purely additive.

### FE-10 — Test architecture: 14 fixture files for a 7-view app (P1)

**Evidence:** `__tests__/fixtures/MockView{Workstation,Translation,Transcription,Settings,Jobs,Glossary,Extraction}.svelte` (7) + `MockChrome{Toast,TabRibbon,ProviderModal,ExportModal,AuthBanner}.svelte` (5) + `MockChrome.svelte` + `MockView.svelte` = 14 fixture files for the App.svelte mounting test alone. `__tests__/a11y.test.ts` is 316 lines but only 6 `it()` blocks, half of which are axe-core no-new-violation checks. `workstationService.test.ts` is the only deep service test (100+ assertions). No behavior test for `TranslationView.svelte` (most complex view), `ExtractionView`, `GlossaryView`, `TranscriptionView`, `SettingsView` despite all having multi-step async flows.

**Problem:** The fixture sprawl exists because each test re-imports every view as a stub; one shared `test-utils/mountAppWithMocks.ts` that takes a single `{ activeView: 'workstation' | 'translation' | ... }` argument would collapse 7+5 fixture files into one. The behavior-coverage gap is the real cost: when FE-01 lands and moves the dispatchers into services, those services need tests, and there is no per-view harness to write them against.

**Proposed refactor:** (1) Add `test-utils/appHarness.ts` that mounts App with all view + chrome fixtures, returning `{ setActiveTab, getView, getByTestId, … }`. Delete the 14 fixture files. (2) Add at least one behavior test per view (focused on the new service's `apply*Result` reducer) so FE-01 lands with test coverage instead of regressing silently.

**Effort:** M. **Risk:** Low. **Depends on:** None.

### Sequenced roadmap (Frontend)

1. **FE-04** (M) — `Tabs` primitive. Foundational for FE-03 and the GlossaryView/ExtractionView sub-tabs.
2. **FE-05** (M) — `Table` primitive. Bundle with FE-04 (one PR, two primitives).
3. **FE-06** (M) — `FileInput`, `Chip`, `Spinner`, `EmptyState`. Bundle with FE-04 + FE-05 (one PR, 6 primitives).
4. **FE-13** (M) — `Icon` primitive + `src/lib/icons.ts`. Bundle with FE-06.
5. **FE-15** (S) — Tailwind class audit (stroke widths, `text-[Npx]`). Trivial; do alongside the primitives.
6. **FE-02** (S) — `artifactsApi.getTextAsString` + `bindArtifactToText` helper. Quick win.
7. **FE-08** (S) — `reportError(err, defaultMessage, ttlMs?)` helper. Quick win. ~100 LOC of mechanical replacement.
8. **FE-12** (M) — bundle all 4 build-chain improvements (pdfjs lazy-load, bundle analyzer, FE pre-commit, coverage script).
9. **FE-09** (M) — extract `configService.ts` + `modalStore.ts` + `persistence.ts`; collapse `appStore.ts` to ~80 LOC.
10. **FE-14** (S) — collapse 3 `update*Namespace` into one + extract `ModelPicker.svelte`. Bundle with FE-09.
11. **FE-11** (S) — tighten `types/api.ts` config shapes. Bundle with FE-09 + FE-14.
12. **FE-07** (M) — `createAbortController()` helper. Apply to 3 sites.
13. **FE-10** (M) — `test-utils/appHarness.ts` + per-view behavior tests. Unblocks test coverage for FE-01.
14. **FE-01** (L) — extract 5 view services. The big FE refactor. Last because every other FE refactor feeds into it.
15. **FE-03** (M) — `SettingsView` decomposition. Last because the 4 sub-cards need the FE-04 `Tabs` primitive.

---

## 7. Domain 4 — Tooling, Tests, Scripts (`scripts/`, `tests/`, `.github/workflows/`, `Dockerfile`, `compose.yaml`, `pyproject.toml`, `install.*`, `start_app.*`, `Makefile`, `.diag_*.py`)

### Architectural status

- **Hygiene axis:** 🟢 F22/F23/F25/F26/F30 closed in remediation. `install.sh:113-125` has Docker check, `start_app.vbs:14-65` has log rotation, `a11y.test.ts:184` has vitest-axe, `test_phase2_*.py` are split into 7 per-finding files.
- **Growth-pain axis:** 🟡 Three new drifts: (a) 8 `.diag_*.py` files at the repo root re-introduce the F24 problem; (b) the `slow_dataset` marker has 2 test files + a nightly job + a `fetch_datasets.py` stub but no production code path; (c) the new `api/plugin/` infrastructure has 5 seams with 18 test files but 3 of 5 are unregistered at boot.
- **Build chain:** 🟡 Version pins scattered across 4+ files; cross-platform install paths with subtle drift.

### Finding register

| ID | Sev | Location | Summary |
|---|---|---|---|
| **TOOL-01** | P2 | `.diag_sse.py` … `.diag_sse8.py` (8 files at `D:/OmniScribe/`) | `.diag_*.py` diagnostic shelf re-introduces the F24 problem at the repo root. |
| **TOOL-02** | P2 | `pyproject.toml:198` + 2 test files + `.github/workflows/nightly.yml:74-153` + `scripts/fetch_datasets.py:70-93` | `slow_dataset` pytest marker is half-built: marker + 2 test files + nightly CI job + `fetch_datasets.py` stub, zero production coverage. |
| **TOOL-03** | P2 | `src/omniscribe/api/plugin/seams.py:50-198` + `server.py:117-135` + `tests/api/plugin/test_*.py` (18 files) | `api/plugin/` ships 5 Protocol seams with 18 test files; 3 of 5 are unregistered at boot. |
| **TOOL-04** | P2 | 9 `sys.path.insert` sites in `scripts/` | `scripts/` sprawl: 25 files, 9 duplicate the same `sys.path.insert` dance, no shared utility module. |
| **TOOL-05** | P2 | `Dockerfile:40` + `install.sh:47` + `install.ps1:40` + `.pre-commit-config.yaml:36` + `pyproject.toml:162, 191` | Version pins are scattered across 4+ files with no central source of truth. |
| **TOOL-06** | P2 | `tests/test_audit_medium_d{1,2,4}.py` + `tests/test_repo_hygiene.py` | `test_audit_medium_d*.py` + `test_repo_hygiene.py` "regression-of-regression" pattern needs its own test. |
| **TOOL-07** | P3 | `tests/conftest.py:35` + `tests/test_integration.py:27` + `test_ui.py:24` + `tests/test_grounded.py:42-43` | `tests/conftest.py` registers only 3 of 6 `examples/` PDFs; the others are referenced by hard-coded paths. |
| **TOOL-08** | P3 | `pyproject.toml:68-87` (`memory = [...]` and `lexicon = [...]` are character-identical) | `[memory]` deprecation alias is a 4-line verbatim duplicate of `[lexicon]` extras. |
| **TOOL-09** | P3 | `tests/test_scripts_smoke.py:97-120` (only checks import-time errors) | `test_scripts_smoke.py` only checks import-time errors; behavioural regressions in dev scripts slip through. |
| **TOOL-10** | P3 | `tests/openapi.json` (1,100+-line checked-in snapshot) | `tests/openapi.json` is a 1,100+-line checked-in snapshot of an API spec; no generation script in the repo. |
| **TOOL-11** | P3 | `examples/` (7 files) | `examples/` binaries ship in git without provenance / license metadata. |
| **TOOL-12** | P3 | `install.bat` + `install.ps1` + `install.sh` + `start_app.vbs` + `start_app.sh` + `stop_app.sh` | Three cross-platform install paths with subtle drift. |
| **TOOL-13** | P3 | `frontend/src/**/*.ts` (40 files) + `__tests__/*.test.ts` (21 files) | Frontend has 21 `.test.ts` files vs ~40 `.ts` source files (~50% coverage) and no Playwright a11y spec in CI. |

### TOOL-01 — `.diag_*.py` diagnostic shelf re-introduces F24 (P2)

**Evidence:** 8 files at the repo root: `.diag_sse.py`, `.diag_sse2.py`, …, `.diag_sse8.py`. Not gitignored. Identical pattern to the `tests/_diag/` originals that F24 moved.

**Problem:** F24 closed the `tests/_diag/` shelf by moving 3 files to `scripts/diagnostics/`. A second wave of 8 SSE-debug files now sits at the repo root with a leading dot (so pytest skips them, but a re-rename or directory-collect change silently re-introduces the same collection risk).

**Proposed refactor:** Move the 8 files into `scripts/diagnostics/` alongside the existing 3. Update the file-level docstrings to point at `scripts/diagnostics/test_sse_keepalive.py` (the canonical SSE smoke). Add `/.diag_*.py` to `.gitignore` as a belt-and-suspenders to catch future shelf scripts. ~20 minutes of work.

**Effort:** S. **Risk:** Low. **Depends on:** None.

### TOOL-02 — `slow_dataset` marker is half-built (P2)

**Evidence:** `pyproject.toml:198` (marker registered); `tests/test_kie_hvqa_hallucination_regression.py:52` + `tests/test_ocr_quality_calibration_regression.py:49` (`pytestmark = pytest.mark.slow_dataset`); `.github/workflows/nightly.yml:74-153` (a 5-step `calibration` job that downloads fixtures and runs `pytest -m slow_dataset`); `scripts/fetch_datasets.py:70-93` (deliberate `NotImplementedError` stub returning exit 77).

**Problem:** Both regression tests always skip (the full fixtures don't ship), so the nightly job is structurally a no-op that costs 5 minutes of CI + a `tests/fixtures/datasets/ocr_quality_full.json` cache entry that never gets read. The marker and the `AGENTS.md:36` mention will outlive the license review, but the test files and the nightly job block until the gate opens.

**Proposed refactor:** Three options, in increasing boldness: (a) **minimal** — change `pytest -m slow_dataset` in `nightly.yml:145` to `pytest -m slow_dataset --co -q` (collect-only) so the job still validates "marker wires up" without running the skip-everything tests; (b) **moderate** — drop the dedicated regression test files and merge them into a single `tests/test_slow_dataset_placeholder.py` that asserts the marker is registered and the stub script exits 77; (c) **bold** — delete the marker, the test files, the `calibration` job, and `fetch_datasets.py` until the license review actually lands. **Recommendation:** option (b) for now (preserves the test-pyramid documentation while removing the cost), option (c) once the license-review timeline is known.

**Effort:** S. **Risk:** Low. **Depends on:** License-review decision.

### TOOL-03 — `api/plugin/` ships 5 seams, 3 unregistered at boot (P2)

**Evidence:** `src/omniscribe/api/plugin/seams.py:50-198` defines `JobQueue`, `SessionLog`, `ConfigStore`, `ProgressService`, `TextArtifactStore`. Boot registers only `JobQueue` and `SessionLog`; the other three `get_*()` calls all return `None` and consumers fall through to the `api/routers/state.py` singletons. Test coverage is heavy (12 events, 4 seam/provider, 4 projection). Phase 6 design doc at `audits/2026-08-19-phase-6-plugin-migration-design.md` exists but has no "go" yet.

**Problem:** The Cordis-style plugin container defines 5 Protocol-based seams with full test coverage but only 2 of 5 are wired at boot. The package is currently documentation-plus-partial-migration.

**Proposed refactor:** Land the Phase 6 design in one PR: mount the remaining three seams in `server.py:117-135` (ConfigStore / ProgressService / TextArtifactStore×3), convert `PLUGIN_CONTEXT_ENABLED` to a `ConfigStore`-backed runtime knob, narrow the dual-write `except` to `(ServiceNotFoundError, ContextDisposedError)`, add an `asyncio.Lock` to `PluginContext.mount/unmount`. The audit-secondary plan already contains the full design.

**Effort:** M. **Risk:** Medium. **Depends on:** Phase 6 design (already drafted).

### TOOL-04 — `scripts/` sprawl: 9 duplicate `sys.path.insert` (P2)

**Evidence:** `scripts/debug_alignment.py:12`, `scripts/debug_detection_only.py:19`, `scripts/debug_image_input.py:11`, `scripts/debug_llm_raw.py:12`, `scripts/inspect_pdf.py:12`, `scripts/test_check.py:12`, `scripts/visualize_bboxes.py:14`, `scripts/visualize_comparison.py:16`, `scripts/verify_output.py:12` (9 sites). Two styles of path-insertion, both copy-pasted. A third variant in `scripts/diagnostics/test_*.py` (`sys.path.insert(0, "src")`).

**Problem:** When `scripts/` is moved or restructured, all 12 call sites need updating in lockstep. There is no `scripts/_common.py`, no `scripts/pyproject.toml`-style package marker.

**Proposed refactor:** Extract a `scripts/_common.py` exposing `PROJECT_ROOT: Path` and a `setup_sys_path()` helper. Convert all 12 call sites to `from _common import PROJECT_ROOT, setup_sys_path; setup_sys_path()`. The 3 diagnostic files in `scripts/diagnostics/` use a different (hard-coded `"src"`) variant — they should use the same helper so a single source of truth exists.

**Effort:** S. **Risk:** Low. **Depends on:** None. **Unblocks:** TOOL-12.

### TOOL-05 — Version pins scattered across 4+ files (P2)

**Evidence:** `Dockerfile:40` (`UV_VERSION=0.11.16`); `install.sh:47` (`UV_VERSION="0.11.16"`); `install.ps1:40` (`$uvVersion = "0.11.16"`); `.pre-commit-config.yaml:36` (`uv-pre-commit: rev: 0.8.7`); `pyproject.toml:162` (`ruff>=0.16.2`); `.pre-commit-config.yaml:20` (`ruff-pre-commit: rev: v0.16.2`); `pyproject.toml:191` (Python 3.11); `Dockerfile:28` (Python 3.14-slim); `test.yml:69` (Python 3.11/3.13 matrix).

**Problem:** A version bump in any tool requires editing 2-4 files in lockstep. The uv pre-commit rev (`0.8.7`) and the standalone uv installer (`0.11.16`) are different artifacts but visually similar. The ruff pre-commit `v0.16.2` and pyproject `>=0.16.2` already drifted once.

**Proposed refactor:** Add a `[tool.omniscribe.toolchain]` table to `pyproject.toml` with `uv = "0.11.16"`, `uv-pre-commit = "0.8.7"`, `ruff = "0.16.2"`, `python = "3.11"`. Generate `install.sh`, `install.ps1`, `Dockerfile`, and `.pre-commit-config.yaml` from this table via a `scripts/sync_toolchain.py` step (or document a single `bump-toolchain` Makefile target that does the 4-place edit and runs `uv lock`). The Python matrix in `test.yml` and `nightly.yml` should derive from `[tool.omniscribe.toolchain.python-floors]` and `[tool.omniscribe.toolchain.python-tested]`.

**Effort:** M. **Risk:** Medium. **Depends on:** None.

### Sequenced roadmap (Tooling)

1. **TOOL-01** (S) — move `.diag_*.py` to `scripts/diagnostics/`. 20 min, zero risk. Do first.
2. **TOOL-04** (S) — extract `scripts/_common.py`. Unblocks TOOL-12.
3. **TOOL-09** (S) — add `test_scripts_have_argparse_and_main_guard()`. ~30 lines.
4. **TOOL-07** (S) — single `EXAMPLE_PDF_NAMES` in `tests/conftest.py`. Mechanical.
5. **TOOL-10** (S) — `make openapi` target (or drop the snapshot, call `app.openapi()` directly).
6. **TOOL-11** (S) — `examples/README.md` provenance entries. 30 min.
7. **TOOL-08** (S) — CI guard test that asserts `memory` and `lexicon` resolve to the same install set.
8. **TOOL-02** (S) — option (b) for `slow_dataset` (or option (c) once license-review decision lands).
9. **TOOL-06** (M) — document the meta-regression test pattern in `AGENTS.md`. Cheap, prevents future confusion.
10. **TOOL-03** (M) — Phase 6 plugin migration. Already designed, just needs the "go" call.
11. **TOOL-05** (M) — toolchain version centralization. High value on the next uv/ruff bump.
12. **TOOL-13** (M) — Playwright a11y in CI per-PR. Gated on the e2e becoming a default PR check, which is a separate decision.
13. **TOOL-12** (L) — consolidate launchers into `scripts/launcher.py`. Defer until after TOOL-04 lands.

---

## 8. Cross-Domain Priority Matrix

Top 20 refactors across all domains, ranked by (impact × probability of unblocking other refactors) ÷ (effort + risk). Source IDs in parens.

| Rank | Refactor | Domain | Sev | Effort | Risk | Unblocks |
|---|---|---|---|---|---|---|
| 1 | **HybridEngine god class split** (CORE-01) | Core | P0 | L | High | CORE-06, CORE-08; any future engine phase |
| 2 | **`Depends()` plumbing + `app.state.backend`** (API-05) | API | P1 | L | Med | API-08, API-10, API-12, all consumer code; unlocks Phase 6 |
| 3 | **Phase 6 plugin migration (mount 3 seams + lock + dispose contract)** (TOOL-03) | Tooling | P2 | M | Med | API-05; the foundation for the new infra |
| 4 | **Unified error envelope** (API-03) | API | P1 | M | Low | API-06, API-09 |
| 5 | **`routers/ocr.py` god-router split** (API-01) | API | P1 | M | Low | API-11; any future `/api/process` change |
| 6 | **VLMClient extraction** (CORE-02) | Core | P1 | M | Med | CORE-05; any future call site that needs retry semantics |
| 7 | **Extract 5 view services mirroring `workstationService.ts`** (FE-01) | FE | P1 | L | Med | FE-02, FE-07, FE-08, FE-10; unblocks per-view test coverage |
| 8 | **SettingsView 4-way decomposition** (FE-03) | FE | P1 | M | Med | All settings-namespace feature work |
| 9 | **Tabs primitive** (FE-04) | FE | P1 | M | Low | FE-03, GlossaryView/ExtractionView sub-tabs |
| 10 | **`LanceDBLexiconStore` SQL injection** (CORE-03) | Core | P1 | M | Low | Translation RAG safety |
| 11 | **State backend consolidation** (API-02 + API-14) | API | P1 | L | Med | Any new state field (priority, TTL variant, etc.) |
| 12 | **`_cleanup` / `_stable_server_error` rename + `api_helpers.py`** (API-15) | API | P3 | S | Low | Foundational rename; unblocks future API refactors |
| 13 | **`BoxRecallSource` Protocol** (CORE-08 + CORE-06) | Core | P2 | M | Low | Next recall source; the third box-supplement source |
| 14 | **Two `evaluation.py` modules disambiguation** (CORE-04) | Core | P1 | S | Low | Naming |
| 15 | **`AbortSignal` discipline in 3 components** (FE-07) | FE | P1 | M | Med | Test architecture for FE-01 |
| 14 | **`.diag_*.py` move** (TOOL-01) | Tooling | P2 | S | Low | Hygiene |
| 16 | **`scripts/_common.py`** (TOOL-04) | Tooling | P2 | S | Low | TOOL-12 |
| 17 | **Trust scoring `asyncio.gather`** (CORE-07) | Core | P2 | S | Med | 200-page document tail latency |
| 18 | **3 parallel glossary data shapes consolidation** (CORE-10) | Core | P2 | M | Med | Phase 5 cleanup milestone |
| 19 | **OpenAPI `response_model=` coverage** (API-09) | API | P2 | S | Low | TS codegen, integration tests |
| 20 | **`artifactsApi.getText` dedup** (FE-02) | FE | P1 | S | Low | FE-01 |

---

## 9. Recommended Execution Sequence

The 61 findings collapse into 6 execution phases over ~3 weeks of M-effort + 1 week of L-effort, all in `main`, no new branches needed. Per the user's "consult me before each phase" preference, each phase ends with a "go" gate.

### Phase A — Quick wins, zero-risk hygiene (1 PR, 1 day)

| Refactor | Effort | Rationale |
|---|---|---|
| TOOL-01 move `.diag_*.py` | S | 20 min, zero risk |
| TOOL-04 `scripts/_common.py` | S | Unblocks TOOL-12 |
| TOOL-09 scripts argparse test | S | ~30 lines, cheap |
| TOOL-07 single `EXAMPLE_PDF_NAMES` | S | Mechanical |
| TOOL-10 `make openapi` | S | Adds discoverable refresh path |
| TOOL-11 `examples/README.md` | S | 30 min provenance entries |
| TOOL-08 CI guard for `memory`/`lexicon` alias | S | Self-checking alias |
| API-15 `_cleanup` rename | S | Foundational rename |
| CORE-04 `evaluation.py` rename | S | Naming |
| CORE-16 delete `_has_vector_index` | S | Dead code |
| CORE-09 + CORE-17 base/handler cleanup | S each | Local moves |
| FE-02 `artifactsApi.getTextAsString` | S | Quick win |
| FE-08 `reportError` helper | S | ~100 LOC mechanical replacement |
| FE-15 Tailwind class audit | S | Bundle with FE-13 |

**Acceptance:** `pytest -m "not slow"` green; `npm run build` clean; `npm test` green.

### Phase B — Plugin context migration (1 PR, 1-2 days) — the design is at `audits/2026-08-19-phase-6-plugin-migration-design.md`

| Refactor | Effort | Rationale |
|---|---|---|
| TOOL-03 Phase 6 plugin migration (mount 3 seams + lock + dispose) | M | Design already drafted; unblocks API-05 |
| API-16 `lifespan.py` with `LifespanStep` decomposition | M | Bundle with TOOL-03 |

**Acceptance:** all 5 seams registered at boot; runtime toggle works; `await plugin_ctx.dispose()` runs provider-owned teardown; thread-safe mutation.

### Phase C — Service layers + typed API plumbing (1-2 PRs, 3-4 days)

| Refactor | Effort | Rationale |
|---|---|---|
| API-03 unified error envelope | M | Foundational; unblocks API-06, API-09 |
| API-06 `safe_api_base` dependency | S | Bundle with API-03 |
| API-13 convert `import_glossary_from_url` to `async def` | S | Bundle with API-06 |
| API-04 split `routers/config.py` | M | Bundle with API-03 (the new file boundaries benefit from the envelope) |
| API-09 `response_model=` coverage | S | Bundle with API-04 |
| FE-01 extract 5 view services | L | The big FE refactor. Bundle with FE-07 + FE-10 (test surface) |
| FE-07 `createAbortController()` helper | M | Bundle with FE-01 |
| FE-10 `appHarness.ts` + per-view behavior tests | M | Bundle with FE-01 |

**Acceptance:** every view calls a service; services have tests; envelope is the only error shape.

### Phase D — Core architecture cleanup (1-2 PRs, 3-4 days)

| Refactor | Effort | Rationale |
|---|---|---|
| CORE-12 delete `__getattr__` shim | S | Cleanup before CORE-02 |
| CORE-13 delete duplicate context-size string match | S | Bundle with CORE-12 |
| CORE-02 VLMClient extraction | M | Bundle with CORE-12 + CORE-13 |
| CORE-05 `ProviderAdapter` split | M | Builds on CORE-02 |
| CORE-08 + CORE-06 `BoxRecallSource` Protocol | M | Unblocks the next recall source |
| CORE-07 trust scoring `asyncio.gather` | S | Quick perf win |
| CORE-11 `DictionaryPostProcessor` cache | S | Quick win |
| CORE-14 singleton consolidation | M | Gated on a 4th singleton appearing — defer if not needed |
| CORE-03 `LanceDBLexiconStore` SQL injection | M | Security fix; the one Core P1 left after CORE-02 |

**Acceptance:** `pytest -m "not slow"` green; no behavior change; trust scoring is faster on 200-page docs.

### Phase E — Frontend primitives + state decomposition (1 PR, 1-2 days)

| Refactor | Effort | Rationale |
|---|---|---|
| FE-04 `Tabs` primitive | M | Foundational; unblocks FE-03 |
| FE-05 `Table` primitive | M | Bundle with FE-04 |
| FE-06 4 small primitives | M | Bundle with FE-04 + FE-05 |
| FE-13 `Icon` primitive + `icons.ts` | M | Bundle with FE-04 + FE-05 + FE-06 |
| FE-09 `appStore.ts` decomposition | M | Bundle with FE-14 + FE-11 |
| FE-14 collapse 3 namespace dispatchers | S | Bundle with FE-09 |
| FE-11 tighten `types/api.ts` config shapes | S | Bundle with FE-09 |
| FE-12 build chain (pdfjs lazy-load, analyzer, FE pre-commit, coverage) | M | Bundle as one PR |

**Acceptance:** design-system primitives are the only way these patterns exist; `appStore.ts` is ~80 LOC; pdfjs is lazy-loaded.

### Phase F — API router splits + state backends (1-2 PRs, 3-4 days)

| Refactor | Effort | Rationale |
|---|---|---|
| API-01 split `routers/ocr.py` | M | The big API router refactor |
| API-11 extract `_process_form` helper | S | Bundle with API-01 |
| API-12 `services/temp_registry.py` | M | Bundle with API-01 |
| API-05 `Depends()` plumbing | L | Lands in parallel with Phase 6 (already in Phase B) — finalize here |
| API-08 move `ProgressService` to `app.state` | M | Bundle with API-05 finalization |
| API-10 frozen Pydantic `RuntimeConfig` | M | Bundle with API-05 finalization |
| API-02 + API-14 state backend consolidation | L | Bundle as one PR |
| API-07 `ProgressTransport` Protocol | L | Additive; defer if not needed |
| FE-03 `SettingsView` 4-way decomposition | M | Last because it needs FE-04 |

**Acceptance:** every router is < 400 LOC; state backends share a `BaseStateBackend`; `app.state.*` is the canonical access path; legacy `state.*` is a fallback.

### Phase G — Toolchain centralization + final cleanup (1 PR, 1-2 days)

| Refactor | Effort | Rationale |
|---|---|---|
| TOOL-05 toolchain version centralization | M | Pays off on the next uv/ruff bump |
| TOOL-06 document meta-regression pattern | M | Cheap, prevents future confusion |
| TOOL-02 option (b) for `slow_dataset` | S | Bundle with TOOL-05 |
| TOOL-13 Playwright a11y in CI per-PR | M | Gated on the e2e becoming a default PR check |
| TOOL-12 consolidate launchers | L | Defer until TOOL-04 has settled (after Phase A) |
| CORE-10 3-shape glossary consolidation | M | Calendared with Phase 5 cleanup |
| CORE-01 `HybridEngine` split | L | Last because it touches everything. A 1-day "extract `_ocr_per_box` to its own module" spike is the first step. |

**Acceptance:** `make bump-toolchain` is a one-line operation; meta-regression pattern is documented; `HybridEngine` is decomposed into phase objects.

### Total

- **S-effort:** 19 items
- **M-effort:** 25 items
- **L-effort:** 7 items
- **Total:** ~3 weeks of M-effort + 1 week of L-effort
- **7 PRs** in `main`, no new branches needed (per user's "personal, no shipping pressure")

---

## 10. Out of Scope / Deferred

These items are out of scope for this refactor plan and deserve their own design doc:

1. **Svelte 4 → Svelte 5 runes migration.** The codebase installs Svelte 5.56.9 but every component uses Svelte 4 idioms (`export let`, `writable<T>`, `createEventDispatcher`). A runes migration is a ~3-week project that touches every `.svelte` file. Not flagged as a finding because the legacy mode is working; called out here so the technical debt is acknowledged.

2. **Multi-tenant / per-request backend swap.** API-05 enables this but the consumer-facing design (per-tenant config keys, per-tenant artifact store, per-tenant job queue) is a separate product question. Today's `state.backend` is a process-wide singleton; multi-tenant deployment is a separate track.

3. **Celery job queue provider.** The Phase 6 disposal-ordering contract (F13) is *for* a future `CeleryJobQueue` provider, but writing the provider itself is a separate phase. The current local queue works; the Celery provider would be a follow-up after Phase 6 lands.

4. **`/api/config` UI for `plugin_context_enabled` toggle.** F11 enables the runtime toggle, but the UI form to flip it is a frontend task. This plan only changes the read path.

5. **Document exporters package decision (F1 from secondary pass).** `core/document_exporters/` is a 100-LOC stub; the three real implementations live outside. The `ARCHITECTURE.md:61` rewrite is done; the move/co-locate decision is still open. Per the secondary pass, "the alternative — moving the writers into the package — would create circular imports" — keeping the co-located shape is the right call. Documented in `ARCHITECTURE.md:61`. Not a refactor I'd prioritize.

6. **A11y Playwright integration on the e2e job.** TOOL-13 recommends a `@axe-core/playwright` scan in the `e2e` job. This is gated on the `e2e` job becoming a default PR check (currently `workflow_dispatch`-only + weekly schedule). The decision to make `e2e` a default PR check is a separate track.

7. **Server-Sent Events (SSE) primary transport.** API-07 acknowledges that the WebSocket router is on borrowed time. Replacing WebSocket with SSE as the primary transport is a separate decision that bundles API-07 + several frontend consumers.

8. **Build chain migration to `bun` or `pnpm`.** TOOL-12's launcher consolidation is a Python refactor; switching the FE build chain to a different package manager is a separate decision.

---

## 11. Appendix A — What is already closed (DO NOT re-flag)

### Closed by 2026-08-17 audit remediation (66 findings, 4 batches)

- **Domain 1 (Core):** D1-01 through D1-10 — all closed
- **Domain 2 (API):** D2-01 through D2-13 — all closed
- **Domain 3 (Frontend):** D3-01 through D3-17 — all closed
- **Domain 4 (Testing):** D4-01 through D4-14 — all closed
- **Domain 5 (DevOps):** D5-01 through D5-30 — all closed (per d4e893d: F5-01 to F5-30)

### Closed by 2026-08-19 secondary validation pass (24 of 30 new build-up findings)

Per `audits/2026-08-19-tech-debt-remediation-plan.md` and the corresponding commits (ef90d31 / 0c297d6 / 4b77fe9 / a8e1b68 / 764f98d / 4f3ff24):

- F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F12, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F28, F29, F30 — all closed

### Still OPEN (not refactors — small bug fixes)

- **D1-08** `ReadingOrderProcessor._sort_key` None guard — 1-line fix in `core/processors/reading_order.py:38`
- **D2-04** `RateLimitMiddleware` amortized sweep — `asyncio.TimerHandle` in `security_middleware.py:729-771`
- **D2-06** `_PinnedIPTransport` chunked/gzip — subclass `httpcore.AsyncBaseTransport` in `services/http_fetch.py:65-184`
- **D2-12** SSE `QueueFull` handler — drop-oldest in `routers/events.py:71-78`
- **D4-04** SQLite lock contention test — add `ThreadPoolExecutor` test in `tests/test_state_backend_sqlite.py`
- **D5-02** Dockerfile `chown` after COPY — `COPY --chown=app:app` in `Dockerfile:81-88`

These belong in a "next bug-fix batch", not a refactor plan.

### Deferred by design (Phase 6 plugin migration)

Per `audits/2026-08-19-phase-6-plugin-migration-design.md`:

- F2-deeper (3 remaining seams registered at boot)
- F11 (`PLUGIN_CONTEXT_ENABLED` runtime toggle via ConfigStore)
- F13 (provider-owned disposal via `ctx.effect(...)`)
- F27 (`threading.RLock` on `PluginContext` mutation surface)

This report references Phase 6 as a dependency but does not duplicate the design.

---

## 12. Appendix B — Glossary

| Term | Meaning |
|---|---|
| **Phase object** | A class implementing a `PagePhase` Protocol that owns one phase of the OCR pipeline (convert, detect, OCR, refine, repair). The `HybridEngine` composes a list of phase objects instead of inlining 7 phase methods. |
| **Cordis-style plugin container** | A registry-based dependency injection pattern where services are registered under a Protocol and looked up at runtime. `api/plugin/context.py:35-44` is the OmniScribe implementation. |
| **`Depends()` plumbing** | FastAPI's built-in dependency injection. `request: Request` → `Depends(get_backend)` → call sites receive a typed backend instead of reaching into a module-level singleton. |
| **Service layer** | A module that owns FormData assembly, error classification, and store-patch reducers for a single view pipeline. `workstationService.ts` is the only one today. |
| **`LifespanStep`** | A namedtuple with `setup()` / `teardown()` pairs. The lifespan body becomes a list of steps instead of a hand-ordered sequence of side effects. |
| **`BoxRecallSource`** | A Protocol with `supplement(page_num, image_or_text, boxes) -> list[BBox]`. Whitespace recall and text-layer recall are concrete implementations. |
| **`VLMClient`** | A class that owns the `CircuitBreakerRegistry` lookup, the retry loop, the message construction, and the `LLMCallError` shaping. Replaces the triplicated `_chat` / `_call_with_retry` / `multi_format_client` patterns. |
| **`ProgressTransport`** | A Protocol with `start()`, `subscribe(job_id, callback)`, `publish(job_id, frame)`, `close()`. `WebSocketTransport` and `SSETransport` are concrete implementations. |
| **Phase 6** | The deferred plugin-context migration; design at `audits/2026-08-19-phase-6-plugin-migration-design.md`. Lands 4 sub-changes: F2-deeper, F11, F13, F27. |

---

## 13. Appendix C — Files referenced (for evidence)

- **Core (30 files):** `core/__init__.py`, `core/processors/{base,reading_order,quality,structure,section,layout,table}.py`, `core/workflows/{base,hybrid,grounded,repair,utils}.py`, `core/aligner.py`, `core/text_recall.py`, `core/text_layer_recall.py`, `core/ocr/{processor,multi_format_client,resilience,prompts}.py`, `core/ocr_quality/*.py`, `core/transcription/*.py`, `core/lexicon/*.py`, `core/glossary_library/*.py`, `core/glossary_sources/*.py`, `core/tree_export.py`, `core/document_exporters/base_exporter.py`, `core/docx_{,tree_}writer.py`, `core/html_writer.py`, `core/block_tree.py`, `core/pdf/{rasterizer,embedder,handler}.py`, `core/grounded/*.py`, `core/postprocess.py`, `core/preprocessing.py`, `core/handwriting_preprocessor.py`, `core/routing.py`, `core/evaluation.py`, `core/translation_config.py`, `core/translation.py`
- **API (47 files):** all `api/routers/*.py` (15), all `api/services/*.py` (25), all `api/schemas/*.py` (3), `api/plugin/*.py` (14), `api/__init__.py`, `api/tasks.py`
- **Frontend (~65 files):** 7 views + 2 modals + 12 UI primitives + 5 stores + 3 service files + 2 API modules + 16 test files + `App.svelte`
- **Tooling:** `scripts/*.py` (25), `tests/*.py` (140+), `tests/conftest.py`, `.github/workflows/*.yml` (nightly.yml + test.yml), `pyproject.toml`, `Dockerfile`, `compose.yaml`, `install.{bat,ps1,sh}`, `start_app.vbs`, `Makefile`, `.pre-commit-config.yaml`, `tests/openapi.json`, `examples/*.{pdf,png,avif}` (7)
- **Companion docs:** `audits/2026-08-17-comprehensive-5-domain-audit.md`, `audits/2026-08-18-comprehensive-5-domain-audit.md`, `audits/2026-08-19-tech-debt-remediation-plan.md`, `audits/2026-08-19-secondary-validation-pass.md`, `audits/2026-08-19-phase-6-plugin-migration-design.md`, `AGENTS.md`, `ARCHITECTURE.md`, `frontend/DESIGN_SYSTEM.md`, `frontend/QA_REPORT.md`

---

_Last updated: 2026-08-20 — awaiting user "go" on Phase A_
