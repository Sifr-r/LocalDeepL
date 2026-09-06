# OmniScribe — Outstanding Work

**Consolidated:** 2026-08-31  
**Updated:** 2026-09-05 (Five-lens audit + remediation plan landed; Phases 0–3 in flight)  
**Sources:** `docs/audits/2026-08-30-pedantic-review.md`, the deferred Medium/Low backlog of the 2026-08-29 five-domain audit, the 2026-09-04 [Five-Lens Audit](audits/2026-09-04-five-lens-audit.md) and [Remediation Plan](audits/2026-09-04-remediation-plan.md), and Phase C follow-ups.

All completed items (audit-remediation sprints 1–6, Phase C plugin slices 1–3, and Waves 1–14) have been closed and verified. Historical records are preserved in git history (`git log --grep="Wave"`).

## Current focus (2026-09-05)

Driving work in flight, in priority order. Each item links to the
remediation plan section that defines the scope, acceptance criteria,
and effort.

- **Phase 0 — Stop the bleeding** ✅ (closed 2026-09-05). Empty
  `REDIS_PASSWORD` in `.env.example`; `ALLOW_SSRF_LOCAL` defaulted to
  `false` in both `.env.example` and `compose.yaml`.
- **Phase 1 — Truth in documentation** ✅ (closed 2026-09-05). Reconciled
  `SECURITY.md`, this file, `README.md` (moved from `docs/README.md`),
  `client/README.md`, `Makefile`, `test.yml`, `nightly.yml`,
  `AGENTS.md`, and `ARCHITECTURE.md` against shipped code.
- **Phase 2 — First-run affordances** ✅ (closed 2026-09-05). Added
  `TROUBLESHOOTING.md`, `CONTRIBUTING.md`, issue templates, PR template,
  SQLite default state backend, and `make doctor` remediation hints.
- **Phase 3 — Quick-win code cleanups** ✅ (closed 2026-09-05). Addressed
  high-leverage code debt: OCR service decomposed into focused submodules,
  `JobStatusResponse.started_at` persisted, `InMemoryJobQueue` exception
  swallowing fixed, `load_dotenv()` removed from `create_app()`, and
  `HybridEngine` failure state resynced.
- **Phase 4 — End-user install path** ✅ (closed 2026-09-05, with bundle
  deferred to v0.3+). **v0.2.0 ships the source install as the supported
  end-user path** (12–16 steps, now covered by Phase 2's
  `TROUBLESHOOTING.md` and `make doctor` hints). The PyInstaller bundle
  per [RFC 001 Option A](rfcs/2026-09-end-user-install.md) is **deferred to
  v0.3+** because PyInstaller's static analyzer refuses to bundle `anyio`
  (14 build attempts documented in
  [`docs/deployment/windows-bundle.md`](deployment/windows-bundle.md)
  §"Known build issue"). Bundle infrastructure kept in tree
  (`omniscribe_server.spec`, `scripts/build_windows.py`,
  `scripts/run_server.py`, `hooks/hook-anyio.py`); the smoke test gate
  (`/api/health -> 200`) is unchanged when the build is unblocked. The
  full v0.2.0 release report is at
  [docs/RELEASE-NOTES-v0.2.0.md](RELEASE-NOTES-v0.2.0.md).
- **Phase 5 — Test hardening** ✅ (closed 2026-09-05). Added 5 property-based
  fuzzing test suites with `hypothesis` (`json_parse`, `prompt_safety`, `page_range`,
  `whitespace`, `filters`), direct unit & property tests for `core/translate/workflow.py`,
  and canonical PDF fixture re-homing in `tests/fixtures/pdfs/`.
- **Phase 6 — Long-tail** ✅ (closed 2026-09-05, updated 2026-09-06). Cleaned deprecated CORS aliases (D10),
  hoisted `_DEFAULTS` in processor (D12), single-pass raw_decode `extract_json` (D11),
  hardened token masking (S8), exact-key sensitive logging redaction (S10),
  resolved Q8 (under-tested modules wave: 178+ tests covering transcription engines, prompted grounded OCR, glossary HTTP fetch/SSRF, library routes, and encoding/XLIFF),
  resolved Q10 (merged `tests/ops/` into `tests/scripts/`), and closed P13 as
  N/A (policy documented in `docs/SECURITY.md`: sensitive reports request
  fingerprint out-of-band; no static PGP key published to avoid unmanaged key rot).

---

## 1. Pedantic Review — Open Medium-Priority Findings

*All items in this section have been resolved:*
- **2.6** `plugins/ocr/service.py` — Prune is the single source of truth for bounding per-job maps (closed in Wave 9).
- **2.8** `plugins/ocr/service.py` / `_OcrPayload` — Replaced in-memory upload bytes with streaming pipeline and per-job spooling (closed in Wave 9 & Wave 12).
- **3.6** `JobStatusResponse` — Reconciled documentation on SSE-delivered token vs polled-result design (closed in Wave 9).

---

## 2. Harness & Plugin Seams (Post-Phase-C)

*All items in this section have been resolved:*
- **9.8** `plugins/glossary/plugin.py` — Evaluated lazy initialization and reload handling (closed in Wave 9).
- **9.9** `plugins/translate/service.py` — Aligned empty-text semantics with route contract (closed in Wave 9 & Wave 13).
- **9.10** `plugins/translate/service.py` — Decoupled `TRANSLATION_SYSTEM_MESSAGE` via stable export from `omniscribe.core.translate` (closed in Wave 13).
- **9.11** `plugins/transcribe/service.py` — Flattened 4-step config fallback with helper (closed in Wave 9).
- **9.12** `plugins/transcribe/service.py` — Co-located `unpack_transcribe_options` helper next to `TranscribeRequest` schema (closed in Wave 13).
- **9.13** `plugins/transcribe/service.py` — Narrowed unused imports block (closed in Wave 9).
- **9.17** Audited new route modules for uniform envelope, union return types, and SSRF validation (closed in Wave 9 & Wave 12).

---

## 3. Test Gaps

*All items in this section have been resolved:*
- **5.1** Added test for `_OcrPayload` round-trip and eviction lookup miss (closed in Wave 9).
- **5.3** Python optimization (`-O`) assertion regression test covered (closed in Wave 7).
- **5.4** Added 200-event rapid burst test pinning per-job replay deque (closed in Wave 9).
- **5.5** Covered `plugins/jobs.py` paginated shutdown under 1500 queued jobs (closed in Wave 9).
- **5.7** Added frontend Flutter test asserting strict discrimination between `cancelled` and `error` status (closed in Wave 13).

---

## 4. Five-Domain Audit Deferred Backlog

*All actionable items in this section have been resolved across Waves 8–14:*

### Domain 1 — Core Pipeline (CLOSED)
- Refine stage decodes target pages on-demand using run-scoped cache (Wave 13).
- Fresh unclosed `AsyncOpenAI` client lifecycle resolved with lazy initialization and ephemeral probes (Wave 12).
- Grounded `ensure_model_loaded` uses ephemeral client closed in `finally` (Wave 12).
- First-use model loads offloaded to thread pool (Wave 8).
- Embedder batches page rasterization in bounded chunks of 16 (Wave 13) and applies `garbage=3, deflate=True` stream compression (Wave 14).
- Cancelled grounded tasks properly awaited and cleaned up (Wave 12).
- $O(1)$ block lookup in `grounded.py` repair loop (Wave 13).
- Single-pass image decode in layout stage (Wave 13).
- Dead `input_path` parameter removed (Wave 14).
- Defensive copying on `trust_images_dict` (Wave 14).
- Explicit `last_exc` invariants for `-O` execution (Wave 14).

### Domain 2 — API & Security (CLOSED)
- Byte-budget streaming upload parsing and size enforcement (Wave 12).
- Full ASGI Middleware Suite restored: Bearer Auth (`auth.py`), Rate Limiting (`rate_limit.py`), and Upload Size Limiting (`upload_limit.py`) (Waves 11, 13, 14).
- Startup validation in `create_app()` prevents uvicorn direct-bind bypass of non-loopback and placeholder tokens (Wave 13).
- `DELETE /api/jobs` protected with `confirm=true` requirement to prevent accidental wipes (Wave 14).
- WebSocket Origin validation against `cors_origins` (Wave 13).
- Constant-time token comparisons (`secrets.compare_digest`) across backends and progress channels (Wave 13).
- Provider API keys accepted via `X-Provider-Api-Key` and `Authorization` headers (Wave 13).
- `CircuitOpenError` mapped to HTTP 503 with standard `Retry-After` header (Wave 14).
- Sanitized `ValueError` detail responses (Wave 13).
- POSIX `0o700` permission enforcement on state directories (Wave 14).

### Domain 3 — Frontend / Flutter Client (CLOSED)
- Workstation async submit fallback polls `getJobStatus` on unexpected WebSocket disconnection and downloads results (Wave 14).
- Result token passed exclusively via Authorization header (Wave 13).
- Real `ServerHealthNotifier.checkHealth` pinging `/api/health` replaces simulated badge (Wave 12).
- File download persists to disk via `FilePicker.platform.saveFile` (Wave 13).
- Dead API constants removed (Wave 13).
- `isCancelled` status discrimination tested and verified (Wave 13).

### Domain 4 — Testing & QA (CLOSED)
- Dedicated unit tests for `page_preprocess.py` (`tests/core/imaging/test_page_preprocess.py`) (Wave 14).
- Dedicated unit tests for `routing.py` (`tests/core/ocr_quality/test_routing.py`) (Wave 14).
- Dedicated unit tests for `local_engine.py` (`tests/core/transcription/test_transcription.py`) (Wave 13).
- Dedicated unit tests for `embedder.py` (`tests/core/pdf/test_embedder.py`) (Wave 14).
- Dedicated unit tests for `config.py` (`tests/test_config.py`) (Wave 14).
- Dedicated unit tests for ASGI middleware triad (`tests/middleware/`) (Waves 11, 13, 14).
- OpenAPI snapshot drift contract test passes (Wave 13 & 14).
- Merged single-test `tests/ops/` directory into `tests/scripts/` (Q10 resolved).
- Under-tested modules wave (Q8 resolved):
  - Local and API audio transcription engine tests (`tests/core/transcription/test_transcription_engines.py`)
  - Grounded OCR prompt builder, chunking, coordinate clamping, reading order, and JSON repair tests (`tests/core/grounded/test_prompted_grounded_ocr.py`)
  - Glossary HTTP fetch, redirect limits, SSRF private IP blocking, body size guards (`tests/plugins/test_glossary_http_fetch.py`)
  - Glossary library routes, source toggle/reorder, query pagination, and LanceDB 503 fallback (`tests/routers/test_glossary_library_routes.py`)
  - Glossary source encoding auto-detection and XLIFF 1.2/2.0 parsing (`tests/core/glossary_sources/test_encoding_and_xliff.py`)

### Domain 5 — DevOps & Config (CLOSED)
- `.env.example` provides working default `REDIS_PASSWORD` allowing `cp .env.example .env && docker compose up` without failure (Wave 14).
- `compose.yaml` aligned and verified (Wave 14).
- Cleaned up stale `# force_run` comment in `nightly.yml` (Wave 14).
- Pinned toolchain versions and security workflows aligned (Wave 14).
- Security contact PGP policy documented in `docs/SECURITY.md` (sensitive reports request fingerprint out-of-band; static PGP key omitted to prevent unmanaged key rot; P13 closed / N/A).

---

## 5. Phase C Architecture Follow-ups

- **Fourth-Producer Registry:** If a fourth runner producer appears beyond OCR (`JobRunner`), Translation (`TranslationJobRunner`), and Glossary (`GlossaryJobRunner`), generalize `JobQueue` dispatch to an explicit registry.
- **Transcribe Spec Drift (Informational):** Text artifacts are stored as page-dict JSON (`application/json`), not literal `text/plain`; response `job_id` is a synthetic `job-<hex>` used as artifact owner for pruning. Documented in contract.
- **Flutter Client Paired Changes:** Pedantic finding 2.2 (`AsyncOpenAI` client lifecycle) requires paired client verification when scheduled.

---

## 6. Deferred Architectural Capabilities

High-level capabilities deferred during the harness rebuild and not yet
shipped. Each entry points at the unblocker.

> **Removed 2026-09-05:** the ASGI Middleware Suite
> (bearer auth + rate limit + upload size) was previously listed here.
> It shipped in Waves 11, 13, and 14 — see §4 Domain 2 closure record
> and [SECURITY.md](SECURITY.md) §Security Features for the current
> contract.

1. **Redis State Backend:** Complete `RedisStateBackend` for distributed deployments (`OMNISCRIBE_STATE_BACKEND=redis` currently crashes at plugin apply).
2. **Model Pre-flight Route:** Formal API endpoint for VLM pre-flight verification against silent fallback. `ensure_model_loaded()` exists in `core/ocr/processor.py`; the public route is unbuilt.
3. **Full Regression Datasets (`slow_dataset`):** `scripts/fetch_datasets.py` execution once upstream licenses clear for OCR-Quality and KIE-HVQA benchmarks.

---

## 7. Low-Priority Naming, API & Style Smells

### §4 Naming & API Smells
- **4.1** `cors_origins_raw: str | None` + property — prefer typed list field.
- **4.2** `_disable_negative_rate_limit` name is misleading; rename/document.
- **4.3** `_inherit_llm_model_for_grounded` compares magic model string; use sentinel.
- **4.4** Retry loop's `last_exc` invariant is implicit, not asserted.
- **4.5** `TrOCREngine` TYPE_CHECKING-only but wired in production; document requirement.
- **4.7** `WhitespaceRecallOptions.from_env` vs `TextLayerRecallOptions.from_env`; shared base.
- **4.8** `_RepairEngineHost` Protocol documents a contract the file then breaks.
- **4.9** `input_path: str = ""` default is dead code.
- **4.10** `state_backend.py:200-206` circular-import workaround is fragile; split types module.
- **4.11** Four names for two concepts across `jobs.py`/`state_backend.py` (`artifact_id` vs `result_artifact_id`).
- **4.12** `_PYTHON_BUG_EXCEPTION_TYPES` treats `ValueError` as non-retryable; conflates bug vs garbage.
- **4.13** `CircuitOpenError.retry_after` never surfaced as a `Retry-After` header.
- **4.14** `load_dotenv()` at module level in `processor.py` and `server.py`; move to entry point.
- **4.15** `cli/migrate_lexicon.py` ships despite CLI deprecation note; check `[project.scripts]`.
- **4.16** `_MODELS_WITHOUT_SYSTEM_ROLE` substring matching catches fine-tunes; document intent.
- **4.17** Inner `import base64` in TrOCR arbitration belongs at top.
- **4.18** SSE loop's clear-on-wake `asyncio.Event` flaps — dropped/interleaved frames; use a deque.
- **4.19** `max_buffered_jobs` caps three structures with two eviction functions; fold.
- **4.20** `update_config` mutates shared `RuntimeSettings` mid-flight; document "applies to subsequent requests".
- **4.21** `_DENSE_MODE_ALIASES` on/off→always/never mapping is hidden; document in contract.
- **4.23** `_QUEUE_STATUS_TO_HTTP` should live next to the schema.
- **4.25** `PRAGMA journal_mode=WAL` set but never verified.
- **4.26** Embedder docstrings reference a 470-LOC file that no longer exists; trim.
- **4.27** `env_int` logs a warning on bad input; other helpers don't; align.
- **4.28** `env_list_csv` vs `env_str` empty-value semantics differ.
- **4.29** `extract_json` walks every `{`/`[` — O(n²) on big responses; use single `raw_decode`.
- **4.30** `whitespace.py` constants block carries 15 lines of audit history; move to docs.
- **4.31** Loader `row = replace(row, ...)` rebind shadows traceback context.
- **4.32** Env-override typos surface as opaque Pydantic ValidationErrors; coerce via schema earlier.
- **4.34** Text_layer `close()` not re-entrant (fitz is idempotent so safe).
- **4.36** `_overlaps_existing` is O(n²) per page on pathological box counts.
- **4.37** HybridEngine re-injects deps into long-lived stages every `execute()`; constructor args decorative.
- **4.38** `_reset_run_state` resets only two of the stage states; document or full-reset.
- **4.39** `_decoded_cache` integer keys could collide across runs; use `(run_id, page)` keys.
- **4.40** `trust_images_dict` aliases `images_dict`; a future mutation leaks across.
- **4.41** `_DEFAULTS` dict rebuilt per attribute access; hoist.
- **4.42** Exponential backoff cumulative sleep budget undocumented.
- **4.43** Context-length error message is LM Studio-specific; generalize or branch.
- **4.45** `Context.__init__` pre-allocates nine collections (negligible cost, signal only).

### §6 Style Nits
- **6.3** `artifact_cleanup_interval_s` vs `cleanup_interval_seconds` naming/units drift.
- **6.4** HybridEngine's 9-kwarg `__init__` is a permanent API surface.
- **6.6** `_KERNEL_W_RANGE` tuples; named MIN/MAX constants would read better.
- **6.7** Whitespace candidates carry an unused score element; misleading annotation.
- **6.8** Triple-`or` candidate filter; three named predicates would scan better.
- **6.9** `_resolve_unicode_chain` is 70 lines; split.
- **6.13** `hybrid_repair.py` `concurrency` param is a documented no-op.
- **6.14** Default-arg closure binding; prefer `functools.partial`.
- **6.15** SQLite path-traversal check rejects deliberate sibling-dir layouts.
- **6.16** `range(self.max_retries + 1)` cryptic; make 1-based.
- **6.17** Post-loop error translation duplicates `is_transient_error` logic.
- **6.18** `_parse_env_line` is 50 lines of bespoke parsing; document or use stdlib.
- **6.19** `update_dotenv` round-trip normalizes CRLF to LF.
- **6.20** `update_dotenv` unconditionally sets every key into `os.environ`.
- **6.26** Memory backend caps blobs at 256 MB; sqlite has no cap; clarify intent.
- **6.30** `new_doc.save` exposes no `garbage`/compression kwargs.
- **6.31** Embedder `page_nums` branching has a dead conditional; unify.
- **6.33** `_OcrPayload` IR lives in the HTTP layer; pipeline can't enqueue without it.
- **6.34** Grounded engine duplicates hybrid's execution path; lockstep-change risk.
- **6.35** `AsyncSubmitResponse.status` is `str`, should use the job-status Literal.
- **6.38** `_split_processors` only handles comma-joined form fields; repeated keys drop.
- **6.39** `preprocessing_enabled` property couples HTTP naming to behavior; move to bridge.
- **6.40** SQLite `_job_from_row` uses positional access; use `sqlite3.Row`.
- **6.42** `cursor.rowcount if cursor.rowcount >= 0 else 0` repeated 4×; extract.
- **6.43** `candidates_dropped` counts per candidate, log reads per page; document.
- **6.45** `trust_images_dict` param on `_finalize` is dead; delete.
- **6.46** `select_dense_pages` union `str | DenseMode` is historical; narrow.
- **6.47** `_apply_adaptive_threshold` via `to_thread` — function not in file; locate/document.
- **6.48** Tesseract dual-engine contract undocumented.
- **6.49** `self_correction` second VLM call path review notes.
- **6.50** F1.9 comment block is 23 lines; trim to a one-liner + pointer.
- **6.51** `import statistics` mid-module.
- **6.52** Every whitespace constant carries a multi-line audit comment; move history to docs.
- **6.53** Substring matching over a frozenset; list + early exit.
- **6.55** Two `PROMPT_VERSION` constants share a value by coincidence; hazard.
- **6.56** Chat client re-encodes JPEG to PNG (+30% payload); use `multi_format_client`.
- **6.57** Backoff formula note (informational).
- **6.63/6.64/6.65/6.66** Hybrid engine re-injection wrappers do nothing; call stages directly.
- **6.68** `_build_document_result` helper visibility note.
- **6.69** `completed_box` mutable-list pattern; `nonlocal` would be cleaner.
- **6.70** Repair loop vs OCR loop not coordinated; possible double re-OCR.
- **6.71** Frozen dataclasses containing unhashable fields break the hashable promise.
- **6.74** `start`/`shutdown` idempotency (verified OK; informational).
- **6.75** Queue worker swallows runner exceptions; document trade-off.
- **6.76** `_mark_cancelled` discard semantics (OK; informational).
- **6.77** Cancelling an already-terminal job suppresses `JobCancelled`; UI may spin.
- **6.78** Progress `frame_cap` is soft when done-callbacks never fire.
- **6.79** `broadcast` returns submissions, not successes; document.
- **6.81** Extensionless upload filenames fall back to `.pdf`; misleading.
- **6.82** Defensive `assert self._progress is not None` after outer check.
- **6.83** Sync path gets no cancel check (`job_id=""` short-circuit).
- **6.84/6.85** `started_at` always None; populate or document.
- **6.86** Masked `api_key == "******"` skip contract is subtle; document.
- **6.87** `update_config` writes even unchanged values; use `model_copy(update=...)`.
- **6.88** `OCRRequest` is 18 fields / 4 validators; consider nested config.
- **6.89** `_coerce_bool` field list duplicates declarations.
- **6.91** Recall `from_env` enable-default semantics (OK; informational).
- **6.93** Text_layer `close` is sync, forcing `to_thread`; document.
- **6.94** Text-layer line grouping order note (final re-sort makes it OK).
- **6.95–6.101** Loader parse/merge/validate behaviors (verified OK; informational).\n