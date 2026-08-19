# Changelog

All notable changes to OmniScribe are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **LanceDB-backed lexicon store (replaces JSON + ChromaDB)** — the
  canonical glossary / translation lexicon is now a single embedded
  columnar vector database (`omniscribe.core.lexicon.LanceDBLexiconStore`)
  with native hybrid (vector + SQL filter) queries. Replaces the prior
  two-system pair of `glossary_library/library.json` (JSON-on-disk) +
  `chroma_db/lanes_lexicon` (ChromaDB PersistentClient). The new
  `LexiconStore` Protocol is the single read/write surface; legacy
  callers route through `GlossaryLibraryAdapter`. Translation lookup
  is now a one-query hybrid (similar terms, in this language pair, in
  this domain, in this user's enabled glossaries) instead of a
  ChromaDB semantic search + a JSON side-lookup. Spec:
  `docs/lexicon-migration-spec.md`.

- **`omniscribe-migrate-lexicon` CLI** — explicit one-shot migration
  script for users who prefer a manual upgrade path. Supports
  `--dry-run` (plan without writing), `--verify-only` (read-only
  check of an existing migration), and `--artifact-dir <path>`. The
  server also auto-migrates on first run after the upgrade
  (fail-open — a broken migration never blocks boot; the user can
  retry with the explicit CLI).

- **Optional `source_lang` / `target_lang` on `TranslationState`** —
  the LangGraph translation flow now carries language pair hints
  through to the lexicon query so a glossary scoped to `en→fr` does
  not bleed into a `de→es` request. Populated by the translation
  route when known (request field, OCR document metadata, or
  inference); missing is fine — the store just skips the filter.

- **Whitespace recall booster (default ON)** — the hybrid pipeline now
  runs a secondary whitespace-masking discovery pass
  (`core/text_recall.py`) after Surya layout detection: binarize +
  invert, horizontal dilation, connected-component filtering, dedup
  against Surya boxes. Recovered line boxes join detection before
  dense selection, OCR, and DP alignment. Disable per process with
  `OMNISCRIBE_WHITESPACE_RECALL=0` (also `false`/`no`/`off`).
  Requires the `preprocessing` extra (`opencv-python-headless`);
  without it the pass logs one warning and stays inert.

- **`omniscribe-migrate-lexicon` exit-code fix** — the CLI no longer
  returns exit code 2 for a valid empty `lexicon.lance` after
  `--verify-only` (a fresh install or one with no glossaries is a
  successful verification, not a problem). Exit 2 is now reserved for
  `--strict` mode when the live store is empty but a backup manifest
  reports glossaries. Operators scripting `if
  omniscribe-migrate-lexicon --verify-only; then …` no longer see
  false-positive failures.

- **Plugin context infrastructure (Cordis-style container)** —
  `src/omniscribe/api/plugin/` introduces a Protocol-based plugin
  container with five seams (`JobQueue`, `SessionLog`, `ConfigStore`,
  `ProgressService`, `TextArtifactStore`), a runtime `get_<name>()`
  helper, a "look up by Protocol, fall back to singleton" migration
  window, and dual-write projections for `JobHistory` and the artifact
  stores. `OMNISCRIBE_PLUGIN_CONTEXT=1` enables it (default off; import-
  time-only toggle, no runtime flip). Two of the five seams are wired at
  boot (`JobQueue` → `local`, `SessionLog` → `memory`); the other three
  fall through to the legacy `api/routers/state.py` singletons by
  design. See `AGENTS.md` §"Plugin Context Migration Status" for the
  current state.

- **`document_exporters/` package** — the `core/document_exporters/`
  package is a thin `DocumentExportProtocol` + `BaseDocumentExporter`
  ABC. The three real exporters (DOCX, tree-DOCX, HTML) are
  co-located with the writers they wrap
  (`core/docx_writer.py`, `core/docx_tree_writer.py`,
  `core/html_writer.py`); the package ships only the abstraction.

- **A11y test additions (frontend)** — `frontend/src/__tests__/a11y.test.ts`
  plus the new `frontend/src/lib/utils/download.ts` / `__tests__/download.test.ts`
  cover the Svelte 5 component layer for accessible-name regressions
  and the new browser download lifecycle. `vitest-axe` /
  `@axe-core/playwright` integration is still pending (tracked
  separately).

- **Celery task unit tests** — `tests/test_distributed_ocr_tasks.py`
  covers the Celery worker side of the OCR pipeline for crash-safety
  and queue draining. Multi-worker / crash-safe dispatch remains a
  follow-up.

- **Document exporter tests** — `tests/test_document_exporters.py`
  pins the new `document_exporters/` abstraction's contract.

- **Phase-2 remediation tests** — `tests/test_phase2_remediations.py`
  bundles 7 fixes from the 2026-08-17 audit's Domain 1 / Domain 2
  close-out into one regression file (splitting per-finding is a
  follow-up; see `audits/2026-08-19-secondary-validation-pass.md` §F26).

- **Misc 2026-08-17 → 2026-08-19** — `tests/test_security_middleware.py`,
  `tests/test_token_deprecation.py`,
  `frontend/src/__tests__/auditMediumD3.test.ts`, and the
  `_PinnedIPTransport` regression test (D2-06 partial close-out) all
  landed in this window.

### Changed

- **`[memory]` extra renamed to `[lexicon]`** — the `chromadb` dependency
  is removed; the new extra installs `lancedb + pyarrow + pandas +
  sentence-transformers` instead. The `[memory]` name is kept as a
  one-release deprecation alias that installs the same set, so existing
  `omniscribe[memory]` users upgrade transparently. After this release
  the alias is dropped.

- **Install paths now include the `preprocessing` extra** —

- **Windows quick-start robustness (install.ps1 + start_app.vbs)** —
  the Windows one-click launcher no longer silently fails on
  re-launch. `start_app.vbs` now writes a timestamped log to
  `start_app.log` next to itself, pre-checks that `uv` is on PATH
  (pops a clear "log out so PATH updates" dialog if not),
  reuses the existing `redis-local-ocr` container via
  `docker start` or creates a new one with `--rm`, skips
  Redis + Celery gracefully if the Docker daemon is not
  reachable (async translation is the only thing that
  breaks), and polls `http://localhost:8000` until uvicorn
  actually responds (max 60 s) before opening the browser.
  `install.ps1` now wraps the `uv` installer in a try/catch,
  fails fast on `uv sync` errors via `$LASTEXITCODE`, runs
  `uv run python --version` to verify the venv is usable, and
  prints a clear "log out so PATH updates" callout at the end.
- **Speech transcription endpoint** — new
  `POST /api/transcribe` route plus
  `GET/POST /api/config/transcription` and
  `GET /api/models/transcription` for the transcription
  provider; gated by the new `OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN`
  env var (falls back to the global `OMNISCRIBE_AUTH_TOKEN`).
  Bypasses bearer auth on `/health`, `/healthz`, `/ready`,
  `/readyz` regardless of token configuration.
- **Quality repair loop (automatic low-confidence retry)** —
  engine-agnostic block-level quality retry in
  `core/workflows/repair.py` (`QualityRepairLoop` +
  `RepairOptions`). Blocks whose estimated confidence falls
  below the target are re-OCR'd crop-scoped (hybrid reuses
  refine's crop → `perform_ocr_on_crop` primitive; grounded
  goes through the backend's `ocr_crop`) up to
  `max_retries` times; a retry is accepted only while
  confidence strictly improves (stall guard), and any
  unexpected error fails open with the original text.
  `CircuitOpenError` is re-raised so the circuit breaker
  stays authoritative. Repair runs sequentially after block
  emission in both engines, before post-processing and
  embedding, so downstream stages always see the repaired
  text.
  - `OCRPipeline.run` accepts `repair_options=`; engines
    default **off** (`repair_options=None`) for in-process
    callers, while `/api/process` defaults **on** — upgrade
    note: expect up to `quality_max_retries` extra VLM
    passes per low-confidence block unless disabled.
  - Per-request form fields `quality_loop_enabled`,
    `quality_target` (0.5–1.0, default 0.98) and
    `quality_max_retries` (0–5, default 2) on
    `/api/process`; out-of-range values return 422.
  - Env seeds `OMNISCRIBE_QUALITY_LOOP` /
    `OMNISCRIBE_QUALITY_TARGET` /
    `OMNISCRIBE_QUALITY_MAX_RETRIES` (out-of-range values
    fall back to the defaults).
  - New WebSocket frames: `block_retry`, `block_revised` and
    `quality_summary` (job-level repaired-block count);
    progress accounting reuses the `refine` stage band.
- **System / user role split in OCR + translation prompts** —
  the canonical OLMOCR page prompt stays a pure user message
  (it was RL-trained on that exact string, so a system role
  would shift the distribution). For other code paths we now
  emit the role identity in a system message so the model
  doesn't have to compete with task content. New constants
  in `omniscribe.core.ocr.prompts`:
  - `OCR_SYSTEM_MESSAGE`, `HANDWRITING_OCR_SYSTEM_MESSAGE`,
    `DUAL_ENGINE_OCR_SYSTEM_MESSAGE`,
    `GROUNDED_OCR_SYSTEM_MESSAGE` — identity + diacritics
    emphasis + "no invent / emit empty on blank" guards.
  - `TRANSLATION_SYSTEM_MESSAGE` (sync + async paths) and
    `EVALUATION_SYSTEM_MESSAGE` (LLM-as-judge step) — both
    pin the "preserve URLs / identifiers / brand names"
    rule that local models otherwise helpfully mistranslate.
  - `EXTRACTION_SYSTEM_MESSAGE` — pins the
    "use `null` for missing fields, no markdown fences" rules
    so the model doesn't invent plausible values for absent
    fields.
  - `model_supports_system_role(model_name)` — the narrow
    OlmOCR exclusion list (see also the bug fix above).
  - `select_system_message(...)` and the new
    `_resolve_page_system` / `_resolve_crop_system` helpers
    on `OCRProcessor` are the single source of truth for
    "which system message goes with which call site".
  - `PROMPT_VERSION = "2026-08-15.v1"` per file. Bump on any
    user-visible prompt body change so log / runtime
    telemetry can correlate regressions with a known version.
  - The OlmOCR-2 canonical page-prompt body is **unchanged**
    and is locked by
    `test_olmocr_prompt_is_canonical` — the model was
    RL-trained on that exact string and any drift would cost
    OCR quality. The system-role plumbing is wired around
    it, never into it.
- **`scripts/debug_websocket_frames.py`** — Python WebSocket
  diagnostic that opens a real progress session, prints every
  incoming text frame as hex + UTF-8 + parse result, and
  writes a JSONL log. Use when a future regression looks
  like "mangled JSON in the browser console": run this
  alongside a real OCR job, and if every frame arrives with
  `parse_ok=true` the corruption is browser-side; if frames
  are already mangled on the wire, the issue is uvicorn /
  websockets.
- **Centralized LLM temperature constants**
  (`omniscribe.core.llm_temperatures`) — six named
  constants (`TEMPERATURE_OCR`, `TEMPERATURE_GROUNDED`,
  `TEMPERATURE_EXTRACTION`, `TEMPERATURE_EVALUATION`,
  `TEMPERATURE_TRANSLATION`,
  `TEMPERATURE_TRANSLATION_TREE`) replace the literal
  floats previously scattered across `core/ocr/processor.py`,
  `core/grounded/prompted.py`, `core/translation.py`,
  `core/translation_tree.py`, and `api/services/ai.py`. Each
  constant has a per-call-site rationale (e.g. OCR=0.1 lets
  the model escape degenerate-token traps without injecting
  real randomness; TRANSLATION_TREE=0.2 because the sliding
  window already constrains per-chunk variation). The
  values are deliberately **not** env-overridable — they
  are deployment shape, not user preference. Adding a new
  call site should pick an existing constant that matches
  the tolerance rather than invent a new float. (Issue 7)
- **Translation evaluator rubric + failure-mode block** —
  `build_evaluation_prompt` in `core/translation.py` now
  ships a 0–10 rubric (meaning preservation, terminology
  fidelity, fluency, format) and an explicit failure-mode
  checklist ("do not reward code-switching mid-sentence",
  "do not award a pass when brand names are silently
  translated") so the LLM-as-judge step stops rewarding the
  exact behaviors the rubric was supposed to penalize. (Issue 9)
- **Prompt input sanitization at the LLM boundary** —
  `sanitize_prompt_input` from `omniscribe.utils.prompt_safety`
  is now applied to every user-controlled text segment that
  reaches a prompt body: translation source chunks, structured
  extraction document text + custom prompt, evaluation
  source + translation, dual-engine / correction OCR draft
  text, and the translation tree chunk input. The helper
  neutralizes control characters and the prompt-injection
  markers most likely to make the model ignore the system
  message; it is applied at the prompt-builder level so a
  future call site can't forget. (Issue 11)
- **`_extract_prompt_and_image` simplified to a 2-tuple**
  — `core.ocr.multi_format_client._extract_prompt_and_image`
  dropped the legacy `(prompt, system_prompt, image)`
  3-tuple shape and the system-from-`messages` branch. The
  single source of truth for the system role is now the
  explicit `system_prompt` parameter on `call_llm` (routed
  through `model_supports_system_role` for OlmOCR family
  models). The previous dual path was not exercised by any
  production caller. (Issue 12)
- **SQLite-backed `StateBackend` (opt-in persistent
  state)** — `OMNISCRIBE_STATE_BACKEND=sqlite` activates
  :class:`SQLiteStateBackend` in
  `omniscribe.api.services.state_backend_sqlite`. Sits
  alongside the existing :class:`LocalStateBackend`
  (`memory`, the default — no behaviour change) and
  :class:`RedisStateBackend` (`redis`, requires a Redis
  server). The SQLite backend writes the three artifact
  tables (`omniscribe_artifact_text`,
  `omniscribe_artifact_meta`, `omniscribe_artifact_export`)
  and the jobs table (`omniscribe_jobs`) to a single
  SQLite file (default
  ``$OMNISCRIBE_ARTIFACT_DIR/omniscribe-state.db``;
  override with `OMNISCRIBE_STATE_DB_PATH`); artifact
  files themselves still live on disk in the existing
  artifact directory. WAL mode is enabled for concurrent
  readers + crash safety; the cap on
  `max_jobs` / `max_entries` is enforced via SQL on every
  write. `ProgressService`, `GlossaryLibrary`, and
  `OCRJobQueue` remain in-memory because they reference
  live WebSocket channels / RAG index state — see the
  module docstring for the "recovery boundary"
  explanation. The backend is the persistent opt-in for
  the local-first deployment shape; the Redis backend
  remains the answer when you need horizontal scaling
  across multiple uvicorn workers. New test module
  `tests/test_state_backend_sqlite.py` covers
  round-trip persistence, TTL/overflow enforcement, the
  per-instance monotonic counter for job ordering, and
  factory wiring.
- **`GET /api/jobs/{job_id}/result` — async OCR result
  download** — completes the existing async path. The
  route streams the searchable PDF produced by
  `POST /api/process/async` once the job reaches
  `status: "complete"`, gated by the per-job
  `text_artifact_token` from
  `GET /api/process/status/{job_id}` (constant-time
  compared via `secrets.compare_digest`; the token is
  passed via `?token=`, `Authorization: Bearer`, or
  `X-Artifact-Token` — matching the legacy artifact
  convention). 404 when the job is unknown, 409 when
  it exists but is not yet complete (PENDING /
  PROCESSING / ERROR), 403 when the token is missing
  or wrong, 410 when the on-disk PDF has been swept
  but the record is still in memory. The
  Content-Disposition header is `<stem>.ocr.pdf` (the
  trailing `.pdf` is stripped from the source filename
  to avoid `report.pdf.ocr.pdf`). The existing async
  endpoint was already shipping but lacked a
  result-download path; this is the user-visible
  completion of the async loop. (Phase D2.1)
- **Async OCR mode toggle in the workstation UI** —
  `ProcessSettings.svelte` gains an "Async processing"
  toggle (off by default — no behaviour change for
  existing users). When on, `WorkstationView` submits
  to `POST /api/process/async` and polls
  `GET /api/process/status/{job_id}` every 2 seconds
  (max 1000 attempts ≈ 33 min, well under the 24h
  record retention) until the job reaches a terminal
  state, then fetches the result PDF via
  `GET /api/jobs/{job_id}/result`. The toggle is
  purely UI state (`configStore.use_async`) — it is
  not synced to the server config because it is a
  deployment preference, not a runtime knob. The
  frontend `ocrApi` gains `processAsync` and
  `getResult`; the `apiClient` route-bearer table
  learns `/api/jobs` so the per-route OCR bearer is
  attached. (Phase D2.2 + D2.3)
- **P1 #4 (type `Any` escapes in `postprocess.py` /
  `handwriting_preprocessor.py`) resolved by venv refresh —
  no code change** — the §2 #4 finding flagged pyspellchecker's
  `candidates()` and `cv2.cvtColor` as untyped at the domain
  boundary, propagating `Any` through the return paths and
  tripping mypy's `warn_return_any = true`. An interim
  `typing.cast(...)` was applied in `glossary_imports.py`
  mid-investigation, then reverted once the
  `uv.lock` reconciliation (commit `829cd3b`) refreshed the
  venv (numpy 2.2.6 → 2.4.6, websockets 13.1 → 17.0.1). The
  mypy violations were symptoms of a stale venv, not actual
  code defects. Logged here for future auditors so the
  finding is not re-opened against a green baseline.

### Fixed

- **Documentation drift**:
  `/api/health` is not a real route; the liveness probe is
  `GET /health` (alias `/healthz`), with `GET /ready` (alias
  `/readyz`) for readiness. `DEPLOYMENT.md` and the
  `Dockerfile` healthcheck block now point at `/health`.
  `ARCHITECTURE.md` listed `/api/models/all`; the real
  combined route is `GET /api/models` (with
  `/api/models/ocr` and `/api/models/translation` siblings).
  `SECURITY.md` referenced a non-existent
  `OMNISCRIBE_CANCEL_SECRET` env var; cancel is an
  in-process `asyncio.Event` per `channel_id`, no signature.
  `DEPLOYMENT.md` documented third-party VLMs under
  `LLM_API_BASE` / `LLM_API_KEY`; the actual env vars are
  `OMNISCRIBE_LLM_API_BASE` / `OMNISCRIBE_LLM_API_KEY`
  (with `OMNISCRIBE_LLM_MODEL`).

- **OCR quality trust layer (Phase 1, foundation)** — new
  `omniscribe.core.ocr_quality` package ships six sub-modules
  (`watermark`, `script_detector`, `hallucination`, `calibration`,
  `trust_scorer`, `orchestrator`) plus an `events` log channel. Every
  sub-module defaults to **off** and fails open — no behavioural change
  for existing callers. `DocumentBlock` gains optional
  `trust_score: float | None` and `trust_flags: tuple[str, ...] | None`
  fields (always `None` until the layer is enabled).
  - New `OCrQualitySettings` Pydantic config (`extra="forbid"`).
  - `pyproject.toml` gains `[tool.omniscribe.ocr_quality]` workspace
    defaults, a `slow_dataset` pytest marker, and a `hypothesis` dev
    dependency for property tests on the pure trust formula.
  - New user-facing docs at `docs/ocr_quality.md`. Phase 2 (defaults on,
    Web UI Trust panel) and Phase 3 (calibration training, dataset
    regression) are planned but not yet shipped.
- **OCR quality trust layer (Phase 2, defaults on)** — wires the trust
  orchestrator into both engines and the `/api/process` route.
  - `OCRPipeline.__init__` accepts `trust_orchestrator=`; the
    `TrustOrchestrator` runtime-checkable Protocol in
    `omniscribe.core.ocr_quality.orchestrator` documents the
    `(blocks, page_image, *, model_id, page_size=None)` contract.
  - `EngineBase` gains `trust_orchestrator` and a no-op default
    `_apply_trust`; `HybridEngine` and `GroundedEngine` override it
    per page (Hybrid decodes the page image from base64; Grounded
    passes `None` because it has no page image in scope). Failures
    in the orchestrator log at DEBUG and fall back to the input
    blocks (design §7 fail-open contract).
  - `ProcessSettings.quality_options: OCrQualitySettings | None` with
    a `field_validator(mode="before")` that accepts `None`, a dict, a
    JSON-encoded string (multipart form), or an existing
    `OCrQualitySettings` instance.
  - `_form_param_keys()` and `process_pdf` / `process_pdf_async` carry
    the new `quality_options` form field through `resolve_process_settings`.
  - `ocr_pipeline_factory.build_pipeline` instantiates the
    orchestrator via `build_trust_orchestrator(settings.quality_options)`
    (returns `None` when every sub-module is off). Both pipeline
    branches pass it to `OCRPipeline(trust_orchestrator=...)`.
  - `/api/process` forwards `trust_model_id=settings.model` to
    `pipeline.run(...)` so calibration picks the right per-model JSON.
  - New `X-Document-Trust` response header carries a compact JSON
    summary (`block_count`, `scored_count`, `flagged_count`,
    `average`, 5-bin `histogram`, `flag_counts`) — emitted only when
    at least one block has a `trust_score`. The header is omitted
    entirely when the layer is off, keeping the no-orchestrator
    default byte-identical.
  - Phase 2 / Phase 3 keep the new defaults behind per-workspace
    toggles (`phase2_default: bool = False`,
    `phase3_default: bool = False`) so existing setups see no
    behaviour change.
- **OCR quality trust layer (Phase 3, calibration + dataset regression)**.
  - `scripts/calibrate_model.py` — CLI that fits Platt scaling
    `sigmoid(a * raw + b)` from an OCR-Quality-format JSON fixture
    via pure-numpy bounded gradient descent with backtracking
    line-search (`omniscribe.core.ocr_quality.calibration_fit.fit_platt`).
    Default `--train-fraction 0.8`, `--min-records 50`, `--seed 42`.
    Reports ECE (Expected Calibration Error, 10-bin weighted) on the
    held-out 20%; the acceptance criterion is ≥ 20% drop vs. raw.
  - `scripts/fetch_datasets.py` — downloads OCR-Quality and KIE-HVQA
    fixtures under `tests/fixtures/datasets/`. Datasets are not
    bundled in the repo (license review pending); the
    `slow_dataset` regression tests skip cleanly when absent.
  - `src/omniscribe/resources/calibration/qwen2_5_vl_72b.json` —
    shipped pre-trained calibration file fit on
    `tests/fixtures/datasets/ocr_quality_synthetic_qwen.json` (500
    records). ECE drop: 0.0999 → 0.0783 (21.6%, exceeds the ≥ 20%
    acceptance).
  - `tests/test_ocr_quality_calibration_regression.py`,
    `tests/test_kie_hvqa_hallucination_regression.py`,
    `tests/test_calibrate_model_script.py`,
    `tests/test_fetch_datasets_script.py`,
    `tests/test_ocr_quality_calibration_fit.py` — dataset-driven
    regression tests (12 Platt-fit, 6 calibration, 3 dataset-script,
    7 calibrate-script tests). Full-fixture paths are `slow_dataset`-
    gated; the `slow_dataset` mini-fixture smoke tests run with the
    fast suite.
  - `.github/workflows/nightly.yml` gains the calibration regression
    job (03:00 UTC) that runs `pytest -m slow_dataset` against the
    fetched datasets with cached HF Hub snapshots.
- **SECURITY.md** — vulnerability disclosure policy, threat model,
  hardening checklist. (D1)
- **DEPLOYMENT.md** — three deployment profiles (local, LAN, public)
  with Caddy + docker-compose reference. (D1)
- **CHANGELOG.md** — this file. (D1)
- `OMNISCRIBE_AUTH_TOKEN`, `OMNISCRIBE_OCR_AUTH_TOKEN`,
  `OMNISCRIBE_TRANSLATION_AUTH_TOKEN` reject well-known placeholder
  values at startup (e.g. `change-me-in-prod`). (M10)
- `AuthTokenUpdate.auth_token` field carries `min_length=32` and a
  custom weak-pattern check. (M1)
- `urllib` redirect handler validates every `Location` hop through
  `is_ssrf_target` (no more silent walk to `169.254.169.254`).
  (M2)
- `OMNISCRIBE_MAX_UPLOAD_MB` default bumped to 10 GB; absolute
  ceiling 100 GB.
- `MaxUploadSizeMiddleware` rejects oversized chunked uploads
  (cumulative byte accounting; was per-chunk before). (T2 / H2)
- `MaxUploadSizeMiddleware` is now wrapped around `send()` so a
  detected overflow actually emits a 413, not the inner app's
  empty-body 422. (T2 / H2)
- `BearerAuthMiddleware` accepts per-service tokens
  (`OMNISCRIBE_OCR_AUTH_TOKEN`, `OMNISCRIBE_TRANSLATION_AUTH_TOKEN`)
  for OCR- and translation-only routes.
- Dockerfile base image is digest-pinned. (M7)
- Dockerfile uv install is version-pinned. (M8)
- Dockerfile HEALTHCHECK against `/api/health`. (M11)
- `compose.yaml` binds the API + Redis to `127.0.0.1` only. (M9)
- `_emit` writes a terminal error progress frame if the output
  writer raises, so the UI does not appear stuck. (E3)
- `test_size_limits.py` covers chunked-upload overflow (single chunk
  and cumulative). (T2)
- `test_http_fetch.py` covers urllib SSRF redirect blocking. (T2)
- `test_websocket_handler.py` covers `/api/progress/cancel`
  session-token binding (missing header, wrong token, unbound
  channel, success). (T2)
- **WebSocket byte-level corruption on the progress channel** —
  block-level senders (`block_complete`, `block_retry`,
  `block_revised`, `quality_summary`) are awaited on the
  `/api/process` worker's own event loop while progress and
  warning frames are emitted on the main uvicorn loop. uvicorn's
  wsproto state machine is not safe to drive from two threads
  at once, so writes interleaved byte-by-byte on the wire and
  the browser saw mangled JSON fragments ("pairge" where the
  real text was "progress", "4tage" instead of "stage"),
  truncated frames (`{"status":"OCR (1/1)","percent` cut off
  mid-string), and ultimately `Invalid frame header` as the
  wsproto receiver gave up. `ConnectionManager.send` now records
  each channel's accept loop on `connect` and marshals any
  foreign-loop send back onto it via
  `asyncio.run_coroutine_threadsafe` + `asyncio.wrap_future`,
  so all socket writes are serialized through the loop that
  accepted the socket. The fix preserves caller ordering and
  backpressure. Regression-locked by
  `test_ws_send_from_foreign_event_loop_is_marshaled_to_accept_loop`,
  which fails against the old single-loop send path because
  `send_threads[0]` would no longer match `accept_thread["id"]`.
- **OCR fail on LM Studio + OlmOCR-2** — adding a system-role
  message on top of the canonical OlmOCR page prompt shifted
  the model's input distribution (OlmOCR-2 was RL-trained on
  the prompt as a single user turn). Symptom was
  `LLMCallError: ...` for every crop / handwriting / dual-engine
  call. `omniscribe.core.ocr.prompts` now exports
  `model_supports_system_role(model_name)`, which returns
  `False` for any model whose name contains `olmocr` (case-
  insensitive) — the only family we have direct field evidence
  for. `OCRProcessor._resolve_page_system` /
  `_resolve_crop_system` and the grounded backend's
  `_call_with_retry` gate on this helper, so the canonical
  page prompt stays a pure user message for OlmOCR-2 *and*
  every crop / handwriting / dual-engine call also drops the
  system role. Other models (Qwen, future additions) keep
  the system role. The list is intentionally narrow — see the
  helper's docstring for the "extend cautiously" rationale.
- **OCR fallback paths now log warnings** — three sites
  (`src/omniscribe/core/ocr/processor.py:487, 566` and
  `src/omniscribe/core/pdf/embedder.py:121`) used to swallow
  all exceptions with bare `except Exception:`, returning safe
  defaults without any log line. OCR quality degradation was
  invisible to operators. The except clauses are now narrowed
  to the specific exception types (pytesseract errors, cv2
  errors, font-probe errors) and each site emits a
  `logger.warning` with the underlying exception before the
  safe-default return. Tests cover the three sites.
- **Form primitives now associate errors and hints via
  ARIA** — `Input.svelte` and `Select.svelte` rendered an
  error/hint `<p>` below the form element but didn't link it
  via `aria-describedby` or set `aria-invalid`. Screen readers
  could not announce the error or hint on focus. The
  `ariaLabel` prop (added in the prior audit-fix 2bec3bf) is
  unchanged; the missing describedby + invalid wiring is
  added in this commit. The `Select.svelte` `ariaLabel` prop
  binding stays as-is.
- **TabRibbon now follows the WAI-ARIA tab pattern** — the
  container was a plain `<nav>` with `<button>` children. The
  container now has `role="tablist"`, each tab has
  `role="tab"`, `aria-selected`, and roving `tabindex`
  (active=0, others=-1).
- **Docker image is now multi-stage** — the Dockerfile was a
  single `FROM python:3.14-slim AS runtime-base` (dependabot PR
  #22 had bumped the base from 3.12 to 3.14 just before P1
  started) that ran `uv sync` of transformers, torch, surya-ocr,
  and chromadb in the production image, with the `uv` toolchain
  and `curl` build deps landing in the final image and
  enlarging the attack surface. A `builder` stage now does the
  `uv sync`; the runtime stage copies only `/app/.venv` from
  the builder, leaving the final image with no `uv` toolchain,
  no `curl`, and no build cache. The pre-change image did not
  build (it was missing a `COPY LICENSE README.md` for
  hatchling's project install — a pre-existing gap, incidentally
  fixed in this commit), so no pre-change size baseline exists.
  The 17.4 GB virtual / 11.4 GB unique final image is dominated
  by `torch` + `transformers` + `chromadb` + `surya-ocr`; the
  main win is the absence of build tools and build cache from
  runtime, verified by `docker run` smoke (no `uv`/`curl`
  in the container) and import test (`transformers`, `surya`,
  `omniscribe` all import).

### Security

- **scripts/ingest_lexicon.py is now XXE-safe** — the script
  parses external GitHub-hosted TEI XML with `defusedxml.ElementTree`
  instead of the stdlib `xml.etree.ElementTree`. The previous parser
  silently accepted `<!DOCTYPE>` declarations and external entity
  references, allowing XXE-driven local file read, SSRF, or
  billion-laughs DoS via a malicious payload. The parse step is
  extracted into `_parse_xml()` and unit-tested for plain XML,
  external-entity XXE, and billion-laughs rejection.

- **Redis password is now CSPRNG-generated** — `start_app.vbs`
  generates the password via a PowerShell one-liner using
  `[System.Security.Cryptography.RandomNumberGenerator]` instead of
  the previous VBScript `Randomize` + `Rnd()` LCG. The consumer-side
  `--requirepass` plumbing added in a77b77a is unchanged; only the
  entropy source moved. A hygiene test asserts the VBS no longer
  references `Rnd` / `Randomize` and now references the CSPRNG type.

### Changed

- `_extract_prompt_and_image` now returns a 2-tuple
  `(prompt, image)`; the legacy `system_prompt` slot and the
  system-from-`messages` branch are removed. Callers must
  pass the system role via the explicit `system_prompt`
  parameter on `call_llm` (which routes through
  `model_supports_system_role` for OlmOCR family models).
  (Issue 12)
- `process_pdf` / `process_pdf_async` share a single
  `_prepare_process_request` helper (was duplicated ~60 lines of
  validation/upload). (Q1)
- `Any`-typed `manager_send_block` / `manager_send_page_complete`
  callbacks replaced by a `ConnectionManagerLike` Protocol. (Q2)
- Runner dependencies lifted from routers to a factory module
  (`ocr_pipeline_factory.py`). (Q3)
- Synchronous `json.load` / `open` calls inside async handlers are
  wrapped in `asyncio.to_thread`. (Q4)
- `_convert_pages` tautology guard simplified to `if pages:`. (Q5)
- **Progress WebSocket wire format is now line-delimited JSON
  (NDJSON)** — every frame the server sends is one JSON object
  followed by a single `\n`. The frontend's `socket.onmessage`
  in `frontend/src/lib/api/websocket.ts` splits on `\n` and
  parses each line independently. Belt-and-suspenders: even
  if a future bug ever concatenates two ASGI frames into one
  text payload, the client can split and recover. The
  previous single-JSON-per-frame path is still valid (a
  trailing `\n` is harmless to `JSON.parse`).
- **`/api/process` warning text now includes the underlying
  exception message**, capped at 500 chars. Old format was
  `OCR failed for page N: LLMCallError`; new format is
  `OCR failed for page N: LLMCallError: <underlying message>`.
  Saves a round-trip to the server log when a warning fires.
- **OCR + grounded prompt bodies slimmed** — the diacritics
  emphasis and "no invent" guard text moved out of the user
  prompt and into the system message (which the model
  processes separately from the per-task instructions).
  Visible side effects: the OlmOCR-2 page prompt and the
  ground-truth OlmOCR page body are unchanged, but the crop
  / handwriting / dual-engine / correction crops no longer
  carry the long diacritics preamble in their user turn.
- **Grounded default prompt gained two extra lines**:
  "for multi-column layouts, read each column top-to-bottom
  before moving to the next column" and "if the page
  contains no readable text, emit an empty JSON array `[]`".
  Both are belt-and-suspenders against the historical
  line-collapsing and "single placeholder element" failure
  modes on dense / blank pages.
- `_ai_error_response` deduplicated to one definition in
  `common.py`. (Q6)
- TrOCR dual-engine fallback catches `LLMCallError` separately so
  the page-isolation boundary sees secondary-VLM failures as
  engine-down signals instead of swallowing them. (E2)
- `OCRProcessor` no longer uses `getattr(self, "handwriting_mode",
  False)` — the attribute is unconditionally set in `__init__`.
  (E4)
- `_PYMUPDF_AGPL_NOTICE_EMITTED` race documented as acceptable
  (logging-only idempotent). (E5)
- Dependency upper pins tightened across `pyproject.toml` and
  `frontend/package.json`:
  - `pillow>=11.3,<13`
  - `httpx>=0.27.2,<0.29` (CVE-2025-43859 floor)
  - `requests>=2.32.0` (CVE-2024-35195 floor)
  - `openai>=2.11.0,<3`
  - `fastapi>=0.124,<1.0`
  - `pymupdf>=1.27,<2`
  - `torch>=2.0,<3`
  - `redis>=5.0,<9`
  - `langgraph>=0.1,<2`
  - `chromadb>=0.5,<2`
- `block_metadata_overlays` typed as `Mapping[...]` so the
  `_cross_page_merge` cast is gone. (A5)
- `ARCHITECTURE.md` adds the missing `/api/config/ocr`,
  `/api/config/translation`, `/api/models/ocr`,
  `/api/models/translation`, `/api/models/all`, and
  `/api/glossary/library/*` routes. (D1)

### Removed

- `markdown-it` frontend dependency (no imports — dead). (Deps)
- `@types/markdown-it` frontend dev dependency. (Deps)
- Vite `manualChunks` branch for `markdown-it`. (Deps)

### Deferred

- A1 — ASGI middleware is intentional for pre-routing enforcement;
  per-router `dependencies=[Depends(...)]` is no safer in practice.
- A2 — module-level state singletons are the right shape until the
  Redis backend ships.
- A3 — frontend store consolidation is out of scope for the backend
  audit.
- A4 — lazy imports are intentional for cold-start perf.

## [0.1.0] — Initial public release

- Hybrid OCR pipeline (Surya detection + VLM OCR + DP align + refine).
- Grounded OCR path (`grounded_backend=`).
- WebSocket-bound progress with token-bound channels.
- Glossary RAG for translation (`async-translation` + `memory` extras).
- Svelte 5 + Tailwind CSS v4 workstation UI.
- Single-worker FastAPI server with optional Celery background jobs.

[Unreleased]: https://github.com/Sifr-r/OmniScribe/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Sifr-r/OmniScribe/releases/tag/v0.1.0