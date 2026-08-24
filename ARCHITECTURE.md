# Architecture Ledger

## System Shape

`omniscribe` is a Python 3.11+ Web UI/API OCR application with a shared
pipeline behind the FastAPI server. Inputs are PDFs or images. Outputs are
searchable sandwich PDFs with normalized OCR bounding boxes embedded as an
invisible text layer.

## Pipeline

```text
PDF/image -> raster pages -> Surya detection (+ optional whitespace + text-layer recall) -> sparse: full-page VLM OCR -> DP alignment --+
                                      \-> dense: per-box VLM OCR -----------------------------------------------------------------------+-> optional refine -> optional quality repair -> optional post-process -> DocumentResult -> optional document processors -> searchable PDF

PDF/image -> grounded bbox-native VLM OCR -> optional quality repair -> optional post-process -> DocumentResult -> optional document processors -> searchable PDF
```

The optional whitespace-recall pass (`core/recall/whitespace.py`, hybrid path only,
default on, kill switch `OMNISCRIBE_WHITESPACE_RECALL`) merges conservative
pixel-statistics text-line candidates into the Surya boxes before dense
selection, OCR, and alignment. It fails open: any per-page error degrades to
the original Surya boxes.

The optional text-layer-recall pass (`core/recall/text_layer.py`, hybrid path
only, default on, kill switch `OMNISCRIBE_TEXT_LAYER_RECALL`) is the second
recall source: on digital PDFs it recovers lines Surya missed straight from
the embedded text layer (`page.get_text("words")`), merged after the
whitespace booster so its dedup sees both sources' extras. Scanned pages and
image inputs have no text layer, making the pass a strict no-op there. Same
fail-open contract: any per-page error degrades to the boxes merged so far,
and each pass logs one INFO run summary per job.

The HTTP layer mounts this pipeline through the plugin harness: `server.py`
loads `resources/cordis.yml` inside the FastAPI lifespan, and the `ocr`
plugin's `pipeline_bridge.py` assembles one `OCRPipeline` per upload
(shared Surya aligner singleton, request-scoped LLM coordinates).

## Plugin Tree

Boot order (from `resources/cordis.yml`; plugins apply top-to-bottom and
dispose LIFO on shutdown):

```text
cordis.yml
├─ runtime        RuntimeService: RuntimeSettings holder, readiness flag,
│                 artifact/channel prune cadence (HarnessReady event)
├─ logging        structured logging (text|json format, level) — side effect only
├─ state_backend  StateBackend service: memory (default) or sqlite
│                 (OMNISCRIBE_STATE_BACKEND); single registration site
├─ artifacts      ArtifactStore: opaque id/token blob store over the backend
├─ jobs           JobQueue: single-worker async queue + JobQueued/Started/
│                 Completed/Failed/Cancelled events; resolves the JobRunner
│                 the ocr plugin registers at claim time
├─ progress       ProgressService: one-shot session tokens, WS attach with
│                 cross-loop send marshaling; /api/progress/* + /ws/{channel_id}
├─ providers      provider catalog + model discovery (/api/providers*)
├─ health         liveness (/api/health, /api/healthz) and readiness (/ready, /readyz)
└─ ocr            OCRService + JobRunner; /api/process*, /api/jobs*, /api/config*,
                  SSE /api/process/{job_id}/events; seeds the quality-loop defaults
```

Every plugin declares a pydantic `Schema` for its config row; the Loader
validates the merged config (YAML row ← patch files ←
`OMNISCRIBE_PLUGIN_<ID>__<FIELD>` env overrides) before `apply`, so a bad
tree fails boot loud with `PluginLoadError`. Services are injected by
Protocol (`ctx.inject(JobQueue)`), never by module singleton.

## Directory Responsibilities

| Path | Single Responsibility |
| --- | --- |
| `src/omniscribe/__init__.py` | Lazy package-level public exports that avoid loading OCR or web dependencies during unrelated submodule imports |
| `src/omniscribe/server.py` | Lazy optional-web dependency loading, FastAPI application setup, CLI argument parsing for `--host/--port/--reload`, and `omniscribe-server` script entry point |
| `src/omniscribe/pipeline.py` | `OCRPipeline` facade — thin orchestration layer that delegates to `HybridEngine` or `GroundedEngine` based on injected components |
| `src/omniscribe/confidence_eval.py` | Package-root confidence evaluator: GLM-OCR fixture loader, greedy IoU matching, and per-document `ConfidenceReport` for the `scripts/confidence_*.py` tooling |
| `src/omniscribe/core/document.py` | Normalized `DocumentResult` IR, pages, blocks, spans, text aggregation, and legacy pages-data adapter |
| `src/omniscribe/core/processors/__init__.py` | Package-level re-exports for backward-compatible import of `DocumentProcessor`, `DocumentProcessorRegistry`, built-in processors, and helper functions |
| `src/omniscribe/core/processors/base.py` | Core `DocumentProcessor` protocol, `DocumentProcessorFactory`, `DocumentProcessorRegistry`, processor name lists, shared regexes, helper functions (`_structure_kind`, `_normalize_space`, `_page_region`, `_bbox_area`), `build_document_processors`, and `run_document_processors` |
| `src/omniscribe/core/processors/reading_order.py` | `ReadingOrderProcessor` — row-major block ordering based on normalized bounding box coordinates |
| `src/omniscribe/core/processors/quality.py` | `QualityAnalysisProcessor` — page-level OCR quality findings (empty pages, sparse text, large empty blocks) |
| `src/omniscribe/core/processors/structure.py` | `StructureAnalysisProcessor` — deterministic block structure hints (headings, list items, key-values, table candidates) |
| `src/omniscribe/core/processors/section.py` | `SectionAnalysisProcessor` — section heading detection and block grouping across page boundaries |
| `src/omniscribe/core/processors/layout.py` | `LayoutEnrichmentProcessor` — page region and layout role labeling (headers, footers, page numbers, figures, captions) |
| `src/omniscribe/core/processors/table.py` | `TableExtractionProcessor` — table grid structure extraction from aligned text blocks |
| `src/omniscribe/core/aligner.py` | Surya detection and DP text-to-box alignment |
| `src/omniscribe/core/recall/whitespace.py` | Whitespace recall booster — pixel-statistics text-line candidates merged into Surya detection on the hybrid path (`OMNISCRIBE_WHITESPACE_RECALL` kill switch, INFO run summary) |
| `src/omniscribe/core/recall/text_layer.py` | Text-layer recall source — lines Surya missed recovered from a digital PDF's embedded text layer; second box source merged after the whitespace booster (`OMNISCRIBE_TEXT_LAYER_RECALL` kill switch, INFO run summary, no-op for scans/images) |
| `src/omniscribe/core/ocr/` | OpenAI/Anthropic/Ollama multi-format VLM client, prompts, response filters, limits, exceptions, retry, and circuit-breaker resilience; `__init__.py` preserves the public import surface |
| `src/omniscribe/core/ocr_quality/` | OCR Quality Trust Layer — watermark detection, script detection, hallucination guard, Platt scaling calibration fit/eval, trust scorer, and orchestrator |
| `src/omniscribe/core/transcription/` | Speech-to-text audio transcription engines (local Whisper & OpenAI-compatible API backends) |
| `src/omniscribe/core/lexicon/` | LanceDB-backed canonical glossary / translation lexicon store (Protocol + LanceDB impl + embedding wrapper + helper queries + one-shot migration core). See `docs/lexicon-migration-spec.md`. |
| `src/omniscribe/core/glossary_sources/` | Terminology import parsers for TBX, CSV, JSON, and web URLs |
| `src/omniscribe/core/writers/tree_json.py` | Hierarchical block-tree export builder |
| `src/omniscribe/core/writers/exporter_base.py` | Thin `DocumentExportProtocol` + `BaseDocumentExporter` ABC. **Implementations are co-located with the writers they wrap** (DOCX in `core/writers/docx.py`, tree-DOCX in `core/writers/docx_tree.py`, HTML in `core/writers/html.py`) — the module ships only the abstraction, not the exporters. To add a new format, subclass `BaseDocumentExporter` in the same file as the existing writer, then register it on `PDFHandler` (or the relevant writer) |
| `src/omniscribe/core/writers/docx_tree.py` | Hierarchical block-tree to `.docx` converter |
| `src/omniscribe/core/writers/html.py` | Semantic HTML document writer from `DocumentResult` |
| `src/omniscribe/core/block_tree.py` | Hierarchical block-tree data structure and tree nodes |
| `src/omniscribe/core/pdf/__init__.py` | Package re-exports for `PDFHandler`, `DocumentResultWriter`, `IMAGE_EXTENSIONS`, `_emit_pymupdf_agpl_notice`, and public PDF symbols |
| `src/omniscribe/core/pdf/rasterizer.py` | PyMuPDF AGPL warning emission, safe DPI calculation, image extension validation, and PDF/image rasterization to JPEG/PNG base64 |
| `src/omniscribe/core/pdf/embedder.py` | Invisible text layer PDF rendering over rasterized backgrounds, normalized bbox coordinate transformations, and font sizing calculation |
| `src/omniscribe/core/pdf/handler.py` | `PDFHandler` class facade implementing `DocumentResultWriter` protocol for high-level workflow orchestration |
| `src/omniscribe/core/grounded/` | Grounded OCR models, prompted backend, rasterization, and bbox-native response parsers; `__init__.py` preserves the public import surface |
| `src/omniscribe/core/postprocess.py` | Dictionary-based spellcheck post-processing |
| `src/omniscribe/core/imaging/page_preprocess.py` | Local hybrid-path page preprocessing (orientation detection, deskew, denoise, contrast normalization, crop cleanup) |
| `src/omniscribe/core/imaging/handwriting.py` | Local handwriting image preprocessor for specialized handwriting pipeline paths |
| `src/omniscribe/core/ocr_quality/routing.py` | Quality routing recommendation metadata and policy recorder |
| `src/omniscribe/core/evaluation.py` | Lightweight `EvaluationMetrics` dataclass and `evaluate_document` helper for in-process processor result scoring |
| `src/omniscribe/core/writers/docx.py` | Markdown → `.docx` converter used by the docx export route |
| `src/omniscribe/core/translate/config.py` | Core-owned typed settings and optional-feature errors for async translation |
| `src/omniscribe/core/translate/workflow.py` | Optional LangGraph translation workflow |
| `src/omniscribe/core/workflows/base.py` | `EngineBase`, `OutputWriter`, `ProgressCallback`, `WarningCallback` shared by both engines |
| `src/omniscribe/core/workflows/hybrid.py` | `HybridEngine` — orchestrator delegating to specialized workflow stages |
| `src/omniscribe/core/workflows/stages/` | Decomposed hybrid workflow stages: `conversion.py` (`HybridConverter`), `layout.py` (`HybridLayoutDetector`), `ocr.py` (`HybridOcrRunner`), `refine.py` (`HybridRefiner`) |
| `src/omniscribe/core/workflows/grounded.py` | `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/omniscribe/core/workflows/repair.py` | `QualityRepairLoop` and `RepairOptions` — engine-agnostic block-level low-confidence re-OCR (stall guard, fail-open, `CircuitOpenError` re-raise) plus the job-level `quality_summary` aggregator |
| `src/omniscribe/core/workflows/utils.py` | Stand-alone workflow helper functions (`parse_page_range`, `_estimate_confidence`, `_decode_page_image`, `_normalize_for_dedup`, `_drop_refined_duplicates`, `_is_refinable`) and workflow constants (`REFINABLE_MIN_WIDTH`, `REFINABLE_MIN_HEIGHT`, `DETECT_CHUNK_SIZE`) |
| `src/omniscribe/core/workflows/__init__.py` | Re-exports `EngineBase`, `HybridEngine`, `GroundedEngine`, public helper `parse_page_range`, constants, and callback type aliases |
| `src/omniscribe/resources/dictionaries/` | Packaged compiled spellcheck dictionaries loaded before legacy repository-root dictionaries |
| `src/omniscribe/resources/calibration/` | Pre-trained model confidence calibration files (e.g. `qwen2_5_vl_72b.json`) |
| `src/omniscribe/core/ocr/multi_format_client.py` | Multi-format LLM completion dispatcher (`openai_compatible`, `anthropic_compatible`, `ollama_compatible`), vision base64 payloads, exponential backoff resilience retries, and timeout boundaries |
| `src/omniscribe/harness/` | Cordis-style plugin harness: `context.py` (Protocol-keyed services, LIFO effects, event bus, router queue), `loader.py` (YAML tree + patches + env overrides, fails loud), `plugin.py` (Plugin base), plus `errors.py`, `events.py`, `effects.py`, `service.py`, `config.py` |
| `src/omniscribe/plugins/` | The nine boot plugins (runtime, logging, state_backend, artifacts, jobs, progress, providers, health, ocr) that register services and mount every `/api` router; see the Plugin Tree section |
| `src/omniscribe/resources/cordis.yml` | Shipped plugin boot tree; patched via `OMNISCRIBE_CORDIS_PATCH` or `<artifact_dir>/cordis.patch.yml` |
| `src/omniscribe/utils/structured_logging.py` | Structured JSON logging formatter and handlers |
| `src/omniscribe/utils/prompt_safety.py` | Prompt injection detection and input sanitization |
| `src/omniscribe/utils/image.py` | Image crop, blank-region detection, and crop encoding helpers |
| `src/omniscribe/utils/security.py` | SSRF target validation |
| `src/omniscribe/utils/tqdm_patch.py` | Surya progress-bar suppression |
| `src/omniscribe/static/` | Built Svelte 5 workstation assets served by FastAPI |
| `frontend/` | Svelte 5 + Tailwind CSS v4 source, Vite configuration, and production build pipeline |
| `scripts/` | Repo-root developer utilities: confidence eval, fixture builder, debug/inspection scripts, bbox visualizers |
| `examples/` | Sample PDFs and images used by `tests/`, `e2e/test_ui.py`, and the confidence scripts |
| `tests/` | Unit, integration, security, and slow-path validation |
| `install.bat` / `install.ps1` | Windows one-click install: `uv` bootstrap, `uv sync --extra web --extra preprocessing`, Docker check, Desktop/Start-Menu shortcuts, post-install verification |
| `start_app.vbs` | Windows terminal launcher for Redis + Celery + uvicorn; writes a timestamped append log to `start_app.log` |
| `e2e/test_ui.py` | Headless Playwright smoke test against the running web UI |

## Extension Points

`OCRPipeline` accepts injected `aligner`, `ocr_processor`, `pdf_handler`,
`output_writer`, `grounded_backend`, and `document_processors` components. Keep
PDF and image inputs on the same output-writer path, and keep normalized bboxes
in `[x0, y0, x1, y1]` form until embedding.

Document processors receive a mutable `DocumentResult` after OCR cleanup,
spellcheck, and cross-page merge but before PDF embedding. The web/API surface
can select built-in local processors by name through `document_processors`.
The current six built-ins (in registration order) are `reading_order`,
`quality_analysis`, `structure_analysis`, `section_analysis`,
`layout_enrichment`, and `table_extraction`. Selection is off by default; the
list can be passed via `ConfigUpdate.document_processors` or the multipart OCR
`document_processors` field.

## Performance Notes

- Dense-mode and refine crop paths decode a page image once and reuse the PIL
  image across boxes.
- Grounded PDF rasterization converts PyMuPDF pixmaps directly into Pillow
  images before producing the final thumbnail JPEG.

## Shared State and Artifacts

All persistent and process-local state flows through the `StateBackend`
service registered by the `state_backend` plugin — no router touches a
module singleton. Two backends ship: `MemoryStateBackend` (default) and
`SQLiteStateBackend` (`OMNISCRIBE_STATE_BACKEND=sqlite`). The backend
covers three domains: artifacts, jobs, and progress channels.

The `artifacts` plugin layers an `ArtifactStore` on top: every artifact is
an opaque id + bearer token pair; sync `/api/process` returns them as
`X-Text-Artifact-Id` / `X-Text-Artifact-Token` headers, and async jobs
expose the same pair through `JobStatusResponse`. The metadata/export
artifact surfaces are deferred with the extraction routes.

### Background OCR lifecycle

`POST /api/process/async` validates and persists the upload before submitting
a payload to the single-worker `JobQueue` (`plugins/jobs.py`). The plugin
starts the worker at apply time and stops it during dispose. Observable HTTP
states are `pending`, `processing`, `complete`, and `error`; status is
available at `GET /api/process/status/{job_id}` and as an SSE replay at
`GET /api/process/{job_id}/events`. `POST /api/jobs/{job_id}/cancel` removes a
pending job or marks an in-flight job as a stable terminal error without
letting the runner's eventual return overwrite the cancellation. With the
memory backend queue and artifact indexes are lost on restart;
`OMNISCRIBE_STATE_BACKEND=sqlite` persists them.

### Authentication and runtime security

The historical ASGI security boundary (bearer auth via
`OMNISCRIBE_AUTH_TOKEN`, per-IP rate limiting, `Content-Length` upload
guard) was part of the removed `api/middleware/` package and is deferred in
the harness rebuild — the current route surface is unauthenticated and
intended for local trusted use only. Upload size is still enforced per
request by the `ocr` plugin (`max_upload_mb` plugin config, falling back to
`OMNISCRIBE_MAX_UPLOAD_MB`). Artifact reads remain token-bound.

## Web API Surface (non-exhaustive)

Rebuilt surface (pinned by `tests/openapi.json`):

| Method | Path | Plugin | Notes |
| --- | --- | --- | --- |
| `GET` / `POST` | `/api/config` | `ocr` | Read or update the shared runtime config store |
| `GET` / `PUT` | `/api/config/ocr` | `ocr` | OCR alias of the same store |
| `GET` | `/api/providers`, `/api/providers/{provider_id}`, `/api/providers/{provider_id}/models` | `providers` | Provider catalog and model discovery |
| `GET` | `/api/health`, `/api/healthz` | `health` | Liveness probes |
| `GET` | `/ready`, `/readyz` | `health` | Readiness probes (503 until the harness is ready) |
| `POST` | `/api/process` | `ocr` | Synchronous multipart OCR; PDF blob + artifact headers |
| `POST` | `/api/process/async` | `ocr` | Queue background OCR, returns `202` + job id |
| `GET` | `/api/process/status/{job_id}` | `ocr` | Background OCR lifecycle status |
| `GET` | `/api/process/{job_id}/events` | `ocr` | SSE replay of the job's lifecycle events |
| `GET` / `DELETE` | `/api/jobs` | `ocr` | Job list; `DELETE` clears all jobs |
| `GET` | `/api/jobs/{job_id}/result` | `ocr` | Token-bound result PDF download |
| `POST` | `/api/jobs/{job_id}/cancel` | `ocr` | Cancel pending/running job; terminal jobs are idempotent |
| `POST` | `/api/progress/session` | `progress` | Issue an opaque progress channel + one-shot session token |
| `POST` | `/api/progress/cancel/{channel_id}` | `progress` | Request cancellation for a progress channel |
| `WS` | `/ws/{channel_id}`, `/api/progress/ws/{channel_id}` | `progress` | Token-bound progress stream; auth via first `{"type":"auth",...}` frame (or `?token=`), then accepts `{"type":"cancel"}` |

Deferred in the harness rebuild (routes not mounted): `/api/models*`,
provider mutation routes (`POST/DELETE /api/providers*`),
`/api/text|metadata|export/*` artifact reads, `/api/export/*` builders,
`/api/translate*`, `/api/extract`, `/api/transcribe`, and
`/api/glossary*` — see the design spec's out-of-scope list.

## Change Blueprint

### 2026-08-20: Robust Multi-Format Model Discovery & 422 Request Resilience

Enhanced model discovery across `src/omniscribe/api/services/provider_manager.py`,
`src/omniscribe/api/routers/config.py`, and `src/omniscribe/api/routers/transcription.py`.
Introduced `extract_model_ids_from_response` supporting OpenAI standard, Ollama native
(`/api/tags`), Anthropic, OpenRouter, Together, top-level arrays, and custom formats.
Added candidate URL fallbacks (`/v1/models`, `/models`, `/api/tags`) for robust
compatibility with local servers (LM Studio, Ollama, vLLM, LocalAI) and remote endpoints.
Updated frontend `loadAppConfig` and `refreshModels` in `appStore.ts` to automatically
pull and populate all model namespaces (`general`, `ocr`, `translation`, `transcription`)
in parallel on application load and upon provider/namespace configuration updates.
Resolved HTTP 422 validation errors by:
- Allowing empty `api_key` in `ConfigUpdate` and defaulting empty `api_key` to `"lm-studio"` in `ProcessSettings` for local model backends.
- Accepting `document_processors` in `OcrConfigUpdate` (`POST /api/config/ocr`).
- Expanding `TranscriptionEngineType` to support `"faster-whisper"` and `"faster_whisper"`.
- Accepting nested namespace update objects in `ConfigUpdate` (`POST /api/config`).
- Aligning frontend namespace update calls in `appStore.ts` and `SettingsView.svelte` with dedicated API routes.
Added bidirectional `.env` preset synchronization:
- Implemented `update_dotenv` in `src/omniscribe/utils/env.py` to atomically update or insert `.env` variables while preserving comments and structure.
- Connected `ProviderManager.set_active_provider` and `_persist_config` to automatically sync `LLM_API_BASE`, `LLM_MODEL`, `LLM_API_KEY`, and OCR/translation settings to `.env`, `os.environ`, and `_config`.
- Updated `ProviderModal.svelte` so selecting catalog presets persists to backend active provider and `.env`.

### 2026-08-13: Quality repair loop (automatic low-confidence block retry)

`core/workflows/repair.py` adds an engine-agnostic `QualityRepairLoop`:
blocks whose estimated confidence is below `RepairOptions.target` are
re-OCR'd crop-scoped (hybrid reuses refine's crop primitive; grounded goes
through the backend's `ocr_crop`) up to `max_retries` times, accepting a
retry only while confidence strictly improves. Unexpected errors fail open
with the original text; `CircuitOpenError` is re-raised so the circuit
breaker stays authoritative. Both engines run repair sequentially after
block emission and before post-processing/embedding, so every downstream
stage sees the repaired text. `OCRPipeline.run` accepts `repair_options=`
(engines default off); `/api/process` defaults on with form fields
`quality_loop_enabled` / `quality_target` / `quality_max_retries` and env
seeds `OMNISCRIBE_QUALITY_LOOP` / `_TARGET` / `_MAX_RETRIES`. New
WebSocket frames: `block_retry`, `block_revised`, `quality_summary`;
progress accounting reuses the `refine` stage band.

### 2026-08-02: Canonical `/api` aliases and background OCR reliability

The Svelte workstation uses `/api/...` as its canonical HTTP contract. Legacy
prefix-less OCR and artifact paths remain registered against the same handler
objects so existing integrations continue to work without maintaining duplicate
implementations. The obsolete `api/routers/ai.py` module is removed; translation
and extraction routers use the single-purpose `api/services/ai.py` service.
Added the single-worker OCR queue to `LocalStateBackend`, wired
its start/stop lifecycle to FastAPI lifespan, exposed async submit/status/cancel
routes, and preserved cancellation as a terminal state when a runner winds down.
The WebSocket contract is `/ws/{channel_id}`: the session token is
presented in the first inbound frame (`{"type":"auth","session_token":...}`),
never in the URL. Progress sessions are
issued by `POST /api/progress/session`.

| Area | Canonical route | Compatibility route |
| --- | --- | --- |
| Synchronous OCR | `POST /api/process` | `POST /process` |
| Background OCR | `POST /api/process/async` | `POST /process/async` |
| OCR status | `GET /api/process/status/{job_id}` | `GET /process/status/{job_id}` |
| Text artifact | `GET /api/text/{artifact_id}` | `GET /text/{artifact_id}` |
| Metadata artifact | `GET /api/metadata/{artifact_id}` | `GET /metadata/{artifact_id}` |
| Export artifact | `GET /api/export/{artifact_id}` | `GET /export/{artifact_id}` |

### 2026-07-25: Core PDF Decomposition into `src/omniscribe/core/pdf/` Package

Refactored `src/omniscribe/core/pdf.py` (~18 KB) into a clean, single-responsibility subpackage `src/omniscribe/core/pdf/`. Separated PyMuPDF/image rasterization, safe DPI calculations, and image extension handling into `rasterizer.py`, invisible text layer rendering, font sizing, and coordinate transformation into `embedder.py`, and high-level workflow orchestration into `handler.py`. Preserved 100% backward compatibility via `__init__.py` re-exports for `PDFHandler`, `DocumentResultWriter`, `IMAGE_EXTENSIONS`, `_emit_pymupdf_agpl_notice`, and all public/internal symbols.

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/pdf/rasterizer.py` | PyMuPDF AGPL warning emission, safe DPI calculation, image extension validation, and PDF/image rasterization to JPEG/PNG base64 |
| `src/omniscribe/core/pdf/embedder.py` | Invisible text layer PDF rendering over rasterized backgrounds, normalized bbox coordinate transformations, and font sizing calculation |
| `src/omniscribe/core/pdf/handler.py` | `PDFHandler` class facade implementing `DocumentResultWriter` protocol for high-level workflow orchestration |
| `src/omniscribe/core/pdf/__init__.py` | Re-exports `PDFHandler`, `DocumentResultWriter`, `IMAGE_EXTENSIONS`, `_emit_pymupdf_agpl_notice`, and public PDF symbols |

### 2026-07-25: Refactor stand-alone workflow helpers into `core/workflows/utils.py`

Extracted stand-alone helper functions (`parse_page_range`, `_estimate_confidence`, `_decode_page_image`, `_normalize_for_dedup`, `_drop_refined_duplicates`, `_is_refinable`) and constants (`REFINABLE_MIN_WIDTH`, `REFINABLE_MIN_HEIGHT`, `DETECT_CHUNK_SIZE`) out of `hybrid.py` into `omniscribe.core.workflows.utils`. Re-exported public helpers in `omniscribe.core.workflows.__init__.py` and maintained backward compatibility in `hybrid.py`.

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/workflows/utils.py` | Stand-alone workflow helper functions and constants |
| `src/omniscribe/core/workflows/hybrid.py` | Imports and uses `omniscribe.core.workflows.utils` while re-exporting helpers |
| `src/omniscribe/core/workflows/__init__.py` | Re-exports public workflow helpers (`parse_page_range`, constants) |

### 2026-07-25: LiteLLM Cleanup, Handwriting Preprocessing, and DocuVerse CSS UI System

Streamlined provider selection by replacing `litellm_provider.py` with direct OpenAI-compatible client integration in `llm/client.py` and `ocr/processor.py`. Added dedicated `handwriting_preprocessor.py` module. Fully overhauled the frontend interface with the DocuVerse CSS Design System featuring dual theme options (dark/light), glassmorphism, responsive control sidebars, interactive modals, and dynamic notification toasts.

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/imaging/handwriting.py` | Local handwriting image preprocessor |
| `src/omniscribe/core/llm/client.py` | Direct OpenAI-compatible VLM client integration and resilience handlers |
| `src/omniscribe/static/css/` | DocuVerse CSS system (`variables.css`, `layout.css`, `components.css`, `workspace.css`, `modals.css`) |
| `src/omniscribe/static/index.html` | Restructured workstation layout with theme toggle, floating control dock, and modal system |
### 2026-07-13: God-module decomposition — `core/ocr/`, `core/grounded/`, `api/services/ocr_*.py`

A four-phase decomposition targeted the two largest god-modules in the
codebase (`core/ocr.py` and `core/grounded.py`) and the
~1000-line `api/routers/ocr.py` that was accumulating responsibilities.

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/ocr/__init__.py` | Re-exports the public OCR surface (`OCRProcessor`, helpers, prompts) for backwards compatibility |
| `src/omniscribe/core/ocr/processor.py` | LiteLLM-backed `OCRProcessor.run` and per-page retry/filter orchestration |
| `src/omniscribe/core/ocr/prompts.py` | System + user prompt templates, OCR-specific limits, response filters |
| `src/omniscribe/core/grounded/__init__.py` | Re-exports the grounded OCR backend, models, parsers, and hosted adapters |
| `src/omniscribe/core/grounded/models.py` | Grounded block/response models and backend protocol |
| `src/omniscribe/core/grounded/prompted.py` | Prompted and hosted grounded OCR backends |
| `src/omniscribe/core/grounded/parsers.py` | Bbox-native JSON response parsers and axis-order normalization |
| `src/omniscribe/core/grounded/rasterize.py` | Grounded PDF/image rasterization helpers |
| `src/omniscribe/api/services/ocr/settings.py` | Form-parameter resolution for `POST /api/process` |
| `src/omniscribe/api/services/ocr/pipeline_factory.py` | Pipeline construction and backend-model verification for `POST /api/process` |
| `src/omniscribe/api/services/ocr/response.py` | Response assembly, validation-error envelopes, and `FileResponse` construction with token-bound headers |
| `src/omniscribe/api/routers/ocr.py` | Shrunk to a thin orchestrator that just chains the services above |
| `tests/api/routers/test_ocr_thread_bridge.py` | Patches updated to point at `api.services.ocr.pipeline_factory.*` instead of `api.routers.ocr.*` (formerly the monolithic API-safety suite) |
| `ARCHITECTURE.md` | Directory table updated to reflect the four new service modules and the corrected `ai.py` role |

Why a service module per concern (vs. expanding the router): each new
service has a single responsibility (resolve → assemble → respond),
maps to a single source-of-truth, and is independently testable. The
router stays declarative — the route body only orchestrates calls into
the three services.

### 2026-06-14: Engine split — `core/workflows/` package

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/workflows/base.py` | New `EngineBase` plus `OutputWriter`, `ProgressCallback`, `WarningCallback`, and `_notify` helpers shared by both engines |
| `src/omniscribe/core/workflows/hybrid.py` | New `HybridEngine` — extract the existing hybrid orchestration from `pipeline.py` (Surya detect → VLM OCR → DP align → refine → post-process → processors → output) |
| `src/omniscribe/core/workflows/grounded.py` | New `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/omniscribe/core/workflows/__init__.py` | Re-export the engines and callback aliases |
| `src/omniscribe/pipeline.py` | Shrink `OCRPipeline` to a facade that picks `HybridEngine` or `GroundedEngine` based on injected components |
| `ARCHITECTURE.md` | Document the new sub-package and the facade pattern in `pipeline.py` |

### 2026-06-14: DOCX export route + `core/writers/docx.py`

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/writers/docx.py` | New `convert_markdown_to_docx(markdown_text: str) -> io.BytesIO` helper |
| `src/omniscribe/api/schemas/requests.py` | New `ExportDocxRequest` typed schema |
| `src/omniscribe/api/routers/extraction.py` | New `POST /api/export/docx` route that streams the generated `.docx` |
| `pyproject.toml` | Already lists `python-docx>=1.1.0` (no change required) |
| `ARCHITECTURE.md` | Document the docx export in the directory table and the Web API surface |

### 2026-06-14: Confidence evaluation scripts and root-level `confidence_eval.py`

| File | Responsibility |
| --- | --- |
| `src/omniscribe/confidence_eval.py` | New package-root module: `GTBlock`, `BlockMatch`, `ConfidenceReport`, `load_ground_truth`, `text_similarity`, `compute_report`, `iou` (auto-detects `[x0,y0,x1,y1]` vs `[y0,x0,y1,x1]` fixture axis order) |
| `scripts/confidence_eval.py` | New developer script — runs hybrid and grounded paths against `examples/*.pdf` and reports per-document block recall, IoU, and text similarity |
| `scripts/confidence_image.py` | New developer script — same comparison on a single image, defaults to `examples/image.avif` |
| `examples/` | New sample inputs (`dense.pdf`, `digital.pdf`, `handwritten.pdf`, `hybrid.pdf`, `image.png`, `image.avif`, `notes.pdf`) |
| `tests/core/test_evaluation.py` | Cover fixture loading, axis-order detection, and `ConfidenceReport` aggregation |
| `ARCHITECTURE.md` | Document the root-level confidence eval vs the lightweight `core/evaluation.py` |

### 2026-06-14: `POST /api/extract` and `ExtractionTemplate` enum

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/schemas/requests.py` | New `ExtractionTemplate` StrEnum (`invoice`, `resume`, `academic`, `custom`) and the `ExtractionRequest` model with `template` and `custom_prompt` fields |
| `src/omniscribe/api/routers/ai.py` | New `extract_structured_data` service with fenced-JSON parsing, retry, and stable error mapping |
| `src/omniscribe/api/routers/extraction.py` | New router that wires the schema, the AI service, and the SSRF guard for `api_base` |
| `tests/api/routers/test_extraction_translation_routers.py` | Cover template dispatch, custom-prompt fallback, and SSRF fail-closed behavior |
| `ARCHITECTURE.md` | Document the new router and the four extraction templates in the Web API surface |

### 2026-06-09: Local document processors exposed to web/API

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/document.py` | Provide the normalized `DocumentResult` handoff used by post-OCR document processors |
| `src/omniscribe/core/processors.py` | Define built-in local processors and map user-facing names to deterministic processor instances |
| `src/omniscribe/api/schemas/requests.py` | Validate `document_processors` for config JSON and multipart OCR requests |
| `src/omniscribe/api/routers/ocr.py` | Instantiate selected processors, pass them into `OCRPipeline`, and expose quality metadata through `X-Document-Quality` when available |
| `src/omniscribe/static/js/state_and_api.js` | Persist and submit web-selected document processors |
| `src/omniscribe/static/index.html` | Expose Reading Order, Quality Analysis, Structure Analysis, and Section Analysis toggles in Advanced Configuration |
| `tests/api/services/test_document_processor_selection.py` | Cover processor selection parsing, validation, and factory mapping |

### 2026-06-09: Stage 2 local structure analysis processor

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors.py` | Add `structure_analysis`, a deterministic local processor that classifies blocks as headings, paragraphs, list items, key-values, table candidates, or empty blocks |
| `src/omniscribe/api/routers/ocr.py` | Expose page-level structure summaries through `X-Document-Structure` when structure metadata is present |
| `src/omniscribe/static/index.html` | Add the Structure Analysis opt-in control |
| `tests/core/test_document.py` | Cover block classification without rewriting output text |

### 2026-06-09: Stage 3 local section analysis processor

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors.py` | Add `section_analysis`, a deterministic local processor that assigns blocks to detected heading sections across page boundaries |
| `src/omniscribe/api/routers/ocr.py` | Expose page-level section summaries through `X-Document-Sections` when section metadata is present |
| `src/omniscribe/static/index.html` | Add the Section Analysis opt-in control |
| `tests/core/test_document.py` | Cover section grouping while preserving original block text |

### 2026-06-09: Stage 4 document metadata artifact surface

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/document_metadata.py` | Build compact JSON-safe metadata reports from `DocumentResult` page/block processor annotations and write them atomically as temporary artifacts |
| `src/omniscribe/api/routers/ocr.py` | Issue `X-Document-Metadata-Artifact-Id` and `X-Document-Metadata-Artifact-Token` only when report content exists, and serve protected `GET /metadata/{artifact_id}` |
| `tests/api/routers/test_artifacts.py` | Cover token-bound metadata artifact access and payload shape without changing text artifact behavior (formerly the monolithic API-safety suite) |

### 2026-06-09: Stage 5-12 Web/API document intelligence

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Deprecate the user-facing `omniscribe` CLI script and drop the CLI-only `rich` dependency; keep `omniscribe-server`. `OCRPipeline` is still importable for in-process programmatic use. |
| `src/omniscribe/core/imaging/page_preprocess.py` | Add opt-in local page preprocessing diagnostics for the hybrid image path |
| `src/omniscribe/core/processors.py` | Add `layout_enrichment` and `table_extraction` deterministic processors |
| `src/omniscribe/api/services/document_exports.py` | Add token-bound JSON, Markdown, text, Docling-compatible, and MinerU-compatible exports |
| `src/omniscribe/core/ocr_quality/routing.py` | Record default-off quality routing recommendations in document metadata |
| `src/omniscribe/api/services/workflow.py` | Expose deterministic Web/API workflow summaries |
| `src/omniscribe/core/evaluation.py` | Add local evaluation metrics for text, bbox, reading-order, and table coverage |

### 2026-06-02: Direct grounded PDF pixmap conversion

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/grounded/rasterize.py` | Convert PDF pixmaps directly into Pillow images before emitting the final grounded OCR thumbnail JPEG |
| `tests/core/grounded/test_grounded.py` | Guard against restoring the redundant intermediate JPEG decode |
| `ARCHITECTURE.md` | Record the existing module layout and the direct pixmap conversion invariant |

### 2026-06-02: Stage 1 API and browser safety hardening

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/schemas/requests.py` | Validate config JSON, OCR multipart settings, translation requests, and extraction requests with explicit enums, booleans, and numeric ranges |
| `src/omniscribe/api/services/uploads.py` | Enforce streaming upload byte limits, content-signature upload type detection, stable API error messages, and server-issued text artifact IDs |
| `src/omniscribe/api/routers/config.py` | Apply typed config validation, SSRF checks, safe environment parsing, and non-leaking model discovery errors |
| `src/omniscribe/api/routers/ocr.py` | Apply typed OCR/AI boundary validation, hardened upload dispatch, opaque text artifact retrieval, SSRF checks, and stable client-facing errors |
| `src/omniscribe/utils/security.py` | Fail closed for malformed, unsupported, or unresolvable URLs and only allow local/private endpoints when `ALLOW_SSRF_LOCAL=true` is explicitly set |
| `src/omniscribe/static/js/app.js` | Use server-issued text artifact IDs and render extraction status/errors/cards without HTML injection |
| `src/omniscribe/static/js/state_and_api.js` | Build model select placeholder with DOM APIs before appending model-controlled option text |
| `src/omniscribe/static/js/workspace_ui.js` | Provide safe DOM helpers for clearing elements and rendering extraction status cards |
| `tests/utils/test_ssrf.py`, `tests/api/services/test_uploads.py`, `tests/api/routers/test_artifacts.py`, `tests/api/routers/test_process_routes.py` | Cover config validation, SSRF fail-closed behavior, streaming upload validation, opaque text artifacts, stable API errors, and static JS sink removal (formerly the monolithic API-safety suite) |
| `tests/api/middleware/test_security_qa.py` | Keep extraction JSON parsing deterministic under fail-closed SSRF validation |

### 2026-06-03: Optional async translation boundary

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/translate/config.py` | Own typed translation settings and the deterministic optional-feature error used by core and API boundaries |
| `src/omniscribe/core/translate/workflow.py` | Keep chunking and evaluation helpers importable without async extras, lazily build the LangGraph workflow, and accept injected translation settings |
| `src/omniscribe/api/routers/config.py` | Adapt the mutable web runtime config into core-owned translation settings without exposing `_config` to core modules |
| `src/omniscribe/api/celery_app.py` | Guard Celery imports and provide an import-safe fallback task facade when async extras are not installed |
| `src/omniscribe/api/tasks.py` | Validate async translation task inputs and pass explicit translation settings into the core workflow |
| `src/omniscribe/api/routers/ocr.py` | Validate async translation route inputs and return deterministic 503 responses when optional async extras are unavailable |
| `pyproject.toml` | Move Celery, Redis, LangGraph, ChromaDB, and sentence-transformers into the `async-translation` extra with `translation` as an alias extra |
| `tests/core/translate/test_translation_boundary.py` | Cover guarded imports without async extras and explicit translation settings injection |

### 2026-06-03: Spellcheck resource package cleanup

| File | Responsibility |
| --- | --- |
| `src/omniscribe/resources/dictionaries/ara.json.gz` | Packaged Arabic compiled spellcheck dictionary for installed distributions |
| `src/omniscribe/resources/dictionaries/eng.json.gz` | Packaged English compiled spellcheck dictionary for installed distributions |
| `src/omniscribe/core/postprocess.py` | Load packaged dictionaries first while retaining legacy repository-root and user-cache fallbacks |
| `pyproject.toml` | Exclude bytecode cache artifacts from Hatch package builds |
| `tests/core/test_dictionary_postprocess.py` | Cover packaged dictionary lookup and legacy repository-root fallback |

### 2026-06-03: Lazy web server imports

| File | Responsibility |
| --- | --- |
| `src/omniscribe/__init__.py` | Preserve package-level OCR exports through lazy lookups so `import omniscribe.server` does not load OCR core dependencies first |
| `src/omniscribe/server.py` | Preserve `omniscribe.server:app` and `omniscribe.server:main` while deferring FastAPI, router, static-file, and uvicorn imports until the web app is created or run |
| `tests/api/test_server_lazy_imports.py` | Verify base-install-safe `omniscribe.server` imports and deterministic missing-web-extra errors without uninstalling FastAPI |
| `ARCHITECTURE.md` | Record the optional-web lazy import boundary for the server module |

### 2026-08-02: Quality Audit & YAGNI Improvements

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/workflows/hybrid.py` | Re-raise `CircuitOpenError` explicitly in crop/box OCR exception handlers to prevent swallowing endpoint failures |
| `src/omniscribe/core/grounded/prompted.py` | Offload grounded PIL crop and PNG buffer generation to thread pool via `asyncio.to_thread` |
| `src/omniscribe/api/routers/ocr.py` | Handle `asyncio.CancelledError` on client disconnect without logging 500 stack traces, and wrap file cleanup calls in `asyncio.to_thread` |
| `src/omniscribe/api/services/uploads.py` | Add parent directory confinement check in `cleanup_files` to ensure deleted paths reside in temporary storage |
| `frontend/src/lib/components/workstation/RightControlDock.svelte` | Add `role="button"`, `tabindex="0"`, and `onkeydown` keyboard trigger to target document drop zone for accessibility compliance |
| `frontend/src/lib/components/workstation/BottomProgressDock.svelte` | Rename outer container ID to `workstation-progress-dock` to eliminate duplicate DOM ID conflicts |

### 2026-08-11: Industry-Standards Audit Implementation (P1 & Quick Wins)

| File | Responsibility |
| --- | --- |
| `.github/dependabot.yml` | Dependabot configuration for `pip` and `github-actions` ecosystems with weekly schedule |
| `.github/workflows/test.yml` | Add `pip-audit` vulnerability scan, `pytest-cov` test coverage reporting, and CycloneDX SBOM artifact generation |
| `pyproject.toml` | Add `pytest-cov`, `pip-audit`, and `cyclonedx-python-lib` to `dependency-groups.dev` |
| `.pre-commit-config.yaml` | Sync `ruff-pre-commit` version to `v0.9.0` |
| `AGENTS.md` | Document `surya-ocr` `requests>=2.31` workaround follow-up and `live_llm` manual test run instructions (workaround closed in audit-secondary Phase 5 — see Known Tech Debt) |

### 2026-08-11: Goose-Style Multi-Provider API Handling Architecture

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/provider_manager.py` | `ProviderManager` service with 11-provider catalog templates, system environment variable auto-discovery (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_HOST`, etc.), disk persistence to `~/.config/omniscribe/providers.yaml`, active provider switching, and model listing dispatch |
| `src/omniscribe/core/ocr/multi_format_client.py` | Multi-format LLM completion dispatcher supporting `openai_compatible`, `anthropic_compatible`, and `ollama_compatible` formats with exponential backoff retries and timeout boundaries |
| `src/omniscribe/api/routers/providers.py` | Goose-style provider management API routes (`/api/providers`, `/api/providers/templates`, `/api/providers/active`, `/api/providers/{provider_id}/models`) |
| `src/omniscribe/api/schemas/requests.py` | `ProviderFormatEnum`, `ProviderConfig`, `ProviderTemplate`, `ActiveProviderUpdate`, `ProviderCreateRequest` schemas |
| `src/omniscribe/core/llm/client.py` | Directs VLM/LLM completion calls through `ocr/multi_format_client.py` based on active provider configuration |
| `src/omniscribe/api/routers/config.py` | Connects `/api/models` discovery endpoints to `ProviderManager` |
| `tests/api/services/test_provider_manager.py` | Unit tests for provider configuration manager, env-var discovery, and persistence |
| `tests/api/test_multi_format_client.py` | Unit tests for OpenAI, Anthropic, and Ollama multi-format completion execution |
| `tests/api/routers/test_provider_api_routes.py` | Unit tests for provider REST management API routes |


### 2026-08-12: Full Svelte 5 + TailwindCSS v4 Frontend Migration & Legacy Cleanup

| File | Responsibility |
| --- | --- |
| `frontend/vite.config.ts` | Configured Svelte 5 + Tailwind v4 build pipeline outputting directly to `src/omniscribe/static` and setting `conditions: ['browser']` for Vitest browser mode testing |
| `frontend/package.json` | Updated project package name to `omniscribe-frontend` |
| `frontend/src/lib/components/ui/Badge.svelte` | Exported `BadgeVariant` type in module context, added `title` prop binding, and supported `class` / `className` props |
| `frontend/src/lib/components/ui/Card.svelte` | Supported standard `class` and legacy `className` props seamlessly |
| `frontend/src/lib/components/ui/Input.svelte` | Fixed HTML `autocomplete` property type casting |
| `frontend/src/lib/components/workstation/MetadataPanel.svelte` | Fixed `BadgeVariant` type assertion and updated component property bindings |
| `frontend/src/lib/components/views/GlossaryView.svelte` | Fixed string casting on dictionary term target properties |
| `frontend/src/lib/components/views/SettingsView.svelte` | Converted component property bindings to standard `class` props |
| `frontend/src/lib/components/views/ExtractionView.svelte` | Converted component property bindings to standard `class` props |
| `frontend/src/lib/components/views/JobHistoryView.svelte` | Updated `BadgeVariant` import and converted component property bindings to standard `class` props |
| `frontend/src/lib/components/views/TranscriptionView.svelte` | Converted component property bindings to standard `class` props |
| `frontend/src/lib/components/modals/ExportModal.svelte` | Fixed `tagVariant` type annotations and converted property bindings to standard `class` props |
| `src/omniscribe/static/` | Compiled production Svelte 5 + Tailwind v4 single-page application assets served by FastAPI |

### 2026-08-14: Multi-Domain Architecture, Security & Quality Audit

Conducted a comprehensive 4-domain audit (Core Pipeline, Backend API/Security, Frontend Workstation, and QA/DevOps):
1. **Core Pipeline**: Confirmed normalized `[0..1]` bounding box invariant, monotonic DP alignment, cooperative cancellation via `OCRCancelled` (`BaseException`), bounded 16-entry image LRU cache, and quality repair loop stall guards. Identified `complete_vlm_prompt` export omission in `core/ocr/__init__.py` and `DocumentTree` child index desync on reading order sort.
2. **API & Security**: Identified and cataloged readiness probe fix (`OCRJobQueue.running` property), third-party provider API key response masking, artifact token separation from server bearer authentication, and uniform SSRF validation on tree translation and transcription endpoints.
3. **Frontend Workstation**: Verified Svelte 5 + TypeScript build and Vitest suite (17/17 passed). Identified unmounted navigation views (`JobHistoryView`, `TranscriptionView`, `ExtractionView`) in `App.svelte` and modal focus trapping requirements.
4. **QA & DevOps**: Executed full test and lint suites (1,230 fast tests passing in 37.9s, 0 Ruff errors, 0 format issues, 144 source files clean in Mypy strict mode). Cataloged missing dev CI dependencies in `pyproject.toml` (`pytest-cov`, `pip-audit`, `cyclonedx-python-lib`, `rich`) and frontend CI job integration.

### 2026-08-14: CI Frontend Build & Test Wiring Hardening

| File | Responsibility |
| --- | --- |
| `.github/workflows/test.yml` | Integrated Node.js v20 setup, frontend dependency installation, checks/tests (`svelte-check` + `vitest`), and frontend production build prior to Python test execution |
| `.github/workflows/release.yml` | Added frontend build step before `uv build` packaging so release wheels contain compiled frontend assets |
| `tests/api/routers/test_static_wiring.py` | Added graceful skip guards for when frontend static assets have not yet been built locally |

### 2026-08-14: Core Dependencies Update (Redis & ChromaDB)

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Promoted `redis>=5.0.0` and `chromadb>=0.5.0` to core `[project.dependencies]` so Celery distributed backend state and vector lexicon RAG support are packaged out-of-the-box |

### 2026-08-14: Full Dependency Modernization & Security Audit Resolution

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Upgraded `surya-ocr>=0.22.1`, bounded `openai>=2.11.0,<3`, pinned `numpy<2.3.0` for Python 3.11 typing stub compatibility, removed unmaintained `comet` (`unbabel-comet`) extra to unblock modern `transformers 5.x` and `huggingface-hub>=1.5.0`, and locked `redis>=5.0.0` and `chromadb>=0.5.0` |
| `uv.lock` | Updated 220 resolved packages across runtime, upgrading `transformers` (v4.57.6 -> v5.15.0), `protobuf` (v4.25.9 -> v7.35.1), `huggingface-hub` (v0.36.2 -> v1.27.0), `pypdfium2` (v4.30.0 -> v5.13.0), resolving 45 of 46 known `pip-audit` security advisories |
| `src/omniscribe/core/translate/nllb.py` | Adapted HuggingFace pipeline and tokenizer typing for `transformers` 5.x |

### 2026-08-18: Comprehensive 5-Domain Multi-Agent Codebase Audit

| `src/omniscribe/api/routers/extraction.py` | New router that wires the schema, the AI service, and the SSRF guard for `api_base` |
| `tests/api/routers/test_extraction_translation_routers.py` | Cover template dispatch, custom-prompt fallback, and SSRF fail-closed behavior |
| `ARCHITECTURE.md` | Document the new router and the four extraction templates in the Web API surface |

### 2026-06-09: Local document processors exposed to web/API

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/document.py` | Provide the normalized `DocumentResult` handoff used by post-OCR document processors |
| `src/omniscribe/core/processors.py` | Define built-in local processors and map user-facing names to deterministic processor instances |
| `src/omniscribe/api/schemas/requests.py` | Validate `document_processors` for config JSON and multipart OCR requests |
| `src/omniscribe/api/routers/ocr.py` | Instantiate selected processors, pass them into `OCRPipeline`, and expose quality metadata through `X-Document-Quality` when available |
| `src/omniscribe/static/js/state_and_api.js` | Persist and submit web-selected document processors |
| `src/omniscribe/static/index.html` | Expose Reading Order, Quality Analysis, Structure Analysis, and Section Analysis toggles in Advanced Configuration |
| `tests/api/services/test_document_processor_selection.py` | Cover processor selection parsing, validation, and factory mapping |

### 2026-06-09: Stage 2 local structure analysis processor

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors.py` | Add `structure_analysis`, a deterministic local processor that classifies blocks as headings, paragraphs, list items, key-values, table candidates, or empty blocks |
| `src/omniscribe/api/routers/ocr.py` | Expose page-level structure summaries through `X-Document-Structure` when structure metadata is present |
| `src/omniscribe/static/index.html` | Add the Structure Analysis opt-in control |
| `tests/core/test_document.py` | Cover block classification without rewriting output text |

### 2026-06-09: Stage 3 local section analysis processor

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors.py` | Add `section_analysis`, a deterministic local processor that assigns blocks to detected heading sections across page boundaries |
| `src/omniscribe/api/routers/ocr.py` | Expose page-level section summaries through `X-Document-Sections` when section metadata is present |
| `src/omniscribe/static/index.html` | Add the Section Analysis opt-in control |
| `tests/core/test_document.py` | Cover section grouping while preserving original block text |

### 2026-06-09: Stage 4 document metadata artifact surface

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/document_metadata.py` | Build compact JSON-safe metadata reports from `DocumentResult` page/block processor annotations and write them atomically as temporary artifacts |
| `src/omniscribe/api/routers/ocr.py` | Issue `X-Document-Metadata-Artifact-Id` and `X-Document-Metadata-Artifact-Token` only when report content exists, and serve protected `GET /metadata/{artifact_id}` |
| `tests/api/routers/test_artifacts.py` | Cover token-bound metadata artifact access and payload shape without changing text artifact behavior (formerly the monolithic API-safety suite) |

### 2026-06-09: Stage 5-12 Web/API document intelligence

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Deprecate the user-facing `omniscribe` CLI script and drop the CLI-only `rich` dependency; keep `omniscribe-server`. `OCRPipeline` is still importable for in-process programmatic use. |
| `src/omniscribe/core/imaging/page_preprocess.py` | Add opt-in local page preprocessing diagnostics for the hybrid image path |
| `src/omniscribe/core/processors.py` | Add `layout_enrichment` and `table_extraction` deterministic processors |
| `src/omniscribe/api/services/document_exports.py` | Add token-bound JSON, Markdown, text, Docling-compatible, and MinerU-compatible exports |
| `src/omniscribe/core/ocr_quality/routing.py` | Record default-off quality routing recommendations in document metadata |
| `src/omniscribe/api/services/workflow.py` | Expose deterministic Web/API workflow summaries |
| `src/omniscribe/core/evaluation.py` | Add local evaluation metrics for text, bbox, reading-order, and table coverage |

### 2026-06-02: Direct grounded PDF pixmap conversion

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/grounded/rasterize.py` | Convert PDF pixmaps directly into Pillow images before emitting the final grounded OCR thumbnail JPEG |
| `tests/core/grounded/test_grounded.py` | Guard against restoring the redundant intermediate JPEG decode |
| `ARCHITECTURE.md` | Record the existing module layout and the direct pixmap conversion invariant |

### 2026-06-02: Stage 1 API and browser safety hardening

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/schemas/requests.py` | Validate config JSON, OCR multipart settings, translation requests, and extraction requests with explicit enums, booleans, and numeric ranges |
| `src/omniscribe/api/services/uploads.py` | Enforce streaming upload byte limits, content-signature upload type detection, stable API error messages, and server-issued text artifact IDs |
| `src/omniscribe/api/routers/config.py` | Apply typed config validation, SSRF checks, safe environment parsing, and non-leaking model discovery errors |
| `src/omniscribe/api/routers/ocr.py` | Apply typed OCR/AI boundary validation, hardened upload dispatch, opaque text artifact retrieval, SSRF checks, and stable client-facing errors |
| `src/omniscribe/utils/security.py` | Fail closed for malformed, unsupported, or unresolvable URLs and only allow local/private endpoints when `ALLOW_SSRF_LOCAL=true` is explicitly set |
| `src/omniscribe/static/js/app.js` | Use server-issued text artifact IDs and render extraction status/errors/cards without HTML injection |
| `src/omniscribe/static/js/state_and_api.js` | Build model select placeholder with DOM APIs before appending model-controlled option text |
| `src/omniscribe/static/js/workspace_ui.js` | Provide safe DOM helpers for clearing elements and rendering extraction status cards |
| `tests/utils/test_ssrf.py`, `tests/api/services/test_uploads.py`, `tests/api/routers/test_artifacts.py`, `tests/api/routers/test_process_routes.py` | Cover config validation, SSRF fail-closed behavior, streaming upload validation, opaque text artifacts, stable API errors, and static JS sink removal (formerly the monolithic API-safety suite) |
| `tests/api/middleware/test_security_qa.py` | Keep extraction JSON parsing deterministic under fail-closed SSRF validation |

### 2026-06-03: Optional async translation boundary

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/translate/config.py` | Own typed translation settings and the deterministic optional-feature error used by core and API boundaries |
| `src/omniscribe/core/translate/workflow.py` | Keep chunking and evaluation helpers importable without async extras, lazily build the LangGraph workflow, and accept injected translation settings |
| `src/omniscribe/api/routers/config.py` | Adapt the mutable web runtime config into core-owned translation settings without exposing `_config` to core modules |
| `src/omniscribe/api/celery_app.py` | Guard Celery imports and provide an import-safe fallback task facade when async extras are not installed |
| `src/omniscribe/api/tasks.py` | Validate async translation task inputs and pass explicit translation settings into the core workflow |
| `src/omniscribe/api/routers/ocr.py` | Validate async translation route inputs and return deterministic 503 responses when optional async extras are unavailable |
| `pyproject.toml` | Move Celery, Redis, LangGraph, ChromaDB, and sentence-transformers into the `async-translation` extra with `translation` as an alias extra |
| `tests/core/translate/test_translation_boundary.py` | Cover guarded imports without async extras and explicit translation settings injection |

### 2026-06-03: Spellcheck resource package cleanup

| File | Responsibility |
| --- | --- |
| `src/omniscribe/resources/dictionaries/ara.json.gz` | Packaged Arabic compiled spellcheck dictionary for installed distributions |
| `src/omniscribe/resources/dictionaries/eng.json.gz` | Packaged English compiled spellcheck dictionary for installed distributions |
| `src/omniscribe/core/postprocess.py` | Load packaged dictionaries first while retaining legacy repository-root and user-cache fallbacks |
| `pyproject.toml` | Exclude bytecode cache artifacts from Hatch package builds |
| `tests/core/test_dictionary_postprocess.py` | Cover packaged dictionary lookup and legacy repository-root fallback |

### 2026-06-03: Lazy web server imports

| File | Responsibility |
| --- | --- |
| `src/omniscribe/__init__.py` | Preserve package-level OCR exports through lazy lookups so `import omniscribe.server` does not load OCR core dependencies first |
| `src/omniscribe/server.py` | Preserve `omniscribe.server:app` and `omniscribe.server:main` while deferring FastAPI, router, static-file, and uvicorn imports until the web app is created or run |
| `tests/api/test_server_lazy_imports.py` | Verify base-install-safe `omniscribe.server` imports and deterministic missing-web-extra errors without uninstalling FastAPI |
| `ARCHITECTURE.md` | Record the optional-web lazy import boundary for the server module |

### 2026-08-02: Quality Audit & YAGNI Improvements

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/workflows/hybrid.py` | Re-raise `CircuitOpenError` explicitly in crop/box OCR exception handlers to prevent swallowing endpoint failures |
| `src/omniscribe/core/grounded/prompted.py` | Offload grounded PIL crop and PNG buffer generation to thread pool via `asyncio.to_thread` |
| `src/omniscribe/api/routers/ocr.py` | Handle `asyncio.CancelledError` on client disconnect without logging 500 stack traces, and wrap file cleanup calls in `asyncio.to_thread` |
| `src/omniscribe/api/services/uploads.py` | Add parent directory confinement check in `cleanup_files` to ensure deleted paths reside in temporary storage |
| `frontend/src/lib/components/workstation/RightControlDock.svelte` | Add `role="button"`, `tabindex="0"`, and `onkeydown` keyboard trigger to target document drop zone for accessibility compliance |
| `frontend/src/lib/components/workstation/BottomProgressDock.svelte` | Rename outer container ID to `workstation-progress-dock` to eliminate duplicate DOM ID conflicts |

### 2026-08-11: Industry-Standards Audit Implementation (P1 & Quick Wins)

| File | Responsibility |
| --- | --- |
| `.github/dependabot.yml` | Dependabot configuration for `pip` and `github-actions` ecosystems with weekly schedule |
| `.github/workflows/test.yml` | Add `pip-audit` vulnerability scan, `pytest-cov` test coverage reporting, and CycloneDX SBOM artifact generation |
| `pyproject.toml` | Add `pytest-cov`, `pip-audit`, and `cyclonedx-python-lib` to `dependency-groups.dev` |
| `.pre-commit-config.yaml` | Sync `ruff-pre-commit` version to `v0.9.0` |
| `AGENTS.md` | Document `surya-ocr` `requests>=2.31` workaround follow-up and `live_llm` manual test run instructions (workaround closed in audit-secondary Phase 5 — see Known Tech Debt) |

### 2026-08-11: Goose-Style Multi-Provider API Handling Architecture

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/provider_manager.py` | `ProviderManager` service with 11-provider catalog templates, system environment variable auto-discovery (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_HOST`, etc.), disk persistence to `~/.config/omniscribe/providers.yaml`, active provider switching, and model listing dispatch |
| `src/omniscribe/core/ocr/multi_format_client.py` | Multi-format LLM completion dispatcher supporting `openai_compatible`, `anthropic_compatible`, and `ollama_compatible` formats with exponential backoff retries and timeout boundaries |
| `src/omniscribe/api/routers/providers.py` | Goose-style provider management API routes (`/api/providers`, `/api/providers/templates`, `/api/providers/active`, `/api/providers/{provider_id}/models`) |
| `src/omniscribe/api/schemas/requests.py` | `ProviderFormatEnum`, `ProviderConfig`, `ProviderTemplate`, `ActiveProviderUpdate`, `ProviderCreateRequest` schemas |
| `src/omniscribe/core/llm/client.py` | Directs VLM/LLM completion calls through `ocr/multi_format_client.py` based on active provider configuration |
| `src/omniscribe/api/routers/config.py` | Connects `/api/models` discovery endpoints to `ProviderManager` |
| `tests/api/services/test_provider_manager.py` | Unit tests for provider configuration manager, env-var discovery, and persistence |
| `tests/api/test_multi_format_client.py` | Unit tests for OpenAI, Anthropic, and Ollama multi-format completion execution |
| `tests/api/routers/test_provider_api_routes.py` | Unit tests for provider REST management API routes |


### 2026-08-12: Full Svelte 5 + TailwindCSS v4 Frontend Migration & Legacy Cleanup

| File | Responsibility |
| --- | --- |
| `frontend/vite.config.ts` | Configured Svelte 5 + Tailwind v4 build pipeline outputting directly to `src/omniscribe/static` and setting `conditions: ['browser']` for Vitest browser mode testing |
| `frontend/package.json` | Updated project package name to `omniscribe-frontend` |
| `frontend/src/lib/components/ui/Badge.svelte` | Exported `BadgeVariant` type in module context, added `title` prop binding, and supported `class` / `className` props |
| `frontend/src/lib/components/ui/Card.svelte` | Supported standard `class` and legacy `className` props seamlessly |
| `frontend/src/lib/components/ui/Input.svelte` | Fixed HTML `autocomplete` property type casting |
| `frontend/src/lib/components/workstation/MetadataPanel.svelte` | Fixed `BadgeVariant` type assertion and updated component property bindings |
| `frontend/src/lib/components/views/GlossaryView.svelte` | Fixed string casting on dictionary term target properties |
| `frontend/src/lib/components/views/SettingsView.svelte` | Converted component property bindings to standard `class` props |
| `frontend/src/lib/components/views/ExtractionView.svelte` | Converted component property bindings to standard `class` props |
| `frontend/src/lib/components/views/JobHistoryView.svelte` | Updated `BadgeVariant` import and converted component property bindings to standard `class` props |
| `frontend/src/lib/components/views/TranscriptionView.svelte` | Converted component property bindings to standard `class` props |
| `frontend/src/lib/components/modals/ExportModal.svelte` | Fixed `tagVariant` type annotations and converted property bindings to standard `class` props |
| `src/omniscribe/static/` | Compiled production Svelte 5 + Tailwind v4 single-page application assets served by FastAPI |

### 2026-08-14: Multi-Domain Architecture, Security & Quality Audit

Conducted a comprehensive 4-domain audit (Core Pipeline, Backend API/Security, Frontend Workstation, and QA/DevOps):
1. **Core Pipeline**: Confirmed normalized `[0..1]` bounding box invariant, monotonic DP alignment, cooperative cancellation via `OCRCancelled` (`BaseException`), bounded 16-entry image LRU cache, and quality repair loop stall guards. Identified `complete_vlm_prompt` export omission in `core/ocr/__init__.py` and `DocumentTree` child index desync on reading order sort.
2. **API & Security**: Identified and cataloged readiness probe fix (`OCRJobQueue.running` property), third-party provider API key response masking, artifact token separation from server bearer authentication, and uniform SSRF validation on tree translation and transcription endpoints.
3. **Frontend Workstation**: Verified Svelte 5 + TypeScript build and Vitest suite (17/17 passed). Identified unmounted navigation views (`JobHistoryView`, `TranscriptionView`, `ExtractionView`) in `App.svelte` and modal focus trapping requirements.
4. **QA & DevOps**: Executed full test and lint suites (1,230 fast tests passing in 37.9s, 0 Ruff errors, 0 format issues, 144 source files clean in Mypy strict mode). Cataloged missing dev CI dependencies in `pyproject.toml` (`pytest-cov`, `pip-audit`, `cyclonedx-python-lib`, `rich`) and frontend CI job integration.

### 2026-08-14: CI Frontend Build & Test Wiring Hardening

| File | Responsibility |
| --- | --- |
| `.github/workflows/test.yml` | Integrated Node.js v20 setup, frontend dependency installation, checks/tests (`svelte-check` + `vitest`), and frontend production build prior to Python test execution |
| `.github/workflows/release.yml` | Added frontend build step before `uv build` packaging so release wheels contain compiled frontend assets |
| `tests/api/routers/test_static_wiring.py` | Added graceful skip guards for when frontend static assets have not yet been built locally |

### 2026-08-14: Core Dependencies Update (Redis & ChromaDB)

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Promoted `redis>=5.0.0` and `chromadb>=0.5.0` to core `[project.dependencies]` so Celery distributed backend state and vector lexicon RAG support are packaged out-of-the-box |

### 2026-08-14: Full Dependency Modernization & Security Audit Resolution

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Upgraded `surya-ocr>=0.22.1`, bounded `openai>=2.11.0,<3`, pinned `numpy<2.3.0` for Python 3.11 typing stub compatibility, removed unmaintained `comet` (`unbabel-comet`) extra to unblock modern `transformers 5.x` and `huggingface-hub>=1.5.0`, and locked `redis>=5.0.0` and `chromadb>=0.5.0` |
| `uv.lock` | Updated 220 resolved packages across runtime, upgrading `transformers` (v4.57.6 -> v5.15.0), `protobuf` (v4.25.9 -> v7.35.1), `huggingface-hub` (v0.36.2 -> v1.27.0), `pypdfium2` (v4.30.0 -> v5.13.0), resolving 45 of 46 known `pip-audit` security advisories |
| `src/omniscribe/core/translate/nllb.py` | Adapted HuggingFace pipeline and tokenizer typing for `transformers` 5.x |

### 2026-08-18: Comprehensive 5-Domain Multi-Agent Codebase Audit

Conducted an exhaustive 5-domain audit (66 findings across Core Pipeline, API & Security, Frontend, Testing & QA, and DevOps & Configuration):
1. **Core Pipeline (10 findings)**: Identified `run_document_processors` strict aggregate assertion bug rejecting valid `MAY_DELETE` contract processors (`D1-01`); `convert_tree_to_docx` crash on `BlockNode(TABLE)` and duplicate table emissions (`D1-02`); unmanaged background task leak on `CircuitOpenError` in `PromptedGroundedOCR` (`D1-03`); `translate_tree` bypassing `TableNode` instances in page children (`D1-04`); and `_Chunker.add` delimiter overwrite formatting bug (`D1-05`).
2. **API & Security (13 findings)**: Identified management route auth bypass when global token is unset but subsystem tokens exist (`D2-01`); `JobHistory.record()` signature mismatch crashing OCR pipeline completion on SQLite or Redis backends (`D2-02`); plaintext token exposure via URL query parameters (`D2-03`); unbounded memory leak and $O(N)$ event loop blocking in `RateLimitMiddleware` (`D2-04`); missing SSRF check on `sql_dsn` in SQL glossary importer (`D2-05`); and flawed chunked/gzip byte parsing in `_PinnedIPTransport` (`D2-06`).
3. **Frontend (17 findings)**: Identified `ExtractionView.svelte` failing to extract text from bound document artifacts (`D3-15`); broken WAI-ARIA tabpanel hierarchy in `SettingsView.svelte` (`D3-01`); unlabeled form controls in Extraction, Translation, and Transcription views (`D3-02`); detached anchor downloads and premature `URL.revokeObjectURL` causing 0-byte downloads in Firefox (`D3-08`); PDF.js document proxy memory leaks (`D3-11`); and synchronous translation returning empty string on bound artifacts (`D3-16`).
4. **Testing & QA (14 findings)**: Identified silent `pytest.skip` calls on empty pipeline outputs hiding regressions in recall and integration gates (`D4-01`); untested Redis/SQLite connection outage handling (`D4-02`); absence of mypy typechecking on `tests/` in CI and pre-commit (`D4-11`); missing `--cov-fail-under` coverage floor in CI (`D4-12`); and vacuous assertions in live VLM tests (`D4-05`).
5. **DevOps & Config (12 findings)**: Identified Celery worker inheriting Dockerfile HTTP healthcheck causing container restart loops (`D5-01`); `RUN chown` duplicating `.venv` layer by 1.5–2.0 GB in Docker image (`D5-02`); CLI flag password exposure in `compose.yaml` and `start_app.vbs` (`D5-03`); release workflow README sed regex typo (`D5-04`); and unverified curl execution in `install.sh` (`D5-05`).

### 2026-08-18: Phase 0 Critical Blocker Fixes Implementation

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/state/sqlite.py` | Added `text_artifact_id: str | None = None` to `SQLiteJobHistory.record()` to match `JobHistory` protocol and persist artifact linkage |
| `src/omniscribe/api/services/state/redis.py` | Added `text_artifact_id: str | None = None` to `RedisJobHistory.record()` to match `JobHistory` protocol and persist artifact linkage |
| `src/omniscribe/api/middleware/auth.py` | Hardened `BearerAuthMiddleware` to protect management routes (`/api/config`, `/api/providers`, `/api/jobs`) with active subsystem tokens when global token is unset |
| `frontend/src/lib/components/views/ExtractionView.svelte` | Fixed extraction on bound documents to read text from `$documentStore.pages` or `/api/text/{id}` before dispatching |
| `tests/core/test_pipeline_recall.py` | Replaced `pytest.skip` on empty pipeline results with strict `assert doc_result is not None` and `assert len(captured) > 0` |
| `tests/api/test_integration.py` | Replaced `pytest.skip` on empty boxes with strict `assert len(boxes) > 0` and `assert len(boxes) >= 3` |
| `compose.yaml` | Overrode container healthcheck for Celery `worker` service with native `celery inspect ping` |
| `tests/api/middleware/test_security_middleware.py` | Added regression test `test_management_routes_protected_when_only_subsystem_token_set` (formerly the separate-auth suite) |

### 2026-08-18: Phase 1 High-Priority Reliability & Security Remediations

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors/base.py` | Honor `MAY_DELETE` contract in `run_document_processors` strict mode aggregate checks without false positives on deletions |
| `src/omniscribe/core/writers/docx_tree.py` | Safely handle `BlockNode(TABLE)` instances and de-duplicate rendered table instances between pages and document roots |
| `src/omniscribe/api/routers/common.py` | Prioritize `X-Artifact-Token` and `Authorization: Bearer` headers in `get_access_token()` over query params |
| `src/omniscribe/api/middleware/rate_limit.py` | Bound `RateLimitMiddleware` memory footprint with `MAX_TRACKED_IPS = 10_000` ceiling and clean eviction |
| `src/omniscribe/utils/security.py` | Provide synchronous `is_blocked_host()` check for SSRF validation |
| `src/omniscribe/core/glossary_sources/sql_table.py` | Block private / local host connections in `parse_sql_table()` with SSRF validation |
| `frontend/src/lib/components/views/SettingsView.svelte` | Add WAI-ARIA tabpanel markup (`role="tabpanel"`, `aria-labelledby`, `tabindex="0"`) for WCAG compliance |
| `frontend/src/lib/components/views/ExtractionView.svelte` | Add explicit `id` and `aria-label` to extraction input textarea |
| `frontend/src/lib/components/views/TranslationView.svelte` | Add explicit `id` and `aria-label` to translation source input textarea |
| `frontend/src/lib/components/views/TranscriptionView.svelte` | Add explicit `aria-label` to file upload input |
| `frontend/src/lib/components/modals/ExportModal.svelte` | Delay `URL.revokeObjectURL()` via `setTimeout(..., 1000)` in `downloadBlob()` to prevent 0-byte download aborts in Firefox |
| `frontend/src/lib/components/views/ExtractionView.svelte` | Delay `URL.revokeObjectURL()` via `setTimeout(..., 1000)` in `downloadBlob()` |
| `frontend/src/lib/components/views/TranscriptionView.svelte` | Delay `URL.revokeObjectURL()` in `downloadAsText()` and `downloadAsSrt()` |
| `frontend/src/lib/stores/pdfPreview.ts` | Explicitly call `pdfDoc.destroy()` in `resetTransient()` and `page.cleanup()` in `renderPage()` to prevent PDF.js canvas/worker memory leaks |
| `pyproject.toml` | Set `mypy_path = "src"` for consistent import resolution |
| `Dockerfile` | Use `COPY --chown=app:app` and remove redundant `RUN chown -R` layer, reducing image size by ~1.5 GB |
| `tests/core/glossary_sources/test_glossary_sources_sql_git.py` | Added regression test `test_ssrf_blocked_dsn_rejected` |

### 2026-08-18: Comprehensive Audit Phase 2 Remediations (Polish & Maintainability)

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/translate/tree.py` | Recursively translate `TableNode.cells` `BlockNode` instances in `translate_tree()` and emit chunk events |
| `src/omniscribe/core/translate/workflow.py` | Preserve multi-granularity delimiters (`\n\n`, `\n`, ` `) in `_Chunker` via formatted string accumulation |
| `src/omniscribe/core/grounded/prompted.py` | Guarantee background `asyncio.create_task` cancellation on `CircuitOpenError` or error in `PromptedGroundedOCR` |
| `src/omniscribe/core/processors/table.py` | Safeguard table cell bounding box calculation against non-finite float coordinates |
| `src/omniscribe/core/glossary_sources/git_repo.py` | Validate and sanitize `ref` arguments in `parse_git_glossary()` against CLI option injection |
| `src/omniscribe/api/services/provider_manager.py` | Prevent masked API key previews (`"***"`, `"..."`) from overwriting real secrets in `save_provider()` |
| `src/omniscribe/utils/security.py` | Unconditionally block cloud instance metadata endpoints (`169.254.169.254` / `169.254.0.0/16`) even under `ALLOW_SSRF_LOCAL=true` |
| `src/omniscribe/api/schemas/requests.py` | Accept `text_artifact_id` and `text_artifact_token` in `TranslationRequest` schema |
| `src/omniscribe/api/services/ai.py` | Resolve source text from token-bound artifact store in `translate_text()` when `request.text` is empty |
| `.github/workflows/release.yml` | Correct repository sed substitution regex to match `(OmniScribe\.git\|local-deepl\.git)` |
| `Dockerfile`, `install.ps1`, `install.sh`, `AGENTS.md` | Include `--extra lexicon` in standard `uv sync` commands to provide LanceDB vectorized glossary out-of-the-box |
### 2026-08-19: Frontend, A11y & Workstation Hardening

| File | Responsibility |
| --- | --- |
| `frontend/src/lib/utils/download.ts` | Centralized utility for filename path traversal sanitization and DOM-attached Blob/URL downloads with deferred `URL.revokeObjectURL()` |
| `frontend/src/lib/utils/__tests__/download.test.ts` | Unit test suite verifying filename sanitization, DOM anchor attachment, and delayed revocation |
| `frontend/src/lib/stores/pdfPreview.ts` | Deterministic `pdfDoc.destroy()`, `pdfDoc.cleanup()`, and `page.cleanup()` execution on stale load version transitions, document resets, and render errors |
| `frontend/src/lib/components/workstation/PdfMiniViewer.svelte` | Deterministic `doc.destroy()`, `doc.cleanup()`, and `page.cleanup()` lifecycle invocations on canvas paints, document switches, and viewer destruction |
| `frontend/src/lib/components/modals/ExportModal.svelte` | Switched file exports (TXT, MD, JSON, DOCX, PDF) to robust `downloadBlob()` and `downloadUrl()` with filename sanitization |
| `frontend/src/lib/components/views/ExtractionView.svelte` | Automatically auto-populates input text from `$documentStore.pages` / resolves text from token-bound artifact store, adds explicit `<label>`, `role="status"` live region, and uses `downloadBlob()` |
| `frontend/src/lib/components/views/TranslationView.svelte` | Automatically auto-populates source text from `$documentStore.pages` / resolves text from token-bound artifact store, adds explicit accessible IDs/labels, and `role="status"` live regions |
| `frontend/src/lib/components/views/TranscriptionView.svelte` | Replaced inline blob downloads with `downloadBlob()`, added explicit sr-only file input label, accessible engine select ID, and `role="status"` live region |
| `frontend/src/lib/components/views/SettingsView.svelte` | Fixed WAI-ARIA tabpanel semantics (`role="tabpanel"`, matching `aria-controls` / `id` / `aria-labelledby`) and added keying to processor chip loop |
| `frontend/src/lib/components/ui/Toggle.svelte` | Fixed native checkbox focus outline styling to keep checkbox visually hidden (`opacity-0`) while driving focus rings onto the styled switch track via `peer-focus-visible` |
| `frontend/src/__tests__/a11y.test.ts` | Automated accessibility test suite verifying WAI-ARIA tablist/tabpanel wiring, toggle semantics, form control labels, and live region statuses |

### 2026-08-19: Distributed Tasks, Real-Time Progress Fanout, Security Hardening & State Parity

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/tasks.py` | Implement Celery background task `process_ocr_task` with `_OCRTask` base mixin for distributed OCR pipeline execution, progress emissions, and `JobHistory` tracking |
| `src/omniscribe/api/routers/ocr.py` | Wire `POST /api/process/async` to dispatch to Celery `process_ocr_task` when running in `RedisStateBackend` mode, falling back to standalone `OCRJobQueue` in memory/sqlite mode; update `process_status` to query queue, job history, and Celery status |
| `src/omniscribe/api/services/progress.py` | Add Redis Pub/Sub broadcast support (`publish`, `publish_async`) in `ProgressService` publishing progress frames to `omniscribe:progress:{channel_id}` |
| `src/omniscribe/api/routers/websocket.py` | Wire `ConnectionManager.send` to broadcast via Redis Pub/Sub, and spawn async background pubsub listener in `websocket_endpoint` for multi-worker WebSocket event fanout |
| `src/omniscribe/api/services/state/redis.py` | Initialize `ProgressService(redis_url=redis_url)`, standardize `RedisJobHistory` default `max_jobs` to 1000, and implement accurate active key counting in `RedisTextArtifactStore.__len__` |
| `src/omniscribe/api/middleware/rate_limit.py` | Implement `OrderedDict` sliding window with LRU eviction and strict 10,000 active IP bound in `RateLimitMiddleware` to prevent unbounded memory growth |
| `src/omniscribe/utils/security.py` | Unconditionally block IMDS (`169.254.0.0/16`, `fe80::/10`), CGNAT (`100.64.0.0/10`), and `0.0.0.0/8` regardless of `ALLOW_SSRF_LOCAL` setting in `is_ssrf_target` and `is_blocked_host` |
| `src/omniscribe/api/routers/common.py` | Emit `DeprecationWarning` and warning log when `?token=` query param is used in `get_access_token`, prioritizing `Authorization: Bearer` and `X-Artifact-Token` headers |
| `tests/api/services/test_distributed_ocr_tasks.py` | Unit tests for Celery `process_ocr_task` execution, error handling, Redis-mode dispatch, and status resolution |
| `tests/api/middleware/test_security_middleware.py` | Unit tests for `RateLimitMiddleware` LRU bounds (10,000 cap, LRU eviction), `BearerAuthMiddleware`, and `MaxUploadSizeMiddleware` |
| `tests/api/middleware/test_token_deprecation.py` | Unit tests for token sunset deprecation warning emission, log warning, and header precedence |

### 2026-08-23: Core Workflow & Engine Decomposition (Phase 3)

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/workflows/stages/conversion.py` | `HybridConverter` — batched page rasterization streaming through `PDFHandler.convert_batches` with page-range filtering and optional preprocessing |
| `src/omniscribe/core/workflows/stages/layout.py` | `HybridLayoutDetector` & `decode_chunk_bytes` — batched Surya layout detection (`DETECT_CHUNK_SIZE`), whitespace recall booster merging, PDF text-layer recall merging, and dense page classification |
| `src/omniscribe/core/workflows/stages/ocr.py` | `HybridOcrRunner` — concurrent sparse page OCR dispatching with DP alignment, dense per-box OCR dispatching, observer callback emission, and resilient exception unwrapping |
| `src/omniscribe/core/workflows/stages/refine.py` | `HybridRefiner` — crop-and-re-OCR for empty sparse boxes and nearby duplicate deduplication |
| `src/omniscribe/core/workflows/stages/__init__.py` | Stage package re-exports for `HybridConverter`, `HybridLayoutDetector`, `HybridOcrRunner`, `HybridRefiner`, and `decode_chunk_bytes` |
| `src/omniscribe/core/workflows/hybrid.py` | Streamlined `HybridEngine` coordinating the 5 execution phases with 100% backward-compatible delegators |
| `tests/core/workflows/test_workflows_stages.py` | Unit test suite for isolated converter and layout detector stages |

## See Also

- [README.md](README.md) — feature overview, install, web workspace
- [CHANGELOG.md](CHANGELOG.md) — version history and breaking changes
- [DEPLOYMENT.md](DEPLOYMENT.md) — local / LAN / public-internet deployment profiles
- [SECURITY.md](SECURITY.md) — threat model, hardening checklist, vulnerability disclosure
- [AGENTS.md](AGENTS.md) — contributor guide and full env-var reference
- `audits/` — historical and comprehensive domain audit logs

_Last updated: 2026-08-23_

