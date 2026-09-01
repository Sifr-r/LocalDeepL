# OmniScribe — Outstanding Work

**Consolidated:** 2026-08-31  
**Updated:** 2026-09-01 (Cleaned: active open work only)  
**Sources:** `docs/audits/2026-08-30-pedantic-review.md`, the deferred Medium/Low backlog of the 2026-08-29 five-domain audit, and Phase C follow-ups.

All completed items (audit-remediation sprints 1–6, Phase C plugin slices 1–3, and Waves 1–7) have been closed and verified. Historical records are preserved in git history (`git log --grep="Wave"`).

---

## 1. Pedantic Review — Open Medium-Priority Findings

- **2.6** `plugins/ocr/service.py:189-194` — `_submission_to_job` eviction (insertion-order trim on every submit) duplicates the `prune` eviction policy with conflicting timing.
- **2.8** `plugins/ocr/service.py` / `_OcrPayload` — Full upload bytes are held in `_submission_to_job` until `run_job` consumes them; the memory backend holds result PDF plus original upload in heap for the whole job lifetime. Needs a streaming pipeline.
- **3.6** `JobStatusResponse` security note says clients get the token via SSE, while `AGENTS.md` says the result URL is a polled endpoint. Reconcile doc.

---

## 2. Harness & Plugin Seams (Post-Phase-C)

- **9.8** `plugins/glossary/plugin.py:31-34` — `LexiconProvider` is created per boot; the service captures the bound `provider.get`. Review lazy initialization and reload handling.
- **9.9** `plugins/translate/service.py:100-120` — Sync translation tolerates `request.text=""` by falling back to the artifact, while `extract` (`plugins/documents/service.py:71`) returns 400 for empty text. Align empty-text semantics.
- **9.10** `plugins/translate/service.py:36-41` — The plugin imports `TRANSLATION_SYSTEM_MESSAGE` from `core.translate.nodes`, sharing a constant across the plugin/core boundary. Decouple or re-export via a stable core boundary.
- **9.11** `plugins/transcribe/service.py:60-77` — `str(request.api_key or config.get(...)) or None` is a 4-step value-or-config-or-default-or-None funnel. Flatten with a helper.
- **9.12** `plugins/transcribe/service.py:80-100` — The route unpacks five kwargs to match the service signature; move the unpack helper next to the schema to stay in sync.
- **9.13** `plugins/transcribe/service.py:27-33` — The 7-line import block is `noqa: F401` wholesale; narrow the noqa or move unused names to `TYPE_CHECKING`.
- **9.17** `plugins/translate/routes.py`, `plugins/transcribe/routes.py`, `plugins/glossary/routes.py` — Audit the three new route modules for uniform `{"error","detail"}` envelope, `response_model=None` union pattern, and SSRF guards on caller-supplied `api_base`.

---

## 3. Test Gaps

- **5.1** No test for the `_OcrPayload` round-trip when the `submission_id` lookup misses (evicted by the 500-deep map) — service silently uses `job_id=""`.
- **5.3** A Python optimization (`-O`) regression test around `core/recall/text_layer.py` to assert assert statements are not relied upon for core control flow.
- **5.4** No test exercises the SSE event-flap in `plugins/ocr/plugin.py:199` (see 4.18).
- **5.5** No test covers `plugins/jobs.py` shutdown with >1000 queued jobs (1.6 fix pagination loop).
- **5.7** No frontend Flutter test distinguishes `cancelled` from `error` status.

---

## 4. Five-Domain Audit Deferred Backlog

Candidate backlog from the 2026-08-29 audit. Verify file:line before implementation as code has shifted.

### Domain 1 — Core Pipeline
- **Medium:** Refine stage decodes all target pages at once (reuse `_decoded_cache`) · Fresh unclosed `AsyncOpenAI` per OCR request (cache per `api_base` or `aclose()`) · Throwaway unclosed client per grounded run (`ensure_model_loaded`) · First-use HF model loads on the event loop in local_engine/trocr/nllb (use `asyncio.to_thread`) · Process-wide breaker registry shares one `asyncio.Lock` across loops (use `threading.Lock`) · Embedder pre-rasterizes all pages before serial construction (interleave in bounded batches) · Cancelled grounded tasks never awaited in finally (gather with `return_exceptions=True`).
- **Low:** One PIL page shared across concurrent crop threads (document or lock) · Triple image decode per page in layout stage · O(repaired × blocks) identity scan in `grounded.py` · Lexicon fallback/listing loads entire tables (partially addressed by LanceDB pushdown) · NLLB deprecated `get_event_loop()` + no concurrency guard.

### Domain 2 — API & Security
- **Medium:** `_parse_upload` buffers the whole upload before the size check (byte-budget streaming; TTL-expire bookkeeping) · Default cordis patch path lives in shared temp dir and patch `use:` executes arbitrary `module:attr` (mode-0700 default; log pickup) · Non-loopback/placeholder-token guards live only in CLI `main()`, bypassed by raw `uvicorn omniscribe.server:app` (move into `create_app()`).
- **Low:** `/api/progress/cancel/{channel_id}` requires no session token · `DELETE /api/jobs` unauthenticated wipe · No Origin check on WS handshake + stale `?token=` comment · Provider `api_key` as query param (leaks to logs) · Artifact token compared with `!=` not `compare_digest` · `ValueError` text echoed to clients · SQLite DB/artifacts default into world-readable temp dir · Env overrides are trust-equivalent to editing `cordis.yml` (document).

### Domain 3 — Frontend / Flutter Client
- **Medium:** Workstation relies solely on WS frames after async submit (poll status on WS close; fetch result) · Result token duplicated into query param + header (header only) · Server health badge is a simulation (wire to `/api/health`) · A11y coverage is 2 files vs ~30 screens; client-tests job missing from `AGENTS.md` gate table.
- **Low:** Job "Download" discards fetched bytes · Per-call `wsUrl` ignored on reconnect · Dead `/health` + `/api/ready` constants · Benign job status-schema drift (add round-trip contract test against `tests/openapi.json`).
- **Flutter Backlog:** Full axe/a11y regression coverage, complete 48 dp touch-target sweep, all keyboard shortcut bindings.

### Domain 4 — Testing & QA
- **Medium:** Coverage gate only in CI flags, not local addopts · Marker drift (`slow_dataset`) between CI/Makefile/nightly · Wall-clock budget meta-test is a flake candidate · `importlib.reload` leaks state mid-suite · Untested modules (`page_preprocess.py`, `local_engine.py`, `ocr_quality/routing.py`) · Fixed-sleep negative assertion in `test_jobs_plugin.py`.
- **Low:** Nightly stale `force_run` comment · Semgrep image pinned by mutable tag · CI runs `mypy src tests` but local gate runs `mypy src`.

### Domain 5 — DevOps & Config
- **Medium:** `compose.yaml` aborts without `REDIS_PASSWORD` though `.env.example` claims a generator one-liner · Image Python 3.14 tested nowhere in fast CI (CI tests 3.11–3.13) · `DEPLOYMENT.md` profile 3 pulls a GHCR image no workflow publishes · No `HF_HOME` for Surya's model download in runtime container stage · `start_app.vbs` `f.Close` on an FSO File aborts boot when log exceeds 10 MiB.
- **Low:** Redis password visible in process argv · Plaintext `redis-password.txt` (acceptable for single-user desktop) · uv tarball SHA-256 verified only in `install.ps1` · Pre-commit uv hook rev vs pinned uv drift · No dependency-review gate.

---

## 5. Phase C Architecture Follow-ups

- **Fourth-Producer Registry:** If a fourth runner producer appears beyond OCR (`JobRunner`), Translation (`TranslationJobRunner`), and Glossary (`GlossaryJobRunner`), generalize `JobQueue` dispatch to an explicit registry.
- **Transcribe Spec Drift (Informational):** Text artifacts are stored as page-dict JSON (`application/json`), not literal `text/plain`; response `job_id` is a synthetic `job-<hex>` used as artifact owner for pruning. Documented in contract.
- **Flutter Client Paired Changes:** Pedantic finding 2.2 (`AsyncOpenAI` client lifecycle) requires paired client verification when scheduled.

---

## 6. Deferred Architectural Capabilities

High-level capabilities documented in `AGENTS.md` deferred during the harness rebuild:

1. **ASGI Middleware Suite:** Authentication middleware (`OMNISCRIBE_AUTH_TOKEN`), Rate-limiting middleware, and Upload-size enforcement middleware.
2. **Redis State Backend:** Complete `RedisStateBackend` for distributed deployments (`OMNISCRIBE_STATE_BACKEND=redis` currently crashes at plugin apply).
3. **Model Pre-flight Route:** Formal API endpoint for VLM pre-flight verification against silent fallback.
4. **Full Regression Datasets (`slow_dataset`):** `scripts/fetch_datasets.py` execution once upstream licenses clear for OCR-Quality and KIE-HVQA benchmarks.

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