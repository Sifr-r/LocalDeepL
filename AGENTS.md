# AGENTS.md

This file tells coding agents and contributors how to work with this repository.

## Quick Start

```bash
uv sync
uv sync --extra web --extra preprocessing --extra async-translation --extra lexicon
uv run omniscribe-server --port 8000
```

Real OCR requires an OpenAI-compatible VLM endpoint. The default is LM Studio at `http://localhost:1234/v1`.

## Validation

**After any code change, run the relevant subset of these checks before claiming completion.**

```bash
# Fast gate — run after every material edit:
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"

# Full gate — run before merge / PR:
uv run pytest
uv run pytest -m slow
uv run pytest -m live_llm
uv run pytest tests/test_aligner.py -v
cd frontend && npm run check && npm test && npm run build
```

- `pytest-asyncio` uses auto mode. Write `async def test_...` without decorators.
- Slow tests load Surya and may download its model on the first run.
- Markers are `slow`, `live_llm`, and `slow_dataset`:
  - `slow` — loads the Surya detection predictor (~5s first run, ~500 MB model weight).
  - `live_llm` — hits a real LLM endpoint; run manually with `uv run pytest -m live_llm` against a local LM Studio instance (`http://localhost:1234/v1`).
  - `slow_dataset` — exercises the full OCR-Quality / KIE-HVQA regression fixtures (`tests/fixtures/datasets/ocr_quality_full.json`, `kie_hvqa_full.json`); only meaningful once `scripts/fetch_datasets.py` has the upstream license review cleared and downloads the real datasets. Today the marker is a no-op skip (the fixtures don't ship); the marker exists so the next test author can land tests that need the full data without remembering the right `xfail` shape.
- Pre-commit hooks run ruff (check + format) and mypy automatically on every commit. Install with `uv tool run pre-commit install`.

## Core Paths

Source directories are split into **core** (OCR pipeline and API surface) and **peripheral** (tooling, frontend, utilities). Changes to core paths require the full fast gate; peripheral-only changes can skip some checks.

### Core — full fast gate required

| Path | Scope |
| --- | --- |
| `src/omniscribe/core/` | OCR engines, alignment, PDF/image handling, document model, workflows, processors, translation, grounded backends, OCR quality trust layer |
| `src/omniscribe/api/` | FastAPI routers, schemas, services, security middleware, Celery tasks |
| `src/omniscribe/pipeline.py` | `OCRPipeline` facade |
| `src/omniscribe/server.py` | FastAPI app entry point |
| `src/omniscribe/config.py` | Runtime settings |

```bash
# Required for every core-path change:
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

If the change touches `core/aligner.py`, `core/workflows/`, or `core/ocr/`, also run `uv run pytest tests/test_aligner.py -v`.

### Peripheral — focused validation

| Path | Scope | Validation |
| --- | --- | --- |
| `src/omniscribe/utils/` | Shared helpers, SSRF guard | `ruff check src` + `mypy src` |
| `scripts/` | Developer CLI utilities | `ruff check scripts` + relevant `pytest tests/test_scripts_smoke.py` |
| `frontend/src/` | Svelte UI | `cd frontend && npm run check && npm test && npm run build` |
| `tests/` (new tests only) | Test additions | `ruff check tests` + `pytest <new_test_file> -v` |
| `AGENTS.md`, `README.md`, `CHANGELOG.md` | Documentation | No code validation required |

### Decision rule

If a change touches **any** core path, run the full fast gate. If it is peripheral-only, run only the validation listed for that path above. When in doubt, run the full fast gate.

## Conventions

- Python 3.11 or newer. Use `uv`; do not install dependencies with `pip`.
- Prefer self-documenting code and docstrings. Add comments only when they clarify non-obvious behavior.
- Keep `tqdm_patch.apply()` before `from surya.detection import DetectionPredictor` in `core/aligner.py`.
- Keep bboxes normalized as `[x0, y0, x1, y1]` in `0..1` until `PDFHandler.embed_structured_text`.
- Treat image inputs as first-class inputs. PDF and image paths share the output writer.
- OmniScribe is Web UI/API-first. The user-facing `omniscribe` CLI script has been deprecated; do not add or restore it. `OCRPipeline` is still importable for in-process programmatic use (e.g. an embedded workflow), but no script entry is shipped.
- Keep local document processors selectable through web/API `document_processors`. Current names are `reading_order`, `quality_analysis`, `structure_analysis`, `section_analysis`, `layout_enrichment`, and `table_extraction`; defaults run no processors.

## Pipeline Paths

```text
PDF/image -> pages -> Surya detection (+ whitespace + text-layer recall) -> sparse: full-page OCR -> DP alignment -> refine ---------------+
                                    \-> dense: per-box OCR --------------------------------------------------------------------------------+-> post-process -> DocumentResult -> optional processors -> searchable PDF

PDF/image -> grounded bbox-native VLM -> post-process -> DocumentResult -> optional processors -> searchable PDF
```

- Hybrid is the default: Surya detection, optional whitespace-recall and text-layer-recall supplements, VLM OCR, DP alignment, optional refine, optional post-processing, embed.
- Dense hybrid pages use per-box OCR. `dense_mode="auto"` switches when box count exceeds `dense_threshold`.
- Grounded OCR uses `grounded_backend=` and skips Surya, DP alignment, and refine.

## Key Files

| File | Role |
| --- | --- |
| `src/omniscribe/server.py` | FastAPI application, server entry point, `omniscribe-server` script |
| `src/omniscribe/pipeline.py` | `OCRPipeline` facade — picks `HybridEngine` or `GroundedEngine` based on injected components |
| `src/omniscribe/evaluation.py` | Package-root confidence eval (fixture loader, IoU matching, `ConfidenceReport`) for `scripts/confidence_*.py` |
| `src/omniscribe/core/document.py` | Normalized DocumentResult IR and legacy pages-data adapter |
| `src/omniscribe/core/processors/` | Local deterministic document processors (`reading_order`, `quality`, `structure`, `section`, `layout`, `table`) and builder |
| `src/omniscribe/core/preprocessing.py` | Local hybrid-path page preprocessing |
| `src/omniscribe/core/routing.py` | Quality routing recommendation metadata |
| `src/omniscribe/core/evaluation.py` | Local evaluation metric helpers (lightweight, for processor result scoring) |
| `src/omniscribe/core/docx_writer.py` | Markdown → `.docx` converter for the docx export route |
| `src/omniscribe/core/aligner.py` | Surya detection and DP alignment |
| `src/omniscribe/core/text_recall.py` | Whitespace recall booster — pixel-statistics text-line candidates merged into Surya detection on the hybrid path; `OMNISCRIBE_WHITESPACE_RECALL` kill switch, INFO run summary, fail-open per page |
| `src/omniscribe/core/text_layer_recall.py` | Text-layer recall source — recovers lines Surya missed from a digital PDF's embedded text layer (second box source, merged after the whitespace booster); `OMNISCRIBE_TEXT_LAYER_RECALL` kill switch, INFO run summary, fail-open per page; strict no-op for scans and image inputs |
| `src/omniscribe/core/ocr/` | OpenAI/Anthropic/Ollama multi-format client, prompts, limits, filters, and resilience (retry + circuit breaker) |
| `src/omniscribe/core/ocr_quality/` | OCR Quality Trust Layer (watermark, script detector, hallucination guard, Platt scaling calibration, trust scorer, orchestrator) |
| `src/omniscribe/core/transcription/` | Speech-to-text audio transcription engines (local & OpenAI-compatible API backends) |
| `src/omniscribe/core/lexicon/` | LanceDB-backed canonical glossary / translation lexicon store (Protocol + LanceDB impl + embedding wrapper + legacy `GlossaryLibrary` adapter + one-shot migration core). See `docs/lexicon-migration-spec.md`. |
| `src/omniscribe/core/glossary_library/` | **DEPRECATED** — JSON-on-disk glossary writer kept as a fallback; new code should use `omniscribe.core.lexicon.LexiconStore` (or the `GlossaryLibraryAdapter` shim for the legacy API). Removed in a future cleanup. |
| `src/omniscribe/core/glossary_sources/` | Glossary import parsers (TBX, CSV, JSON, URL, SQL, Git, TMX, XLIFF) |
| `src/omniscribe/core/ocr/resilience.py` | `is_transient_error` classification, `CircuitBreaker` (closed/open/half-open), `CircuitOpenError` |
| `src/omniscribe/core/pdf/` | PDF/image rasterization (`rasterizer.py`), sandwich PDF embedding (`embedder.py`), and `PDFHandler` facade (`handler.py`) |
| `src/omniscribe/core/grounded/` | Grounded backends and bbox JSON parsers (retry + circuit breaker on the VLM call) |
| `src/omniscribe/core/postprocess.py` | Dictionary spellcheck |
| `src/omniscribe/core/translation_config.py` | Core-owned async translation settings |
| `src/omniscribe/core/translation.py` | Optional LangGraph translation workflow |
| `src/omniscribe/core/workflows/base.py` | `EngineBase` + `OutputWriter` / `DocumentResultWriter` / `ProgressCallback` / `WarningCallback` shared by both engines |
| `src/omniscribe/core/workflows/utils.py` | Stand-alone workflow helper functions (`parse_page_range`, `_estimate_confidence`, `_decode_page_image`, `_drop_refined_duplicates`) and constants |
| `src/omniscribe/core/workflows/hybrid.py` | `HybridEngine` — Surya detect → VLM OCR → DP align → refine → post-process → processors → output |
| `src/omniscribe/core/workflows/grounded.py` | `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/omniscribe/core/workflows/repair.py` | `QualityRepairLoop` / `RepairOptions` — engine-agnostic block-level low-confidence re-OCR with stall guard and fail-open |
| `src/omniscribe/resources/dictionaries/` | Packaged spellcheck dictionaries |
| `src/omniscribe/resources/calibration/` | Pre-trained model confidence calibration files (e.g. `qwen2_5_vl_72b.json`) |
| `src/omniscribe/api/routers/config.py` | Runtime configuration and model discovery |
| `src/omniscribe/api/routers/ocr.py` | OCR upload, process, and synchronous AI routes |
| `src/omniscribe/api/routers/providers.py` | Multi-format provider catalog, details, and active provider switching |
| `src/omniscribe/api/routers/transcription.py` | Voice transcription and transcription provider configuration |
| `src/omniscribe/api/routers/glossary_imports.py` | Terminology library and file/URL glossary import routes |
| `src/omniscribe/api/routers/health.py` | Liveness (`/health`, `/healthz`) and readiness (`/ready`, `/readyz`) probe endpoints |
| `src/omniscribe/api/routers/websocket.py` | Token-bound WebSocket progress transport |
| `src/omniscribe/api/routers/jobs.py` | `GET/DELETE /api/jobs` — job history and clear-all |
| `src/omniscribe/api/routers/artifacts.py` | Token-bound artifact download routes (text, metadata, exports) |
| `src/omniscribe/api/routers/translation.py` | Synchronous and async translation routes |
| `src/omniscribe/api/routers/extraction.py` | `POST /api/extract` and `POST /api/export/*` routes |
| `src/omniscribe/api/routers/state.py` | Module-level singletons (`text_artifacts`, `metadata_artifacts`, `export_artifacts`, `job_history`, `progress_service`) — `backend` is the canonical access path; the seven module-level aliases mirror `state.backend.*` |
| `src/omniscribe/api/services/state_backend.py` | `StateBackend` runtime-checkable Protocol + `LocalStateBackend` (in-memory, default) + `build_state_backend(settings)` factory. The factory is the single boundary that fails loud on an unknown `OMNISCRIBE_STATE_BACKEND` value |
| `src/omniscribe/api/routers/common.py` | Shared router helpers (`_stable_server_error`, `_extract_bearer_token`, `_path_exists`) |
| `src/omniscribe/api/schemas/requests.py` | `ConfigUpdate`, `ProcessSettings`, `TranslationRequest`, `ExtractionRequest`, `ExtractionTemplate`, `DocumentExportRequest`, `DocumentExportFormat`, `ExportDocxRequest`; enums: `PipelineMode`, `DenseMode`, `SpellcheckMode`, `DocumentProcessorName` |
| `src/omniscribe/api/services/provider_manager.py` | `ProviderManager` service — provider templates, env-var discovery, disk persistence, and active provider switching |
| `src/omniscribe/api/services/security.py` | API upload validation, stable error constants, temporary-file cleanup, opaque text artifact IDs |
| `src/omniscribe/api/services/security_config.py` | `SecuritySettings.from_env()` — env-driven knobs for `OMNISCRIBE_AUTH_TOKEN`, `_CORS_ORIGINS`, `_MAX_UPLOAD_MB`, `_RATE_LIMIT_PER_MIN` |
| `src/omniscribe/api/services/security_middleware.py` | ASGI middlewares wired by `server.create_app()`: `BearerAuthMiddleware` (constant-time `secrets.compare_digest`), `MaxUploadSizeMiddleware` (rejects on `Content-Length`), `RateLimitMiddleware` (per-IP 60s sliding window, in-memory). WebSocket handshake auth is still enforced per-channel in `routers/websocket.py` |
| `src/omniscribe/api/services/artifacts.py` | `TextArtifactStore`, `PageText`, `TextArtifactHandle`, opaque id / token primitives |
| `src/omniscribe/api/services/jobs.py` | `JobHistory`, `JobRecord`, `JobStatus` |
| `src/omniscribe/api/services/state_backend_redis.py` | `RedisStateBackend` (opt-in; requires `OMNISCRIBE_STATE_BACKEND=redis` + a Redis server) — Redis-backed artifact metadata + job history for horizontal scaling across multiple uvicorn workers |
| `src/omniscribe/api/services/state_backend_sqlite.py` | `SQLiteStateBackend` (opt-in; requires `OMNISCRIBE_STATE_BACKEND=sqlite`) — single-file persistent state for the local-first deployment shape. WAL-mode SQLite file (default `<artifact_dir>/omniscribe-state.db`; override with `OMNISCRIBE_STATE_DB_PATH`) holds the three artifact tables + jobs table; `ProgressService` / `GlossaryLibrary` / `OCRJobQueue` remain in-memory because they reference live channels |
| `src/omniscribe/api/services/progress.py` | `ProgressService`, `ProgressChannel`, stage weights |
| `src/omniscribe/api/services/document_metadata.py` | Token-bound metadata report artifacts for optional document processor outputs |
| `src/omniscribe/api/services/document_exports.py` | Token-bound document export artifacts |
| `src/omniscribe/api/services/workflow.py` | Web/API workflow summaries |
| `src/omniscribe/api/services/ai.py` | Backing AI service for extraction and translation routes |
| `src/omniscribe/utils/security.py` | SSRF target validation |
| `src/omniscribe/core/handwriting_preprocessor.py` | Local handwriting image preprocessor |
| `scripts/` | Developer utilities: confidence eval, fixture builder, debug/inspection scripts, bbox visualizers |
| `examples/` | Sample PDFs and images for `tests/`, `test_ui.py`, and the confidence scripts |
| `install.bat` / `install.ps1` / `start_app.vbs` / `stop_app.bat` / `test_ui.py` | Windows one-click install, hidden-start, stop, and Playwright smoke test |

## Extension Points

`OCRPipeline` accepts injected components:

- `aligner=`: layout detection and text alignment
- `ocr_processor=`: page and crop OCR backend
- `pdf_handler=`: input conversion and default PDF writer
- `output_writer=`: alternate output generation (legacy 4-arg callable, or any object implementing `DocumentResultWriter.write_document_result` for the lossless `DocumentResult` path)
- `grounded_backend=`: bbox-native OCR path
- `document_processors=`: sequence of `DocumentProcessor` instances run after OCR cleanup and before PDF embedding
- `page_preprocessor=`: opt-in `PagePreprocessor` for orientation/deskew/denoise/contrast/crop preprocessing on the hybrid image path

## Plugin Context Migration Status

The new `src/omniscribe/api/plugin/` package introduces a Cordis-style
plugin container with Protocol-based seams and a "look up by Protocol,
fall back to singleton" migration window. This section is the single
source of truth for which seams are wired at boot and which fall through
to the legacy `api/routers/state.py` singletons. **Last updated 2026-08-19.**

| Seam | Protocol | Boot provider | Status |
|---|---|---|---|
| `JobQueue` | `seams.JobQueue` | `local_job_queue_provider("local")` | REGISTERED — wraps `state.ocr_job_queue` |
| `SessionLog` | `seams.SessionLog` | `memory_session_log_provider("memory")` | REGISTERED — new audit log |
| `ConfigStore` | `seams.ConfigStore` | _none_ | UNREGISTERED — `get_config_store()` returns `None`; legacy singleton wins |
| `ProgressService` | `seams.ProgressService` | _none_ | UNREGISTERED — `get_progress_service()` returns `None`; legacy singleton wins |
| `TextArtifactStore` | `seams.TextArtifactStore` | _none_ | UNREGISTERED — `get_text_artifact_store()` returns `None`; legacy singleton wins |

**Migration semantics.** During the migration window every consumer uses
`runtime.get_<name>()` which returns the registered provider or `None`.
Callers fall through to the legacy `api/routers/state.py` singletons
when the lookup is `None`. This is intentional — it lets new and old code
paths coexist on the same request.

**Toggle.** `PLUGIN_CONTEXT_ENABLED` is read at import time from
`OMNISCRIBE_PLUGIN_CONTEXT` (default `False`). Runtime toggling is not
yet supported; the seam is "open or closed" for the life of the process.
`set_plugin_context_enabled()` exists for tests only.

**Dual-write shim.** `api/services/artifacts.py` `TextArtifactStore.put`
emits an `artifact.created` event to the plugin context as a
best-effort secondary write. The primary write (the singleton store)
never blocks on the plugin path. The dual-write `except Exception` is
intentionally narrow in the new code (only `ServiceNotFoundError` and
`ContextDisposedError` are swallowed) — programming bugs in
`ArtifactStoreProjection._apply` propagate to the caller.

**Operator note.** Until the three UNREGISTERED seams get providers,
you can ignore the plugin package entirely. The legacy `state.py`
singletons are the production access path. See `audits/2026-08-19-secondary-validation-pass.md` for the build-up debt the new infra introduced.

## Web Notes

- Browser translation and structured extraction use synchronous endpoints and do not require Redis.
- `/api/translate/async` uses Celery, Redis, and LangGraph from the `async-translation` extra. The translation module reads glossary context from the LanceDB-backed `LexiconStore`; install the `lexicon` extra (lancedb + pyarrow + pandas + sentence-transformers). The store degrades gracefully when unavailable (empty `rag_context`). The `memory` extra name is kept as a one-release deprecation alias for `lexicon`.
- `ALLOW_SSRF_LOCAL=true` is the local-development default. Set it to `false` when exposing the server to untrusted users.
- **Auth**: set `OMNISCRIBE_AUTH_TOKEN` to require `Authorization: Bearer <token>` on every HTTP route (constant-time compare, ASGI middleware). Unset = open (local-desktop default).
- **VLM resilience**: every LLM call retries transient errors (429/5xx/connection resets) with exponential backoff, and a per-request circuit breaker fails fast after `OMNISCRIBE_CB_FAILURE_THRESHOLD` (default 5) consecutive failures. Tunables: `OMNISCRIBE_LLM_MAX_RETRIES` (default 2), `OMNISCRIBE_LLM_RETRY_BASE_DELAY` (default 1.0s), `OMNISCRIBE_CB_COOLDOWN` (default 30s).
- **Model pre-flight**: each `/api/process` request verifies the configured model is actually loaded on the VLM server (`GET /v1/models`) before paying for conversion/detection — one extra HTTP round-trip per request, guarding against LM Studio's silent model fallback (issue #7).
- **Quality repair loop**: `/api/process` re-OCRs blocks whose estimated confidence is below the target (crop-scoped, sequential, accept-only-while-improving) after block emission and before embedding. Defaults ON at the API layer (up to 2 extra VLM passes per low-confidence block); in-process `OCRPipeline.run` callers stay off unless they pass `repair_options=`. Per-request form fields `quality_loop_enabled` / `quality_target` (0.5–1.0) / `quality_max_retries` (0–5); env seeds `OMNISCRIBE_QUALITY_LOOP`, `OMNISCRIBE_QUALITY_TARGET`, `OMNISCRIBE_QUALITY_MAX_RETRIES`. WebSocket frames: `block_retry`, `block_revised`, `quality_summary`.
- Web runtime settings are initialized in `api/routers/config.py`.
- **Windows quick-start**: run `install.bat` to install `uv`, sync the web extra, and create Desktop / Start-Menu shortcuts. `start_app.vbs` boots Redis (via Docker) + Celery + uvicorn hidden and opens the browser; it writes a timestamped append log to `start_app.log` next to itself. `stop_app.bat` terminates the uvicorn + Celery processes. `test_ui.py` is the headless Playwright smoke test against `examples/dense.pdf`.
- **Developer scripts** live in `scripts/`. The most useful for OCR quality work are `scripts/confidence_eval.py` (hybrid + grounded vs the `examples/*.pdf` fixtures) and `scripts/confidence_image.py` (single-image confidence). The rest are debug/inspection/visualization tools.
- **Docker**: `Dockerfile` builds a `python:3.14-slim` runtime with the `web`, `async-translation`, and `preprocessing` extras. `compose.yaml` runs `api` + `redis` by default; add `--profile async` to also start a Celery worker. Image exposes port 8000; bind `LLM_API_BASE` to `http://host.docker.internal:1234/v1` to talk to a host-side LM Studio.
- **Pre-commit**: `.pre-commit-config.yaml` runs ruff (check + format), mypy, and `uv-lock` on every commit. Enable with `uv tool run pre-commit install` after cloning.
- **Nightly slow tests**: `.github/workflows/nightly.yml` runs `pytest -m slow` at 03:00 UTC with cached HF Hub snapshots, catching Surya-path regressions the fast tier skips.
- **OCR system-role gating**: some models (notably OlmOCR-2 / OlmOCR) were RL-trained on a single user-role turn with the canonical OlmOCR page prompt and reject a layered system role. `omniscribe.core.ocr.prompts.model_supports_system_role` is the single source of truth — the canonical OLMOCR page prompt is also always sent as a pure user message even on models that *do* support system role. When adding a new call site that emits OCR prompts, route through `_resolve_page_system` / `_resolve_crop_system` (or `select_system_message` for crop / dual-engine / correction) rather than hand-rolling a system role.
- **Progress WebSocket cross-loop marshalling**: `ConnectionManager.send` records each channel's accept loop on `connect` and marshals any foreign-loop send back onto it. **All writes to the underlying uvicorn WebSocket must go through `manager.send(...)` from any non-accept loop** — uvicorn's wsproto state machine is not safe to drive from two threads / loops at once, and concurrent writes interleave bytes on the wire (browser sees mangled JSON, truncated frames, `Invalid frame header`). The regression test is `test_ws_send_from_foreign_event_loop_is_marshaled_to_accept_loop`; if you find yourself bypassing the manager to call `ws.send_text` / `ws.send_json` directly, that test is the contract you're breaking.

## Known Tech Debt

- `/api/process` runs the full OCR pipeline synchronously on the uvicorn worker (no background task queue on the default path); long jobs block other requests on the same worker. The async path ships already — `POST /api/process/async` returns `202 + job_id` immediately and the single-worker `OCRJobQueue` (in `api/services/ocr_jobs.py`) drains jobs sequentially. The workstation UI gained an "Async processing" toggle in Phase D2 that lets users opt into the async path; the result PDF is fetched from `GET /api/jobs/{job_id}/result` once the job reaches `status: "complete"`. The async queue is still in-memory (dies on restart) and single-worker — true multi-worker / crash-safe dispatch needs a Celery task that mirrors the translation pattern in `api/tasks.py`.
- Job/artifact state is in-memory by default (`api/routers/state.py` singletons). Two opt-in persistent backends ship now: `OMNISCRIBE_STATE_BACKEND=sqlite` (single-file, local-first; see `state_backend_sqlite.py`) and `OMNISCRIBE_STATE_BACKEND=redis` (multi-worker; see `state_backend_redis.py`). All three implementations satisfy the `StateBackend` Protocol so call sites are unchanged. `ProgressService` / `GlossaryLibrary` / `OCRJobQueue` stay in-memory by design — they reference live WebSocket channels / RAG index state and cannot meaningfully be persisted.
- `pages_structured` legacy dict is still the working format inside `HybridEngine`; `DocumentResult` is built at finalize. The output boundary now supports the lossless rich path (`DocumentResultWriter`), but intermediate stages still convert.
- `dense.pdf` and `notes.pdf` ground-truth fixtures are bootstrapped from hybrid output (regression baseline, not absolute quality).
- `surya-ocr 0.17.x` imports `requests` in `surya/common/s3.py` without declaring it. `pyproject.toml` includes a `requests>=2.31` workaround dependency; track for cleanup once `surya-ocr` updates upstream.
- **Frontend accessibility (a11y) test infrastructure is not in CI.** The Svelte 5 component layer relies on a mix of `axe-core` recommendations and manual review; there is no `vitest-axe` or `@axe-core/playwright` dependency and no Playwright a11y spec in the `test.yml::e2e` job. The `F4.9` audit (Domain 4) flagged this; closing it is a separate track. Today, a button losing its accessible name silently lands without a regression test.

## Product-Planning Notes (scout plans, not code)

External scout plans live in `.mavis/plans/scout/`. The most recent
plan (2026-06-14) has four tracks plus a synthesis plan:

- `track-md.md` — Anything-to-Markdown / rich-text converter
  landscape (29 players: Microsoft / Google / Adobe / Apple / OSS).
  Headline finding: OSS has converged on three pipeline patterns
  (local-only / local+VLM / VLM-only) with OmniScribe in the
  defensible B-mode center; license posture (Marker's GPL+RAIL-M
  $2M cap, PyMuPDF4LLM AGPL) is a real B2B wedge; Docling's
  `StandardPdfPipeline` is the production reference for batch
  multi-stage threaded PDF processing.
- `track-schema-tables.md` — schema / table extraction landscape.
- `track-ocr-vision.md` — AI OCR / VLM landscape.
- `track-localdeepl.md` — internal architecture inventory.
- `PLAN.md` — synthesis of all four tracks (recommendations by
  extension point, sequenced roadmap).

Per-track changelogs (project-specific findings that should
survive into the post-scout roadmap) live in
`.mavis/plans/scout/changelogs/`. Generic research patterns
(fan-out, brief-correction) belong in agent memory, not here.

## See Also

- [README.md](README.md) — feature overview, install, web workspace
- [CHANGELOG.md](CHANGELOG.md) — version history and breaking changes
- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline, component map, and full API surface
- [DEPLOYMENT.md](DEPLOYMENT.md) — local / LAN / public-internet deployment profiles
- [SECURITY.md](SECURITY.md) — threat model, hardening checklist, vulnerability disclosure

_Last updated: 2026-08-19_
