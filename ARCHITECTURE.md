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

The optional whitespace-recall pass (`core/text_recall.py`, hybrid path only,
default on, kill switch `OMNISCRIBE_WHITESPACE_RECALL`) merges conservative
pixel-statistics text-line candidates into the Surya boxes before dense
selection, OCR, and alignment. It fails open: any per-page error degrades to
the original Surya boxes.

The optional text-layer-recall pass (`core/text_layer_recall.py`, hybrid path
only, default on, kill switch `OMNISCRIBE_TEXT_LAYER_RECALL`) is the second
recall source: on digital PDFs it recovers lines Surya missed straight from
the embedded text layer (`page.get_text("words")`), merged after the
whitespace booster so its dedup sees both sources' extras. Scanned pages and
image inputs have no text layer, making the pass a strict no-op there. Same
fail-open contract: any per-page error degrades to the boxes merged so far,
and each pass logs one INFO run summary per job.

## Directory Responsibilities

| Path | Single Responsibility |
| --- | --- |
| `src/omniscribe/__init__.py` | Lazy package-level public exports that avoid loading OCR or web dependencies during unrelated submodule imports |
| `src/omniscribe/server.py` | Lazy optional-web dependency loading, FastAPI application setup, CLI argument parsing for `--host/--port/--reload`, and `omniscribe-server` script entry point |
| `src/omniscribe/pipeline.py` | `OCRPipeline` facade — thin orchestration layer that delegates to `HybridEngine` or `GroundedEngine` based on injected components |
| `src/omniscribe/evaluation.py` | Package-root confidence evaluator: GLM-OCR fixture loader, greedy IoU matching, and per-document `ConfidenceReport` for the `scripts/confidence_*.py` tooling |
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
| `src/omniscribe/core/text_recall.py` | Whitespace recall booster — pixel-statistics text-line candidates merged into Surya detection on the hybrid path (`OMNISCRIBE_WHITESPACE_RECALL` kill switch, INFO run summary) |
| `src/omniscribe/core/text_layer_recall.py` | Text-layer recall source — lines Surya missed recovered from a digital PDF's embedded text layer; second box source merged after the whitespace booster (`OMNISCRIBE_TEXT_LAYER_RECALL` kill switch, INFO run summary, no-op for scans/images) |
| `src/omniscribe/core/ocr/` | OpenAI/Anthropic/Ollama multi-format VLM client, prompts, response filters, limits, exceptions, retry, and circuit-breaker resilience; `__init__.py` preserves the public import surface |
| `src/omniscribe/core/ocr_quality/` | OCR Quality Trust Layer — watermark detection, script detection, hallucination guard, Platt scaling calibration fit/eval, trust scorer, and orchestrator |
| `src/omniscribe/core/transcription/` | Speech-to-text audio transcription engines (local Whisper & OpenAI-compatible API backends) |
| `src/omniscribe/core/glossary_library/` | In-memory and persistent terminology glossary terms, library store, and search |
| `src/omniscribe/core/glossary_sources/` | Terminology import parsers for TBX, CSV, JSON, and web URLs |
| `src/omniscribe/core/tree_export.py` | Hierarchical block-tree export builder |
| `src/omniscribe/core/docx_tree_writer.py` | Hierarchical block-tree to `.docx` converter |
| `src/omniscribe/core/html_writer.py` | Semantic HTML document writer from `DocumentResult` |
| `src/omniscribe/core/block_tree.py` | Hierarchical block-tree data structure and tree nodes |
| `src/omniscribe/core/pdf/__init__.py` | Package re-exports for `PDFHandler`, `DocumentResultWriter`, `IMAGE_EXTENSIONS`, `_emit_pymupdf_agpl_notice`, and public PDF symbols |
| `src/omniscribe/core/pdf/rasterizer.py` | PyMuPDF AGPL warning emission, safe DPI calculation, image extension validation, and PDF/image rasterization to JPEG/PNG base64 |
| `src/omniscribe/core/pdf/embedder.py` | Invisible text layer PDF rendering over rasterized backgrounds, normalized bbox coordinate transformations, and font sizing calculation |
| `src/omniscribe/core/pdf/handler.py` | `PDFHandler` class facade implementing `DocumentResultWriter` protocol for high-level workflow orchestration |
| `src/omniscribe/core/grounded/` | Grounded OCR models, prompted backend, rasterization, and bbox-native response parsers; `__init__.py` preserves the public import surface |
| `src/omniscribe/core/postprocess.py` | Dictionary-based spellcheck post-processing |
| `src/omniscribe/core/preprocessing.py` | Local hybrid-path page preprocessing (orientation detection, deskew, denoise, contrast normalization, crop cleanup) |
| `src/omniscribe/core/handwriting_preprocessor.py` | Local handwriting image preprocessor for specialized handwriting pipeline paths |
| `src/omniscribe/core/routing.py` | Quality routing recommendation metadata and policy recorder |
| `src/omniscribe/core/evaluation.py` | Lightweight `EvaluationMetrics` dataclass and `evaluate_document` helper for in-process processor result scoring |
| `src/omniscribe/core/docx_writer.py` | Markdown → `.docx` converter used by the docx export route |
| `src/omniscribe/core/translation_config.py` | Core-owned typed settings and optional-feature errors for async translation |
| `src/omniscribe/core/translation.py` | Optional LangGraph translation workflow |
| `src/omniscribe/core/workflows/base.py` | `EngineBase`, `OutputWriter`, `ProgressCallback`, `WarningCallback` shared by both engines |
| `src/omniscribe/core/workflows/hybrid.py` | `HybridEngine` — Surya detect → VLM OCR (sparse/dense) → DP align → optional refine → post-process → processors → output |
| `src/omniscribe/core/workflows/grounded.py` | `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/omniscribe/core/workflows/repair.py` | `QualityRepairLoop` and `RepairOptions` — engine-agnostic block-level low-confidence re-OCR (stall guard, fail-open, `CircuitOpenError` re-raise) plus the job-level `quality_summary` aggregator |
| `src/omniscribe/core/workflows/utils.py` | Stand-alone workflow helper functions (`parse_page_range`, `_estimate_confidence`, `_decode_page_image`, `_normalize_for_dedup`, `_drop_refined_duplicates`, `_is_refinable`) and workflow constants (`REFINABLE_MIN_WIDTH`, `REFINABLE_MIN_HEIGHT`, `DETECT_CHUNK_SIZE`) |
| `src/omniscribe/core/workflows/__init__.py` | Re-exports `EngineBase`, `HybridEngine`, `GroundedEngine`, public helper `parse_page_range`, constants, and callback type aliases |
| `src/omniscribe/resources/dictionaries/` | Packaged compiled spellcheck dictionaries loaded before legacy repository-root dictionaries |
| `src/omniscribe/resources/calibration/` | Pre-trained model confidence calibration files (e.g. `qwen2_5_vl_72b.json`) |
| `src/omniscribe/api/routers/config.py` | Runtime configuration and model discovery routes (`GET/POST /api/config`) |
| `src/omniscribe/api/routers/ocr.py` | Thin `POST /api/process` orchestrator — validate the request, build the pipeline, run it, build the response, record the job; delegates all heavy lifting to `api/services/ocr_*.py` |
| `src/omniscribe/api/routers/websocket.py` | Token-bound WebSocket progress transport and progress session issuance |
| `src/omniscribe/api/routers/jobs.py` | `GET/DELETE /api/jobs` — recent job history and clear-all |
| `src/omniscribe/api/routers/artifacts.py` | Token-bound artifact download routes for text, metadata, and document exports |
| `src/omniscribe/api/routers/translation.py` | Synchronous `POST /api/translate`, async `POST /api/translate/async`, tree translation `POST /api/translate/tree`, glossary and NLLB endpoints |
| `src/omniscribe/api/routers/transcription.py` | Voice transcription and transcription provider configuration routes (`POST /api/transcribe`, `GET/POST /api/config/transcription`) |
| `src/omniscribe/api/routers/glossary_imports.py` | Local glossary library and external URL glossary import routes |
| `src/omniscribe/api/routers/health.py` | Liveness (`/health`, `/healthz`) and readiness (`/ready`, `/readyz`) probe endpoints |
| `src/omniscribe/api/routers/extraction.py` | `POST /api/extract` — structured data extraction, plus document export routes |
| `src/omniscribe/api/routers/state.py` | Compatibility aliases over the `LocalStateBackend` singleton, plus the process-local glossary library |
| `src/omniscribe/api/routers/providers.py` | Multi-format provider catalog and provider detail routes |
| `src/omniscribe/api/routers/common.py` | Shared router helpers: `_stable_server_error`, `_extract_bearer_token`, `_path_exists`, `_cleanup` |
| `src/omniscribe/api/schemas/__init__.py` | Re-exports the typed request models and StrEnums |
| `src/omniscribe/api/schemas/requests.py` | `ConfigUpdate`, `ProcessSettings`, `TranslationRequest`, `ExtractionRequest`, `ExtractionTemplate`, `DocumentExportRequest`, `DocumentExportFormat`, `ExportDocxRequest`; enums: `PipelineMode`, `DenseMode`, `SpellcheckMode`, `DocumentProcessorName` |
| `src/omniscribe/core/ocr/multi_format_client.py` | Multi-format LLM completion dispatcher (`openai_compatible`, `anthropic_compatible`, `ollama_compatible`), vision base64 payloads, exponential backoff resilience retries, and timeout boundaries |
| `src/omniscribe/api/services/provider_manager.py` | `ProviderManager` service — 11-provider catalog templates, system environment variable auto-discovery (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_HOST`, etc.), disk persistence (`~/.config/omniscribe/providers.yaml`), active provider switching, and model discovery delegation |
| `src/omniscribe/api/services/ocr_settings.py` | Form-parameter resolution for `POST /api/process` — "form field wins, config falls back" merge that produces a validated `ProcessSettings` |
| `src/omniscribe/api/services/ocr_pipeline_factory.py` | Pipeline construction for `POST /api/process` — branches on `pipeline_mode` (hybrid vs grounded), wires WebSocket-bound per-block callbacks, decides whether to plug in the TrOCR handwriting specialist, and exposes backend-model verification |
| `src/omniscribe/api/services/ocr_response.py` | Response assembly for `POST /api/process` — validation-error JSON, FileResponse construction with token-bound headers (`X-Document-Quality`, `X-Document-Structure`, `X-Document-Sections`, artifact-id/token pairs), and stable error envelopes |
| `src/omniscribe/api/services/ocr_chunked_runner.py` | Bounded-page PDF execution, per-chunk progress frames, text/page remapping, and merged searchable-PDF output |
| `src/omniscribe/api/services/ocr_jobs.py` | Single-worker asyncio OCR queue, background job lifecycle records, status serialization, and cancellation semantics |
| `src/omniscribe/api/services/transcription.py` | Audio transcription service boundary, input validation, and provider execution |
| `src/omniscribe/api/services/tree_artifact.py` | Document tree artifact persistence and retrieval |
| `src/omniscribe/api/services/http_fetch.py` | SSRF-safe remote document fetcher with redirect and private IP guards |
| `src/omniscribe/api/services/state_backend.py` | `StateBackend` protocol and process-local `LocalStateBackend`, including artifacts, history, progress, glossary, and OCR queue |
| `src/omniscribe/api/services/state_backend_redis.py` | Redis-backed distributed state backend implementation |
| `src/omniscribe/api/services/security.py` | API upload validation, stable error constants, temporary-file cleanup, and opaque text artifact IDs |
| `src/omniscribe/api/services/security_config.py` | `SecuritySettings.from_env()` — env-driven knobs for `OMNISCRIBE_AUTH_TOKEN`, `_CORS_ORIGINS`, `_MAX_UPLOAD_MB`, `_RATE_LIMIT_PER_MIN` |
| `src/omniscribe/api/services/security_middleware.py` | ASGI middlewares wired by `server.create_app()`: `BearerAuthMiddleware`, `MaxUploadSizeMiddleware`, `RateLimitMiddleware` |
| `src/omniscribe/api/services/artifacts.py` | `TextArtifactStore`, `PageText`, `TextArtifactHandle`, and the opaque artifact-id / token primitives shared by text, metadata, and export stores |
| `src/omniscribe/api/services/jobs.py` | `JobHistory`, `JobRecord`, `JobStatus` — durable job history with per-page failure tracking |
| `src/omniscribe/api/services/progress.py` | `ProgressService`, `ProgressChannel`, stage weights, channel/session token validation |
| `src/omniscribe/api/services/document_metadata.py` | Compact JSON report builder and atomic writer for token-bound `DocumentResult` metadata artifacts |
| `src/omniscribe/api/services/document_exports.py` | Token-bound JSON, Markdown, text, Docling-compatible, and MinerU-compatible export artifact builder |
| `src/omniscribe/api/services/workflow.py` | Aggregated orchestration tracking, unifying Celery and synchronous pipeline state |
| `src/omniscribe/api/services/ai.py` | AI service module backing `POST /api/translate` and `POST /api/extract` — OpenAI-compatible calls with fenced-JSON parsing, retry, and stable error mapping |
| `src/omniscribe/api/tasks.py` | Optional Celery translation task execution |
| `src/omniscribe/utils/structured_logging.py` | Structured JSON logging formatter and handlers |
| `src/omniscribe/utils/prompt_safety.py` | Prompt injection detection and input sanitization |
| `src/omniscribe/utils/image.py` | Image crop, blank-region detection, and crop encoding helpers |
| `src/omniscribe/utils/security.py` | SSRF target validation |
| `src/omniscribe/utils/tqdm_patch.py` | Surya progress-bar suppression |
| `src/omniscribe/static/` | Built Svelte 5 workstation assets served by FastAPI |
| `frontend/` | Svelte 5 + Tailwind CSS v4 source, Vite configuration, and production build pipeline |
| `scripts/` | Repo-root developer utilities: confidence eval, fixture builder, debug/inspection scripts, bbox visualizers |
| `examples/` | Sample PDFs and images used by `tests/`, `test_ui.py`, and the confidence scripts |
| `tests/` | Unit, integration, security, and slow-path validation |
| `install.bat` / `install.ps1` | Windows one-click install: `uv` bootstrap, `uv sync --extra web --extra preprocessing`, Docker check, Desktop/Start-Menu shortcuts, post-install verification |
| `start_app.vbs` / `stop_app.bat` | Windows hidden-start and stop-launcher for Redis + Celery + uvicorn; `start_app.vbs` writes a timestamped append log to `start_app.log` |
| `test_ui.py` | Headless Playwright smoke test against the running web UI |

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

Process-local singletons live in `src/omniscribe/api/routers/state.py` and are
imported by every router that needs them. Three independent `TextArtifactStore`
instances back the three artifact surfaces:

| Singleton | Surface | Token-bound header | Read endpoint |
| --- | --- | --- | --- |
| `text_artifacts` | Per-job searchable text | `X-Text-Artifact-Id` / `X-Text-Artifact-Token` | `GET /api/text/{artifact_id}` |
| `metadata_artifacts` | Compact `DocumentResult` page/block metadata | `X-Document-Metadata-Artifact-Id` / `X-Document-Metadata-Artifact-Token` | `GET /api/metadata/{artifact_id}` |
| `export_artifacts` | JSON / Markdown / text / Docling / MinerU exports | `X-Document-Export-Artifact-Id` / `X-Document-Export-Artifact-Token` | `GET /api/export/{artifact_id}` |

`job_history` (`JobHistory`), `progress_service` (`ProgressService`),
`glossary_library` (`GlossaryLibrary`), and `ocr_job_queue` (`OCRJobQueue`) round
out the process-local state. The store implementation lives in
`api/services/artifacts.py` and the token format is the same opaque
hex-id / bearer-token pair across all three artifact surfaces.

### Background OCR lifecycle

`POST /api/process/async` validates and persists the upload before submitting a
runner to the single-worker `OCRJobQueue`. The application lifespan starts the
worker before serving requests and stops it during shutdown. Observable states
are `pending`, `processing`, `complete`, and `error`; status is available at
`GET /api/process/status/{job_id}`. `POST /api/jobs/{job_id}/cancel` removes a
pending job or marks an in-flight job as a stable terminal error without letting
the runner's eventual return overwrite the cancellation. Queue and artifact
indexes are in-memory and are therefore lost on restart; horizontal scaling
requires a shared backend.

### Authentication and runtime security

`SecuritySettings.from_env()` configures the ASGI boundary. A per-service
`OMNISCRIBE_OCR_AUTH_TOKEN` or `OMNISCRIBE_TRANSLATION_AUTH_TOKEN` takes
precedence over the global `OMNISCRIBE_AUTH_TOKEN` for its route group.
`OMNISCRIBE_MAX_UPLOAD_MB`, `OMNISCRIBE_RATE_LIMIT_PER_MIN`, and
`OMNISCRIBE_CORS_ORIGINS` control upload limits, per-IP request throttling, and
CORS respectively. Artifact IDs use a separate artifact token supplied through
`Authorization: Bearer ...`; artifact tokens must not be placed in query strings.

## Web API Surface (non-exhaustive)

| Method | Path | Router | Notes |
| --- | --- | --- | --- |
| `GET` / `POST` | `/api/config` | `config` | Read or update shared runtime configuration |
| `GET` / `POST` | `/api/config/ocr` | `config` | OCR-specific runtime configuration |
| `POST` | `/api/config/ocr/auth` | `config` | Rotate the OCR bearer token at runtime |
| `GET` / `POST` | `/api/config/translation` | `config` | Translation-specific runtime configuration |
| `POST` | `/api/config/translation/auth` | `config` | Rotate the translation bearer token at runtime |
| `GET` / `POST` | `/api/config/transcription` | `transcription` | Transcription provider configuration |
| `GET` | `/api/models`, `/api/models/ocr`, `/api/models/translation`, `/api/models/transcription` | `config` / `transcription` | Backend model discovery (combined, per-service) |
| `GET` | `/api/providers`, `/api/providers/{provider_id}`, `/api/providers/{provider_id}/models`, `/api/providers/active`, `/api/providers/templates` | `providers` | Provider catalog, details, and active-provider switching |
| `POST` | `/api/providers`, `/api/providers/active` | `providers` | Add a provider; set the active provider |
| `DELETE` | `/api/providers/{provider_id}` | `providers` | Remove a provider |
| `GET` | `/health`, `/healthz` (alias), `/ready`, `/readyz` (alias) | `health` | Liveness and readiness probes; bypass bearer auth |
| `POST` | `/api/process` | `ocr` | Canonical synchronous multipart OCR; `/process` is the legacy alias |
| `POST` | `/api/process/async` | `ocr` | Queue background OCR and return `202` with a job ID; `/process/async` is the legacy alias |
| `GET` | `/api/process/status/{job_id}` | `ocr` | Background OCR lifecycle status; `/process/status/{job_id}` is the legacy alias |
| `POST` | `/api/jobs/{job_id}/cancel` | `jobs` | Cancel pending/running background OCR; terminal jobs are idempotent |
| `GET` / `DELETE` | `/api/jobs` | `jobs` | Recent completed-job history; `DELETE` clears history and text artifacts |
| `POST` | `/api/progress/session` | `websocket` | Issue an opaque progress channel and session token |
| `POST` | `/api/progress/cancel/{channel_id}` | `websocket` | Request cancellation for an active progress channel |
| `WS` | `/ws/{channel_id}` | `websocket` | Token-bound progress stream; first inbound frame must be `{"type":"auth","session_token":...}`, then accepts `{"type":"cancel"}` |
| `GET` | `/api/text/{artifact_id}` | `artifacts` | Text artifact; aliases: `/text/...` and `/api/artifacts/text/...` |
| `GET` | `/api/metadata/{artifact_id}` | `artifacts` | Metadata artifact; aliases: `/metadata/...` and `/api/artifacts/metadata/...` |
| `GET` | `/api/export/{artifact_id}` | `artifacts` | Export artifact; aliases: `/export/...` and `/api/artifacts/export/...` |
| `POST` | `/api/export/document` | `artifacts` | Build a token-bound JSON, Markdown, text, Docling, or MinerU artifact |
| `POST` | `/api/export/docx`, `/api/export/docx-tree`, `/api/export/html`, `/api/export/blocktree` | `artifacts` / `extraction` | Document-format exports |
| `POST` | `/api/translate`, `/api/translate/tree`, `/api/translate/nllb` | `translation` | Synchronous translation surfaces |
| `POST` | `/api/translate/async` | `translation` | Celery + Redis translation job (optional extra) |
| `GET` | `/api/translate/status/{job_id}` | `translation` | Poll a Celery translation job |
| `POST` | `/api/extract` | `extraction` | Structured extraction with invoice, resume, academic, or custom templates |
| `POST` | `/api/transcribe` | `transcription` | Speech-to-text via the configured transcription provider |
| `POST` | `/api/glossary`, `/api/glossary/import`, `/api/glossary/import/url` | `translation` / `glossary_imports` | Glossary management and imports |
| `GET` / `POST` / `DELETE` | `/api/glossary/library...` | `glossary_imports` | Local glossary library management |

## Change Blueprint

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

Streamlined provider selection by replacing `litellm_provider.py` with direct OpenAI-compatible client integration in `llm_client.py` and `ocr/processor.py`. Added dedicated `handwriting_preprocessor.py` module. Fully overhauled the frontend interface with the DocuVerse CSS Design System featuring dual theme options (dark/light), glassmorphism, responsive control sidebars, interactive modals, and dynamic notification toasts.

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/handwriting_preprocessor.py` | Local handwriting image preprocessor |
| `src/omniscribe/core/llm_client.py` | Direct OpenAI-compatible VLM client integration and resilience handlers |
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
| `src/omniscribe/api/services/ocr_settings.py` | Form-parameter resolution for `POST /api/process` |
| `src/omniscribe/api/services/ocr_pipeline_factory.py` | Pipeline construction and backend-model verification for `POST /api/process` |
| `src/omniscribe/api/services/ocr_response.py` | Response assembly, validation-error envelopes, and `FileResponse` construction with token-bound headers |
| `src/omniscribe/api/routers/ocr.py` | Shrunk to a thin orchestrator that just chains the services above |
| `tests/test_api_safety.py` | Patches updated to point at `api.services.ocr_pipeline_factory.*` instead of `api.routers.ocr.*` |
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

### 2026-06-14: DOCX export route + `core/docx_writer.py`

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/docx_writer.py` | New `convert_markdown_to_docx(markdown_text: str) -> io.BytesIO` helper |
| `src/omniscribe/api/schemas/requests.py` | New `ExportDocxRequest` typed schema |
| `src/omniscribe/api/routers/extraction.py` | New `POST /api/export/docx` route that streams the generated `.docx` |
| `pyproject.toml` | Already lists `python-docx>=1.1.0` (no change required) |
| `ARCHITECTURE.md` | Document the docx export in the directory table and the Web API surface |

### 2026-06-14: Confidence evaluation scripts and root-level `evaluation.py`

| File | Responsibility |
| --- | --- |
| `src/omniscribe/evaluation.py` | New package-root module: `GTBlock`, `BlockMatch`, `ConfidenceReport`, `load_ground_truth`, `text_similarity`, `compute_report`, `iou` (auto-detects `[x0,y0,x1,y1]` vs `[y0,x0,y1,x1]` fixture axis order) |
| `scripts/confidence_eval.py` | New developer script — runs hybrid and grounded paths against `examples/*.pdf` and reports per-document block recall, IoU, and text similarity |
| `scripts/confidence_image.py` | New developer script — same comparison on a single image, defaults to `examples/image.avif` |
| `examples/` | New sample inputs (`dense.pdf`, `digital.pdf`, `handwritten.pdf`, `hybrid.pdf`, `image.png`, `image.avif`, `notes.pdf`) |
| `tests/test_evaluation.py` | Cover fixture loading, axis-order detection, and `ConfidenceReport` aggregation |
| `ARCHITECTURE.md` | Document the root-level confidence eval vs the lightweight `core/evaluation.py` processor-metrics helper |

### 2026-06-14: `POST /api/extract` and `ExtractionTemplate` enum

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/schemas/requests.py` | New `ExtractionTemplate` StrEnum (`invoice`, `resume`, `academic`, `custom`) and the `ExtractionRequest` model with `template` and `custom_prompt` fields |
| `src/omniscribe/api/routers/ai.py` | New `extract_structured_data` service with fenced-JSON parsing, retry, and stable error mapping |
| `src/omniscribe/api/routers/extraction.py` | New router that wires the schema, the AI service, and the SSRF guard for `api_base` |
| `tests/test_extraction.py` | Cover template dispatch, custom-prompt fallback, and SSRF fail-closed behavior |
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
| `tests/test_document_processor_selection.py` | Cover processor selection parsing, validation, and factory mapping |

### 2026-06-09: Stage 2 local structure analysis processor

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors.py` | Add `structure_analysis`, a deterministic local processor that classifies blocks as headings, paragraphs, list items, key-values, table candidates, or empty blocks |
| `src/omniscribe/api/routers/ocr.py` | Expose page-level structure summaries through `X-Document-Structure` when structure metadata is present |
| `src/omniscribe/static/index.html` | Add the Structure Analysis opt-in control |
| `tests/test_document.py` | Cover block classification without rewriting output text |

### 2026-06-09: Stage 3 local section analysis processor

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/processors.py` | Add `section_analysis`, a deterministic local processor that assigns blocks to detected heading sections across page boundaries |
| `src/omniscribe/api/routers/ocr.py` | Expose page-level section summaries through `X-Document-Sections` when section metadata is present |
| `src/omniscribe/static/index.html` | Add the Section Analysis opt-in control |
| `tests/test_document.py` | Cover section grouping while preserving original block text |

### 2026-06-09: Stage 4 document metadata artifact surface

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/document_metadata.py` | Build compact JSON-safe metadata reports from `DocumentResult` page/block processor annotations and write them atomically as temporary artifacts |
| `src/omniscribe/api/routers/ocr.py` | Issue `X-Document-Metadata-Artifact-Id` and `X-Document-Metadata-Artifact-Token` only when report content exists, and serve protected `GET /metadata/{artifact_id}` |
| `tests/test_api_safety.py` | Cover token-bound metadata artifact access and payload shape without changing text artifact behavior |

### 2026-06-09: Stage 5-12 Web/API document intelligence

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Deprecate the user-facing `omniscribe` CLI script and drop the CLI-only `rich` dependency; keep `omniscribe-server`. `OCRPipeline` is still importable for in-process programmatic use. |
| `src/omniscribe/core/preprocessing.py` | Add opt-in local page preprocessing diagnostics for the hybrid image path |
| `src/omniscribe/core/processors.py` | Add `layout_enrichment` and `table_extraction` deterministic processors |
| `src/omniscribe/api/services/document_exports.py` | Add token-bound JSON, Markdown, text, Docling-compatible, and MinerU-compatible exports |
| `src/omniscribe/core/routing.py` | Record default-off quality routing recommendations in document metadata |
| `src/omniscribe/api/services/workflow.py` | Expose deterministic Web/API workflow summaries |
| `src/omniscribe/core/evaluation.py` | Add local evaluation metrics for text, bbox, reading-order, and table coverage |

### 2026-06-02: Direct grounded PDF pixmap conversion

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/grounded/rasterize.py` | Convert PDF pixmaps directly into Pillow images before emitting the final grounded OCR thumbnail JPEG |
| `tests/test_grounded.py` | Guard against restoring the redundant intermediate JPEG decode |
| `ARCHITECTURE.md` | Record the existing module layout and the direct pixmap conversion invariant |

### 2026-06-02: Stage 1 API and browser safety hardening

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/schemas/requests.py` | Validate config JSON, OCR multipart settings, translation requests, and extraction requests with explicit enums, booleans, and numeric ranges |
| `src/omniscribe/api/services/security.py` | Enforce streaming upload byte limits, content-signature upload type detection, stable API error messages, and server-issued text artifact IDs |
| `src/omniscribe/api/routers/config.py` | Apply typed config validation, SSRF checks, safe environment parsing, and non-leaking model discovery errors |
| `src/omniscribe/api/routers/ocr.py` | Apply typed OCR/AI boundary validation, hardened upload dispatch, opaque text artifact retrieval, SSRF checks, and stable client-facing errors |
| `src/omniscribe/utils/security.py` | Fail closed for malformed, unsupported, or unresolvable URLs and only allow local/private endpoints when `ALLOW_SSRF_LOCAL=true` is explicitly set |
| `src/omniscribe/static/js/app.js` | Use server-issued text artifact IDs and render extraction status/errors/cards without HTML injection |
| `src/omniscribe/static/js/state_and_api.js` | Build model select placeholder with DOM APIs before appending model-controlled option text |
| `src/omniscribe/static/js/workspace_ui.js` | Provide safe DOM helpers for clearing elements and rendering extraction status cards |
| `tests/test_api_safety.py` | Cover config validation, SSRF fail-closed behavior, streaming upload validation, opaque text artifacts, stable API errors, and static JS sink removal |
| `tests/test_security_qa.py` | Keep extraction JSON parsing deterministic under fail-closed SSRF validation |

### 2026-06-03: Optional async translation boundary

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/translation_config.py` | Own typed translation settings and the deterministic optional-feature error used by core and API boundaries |
| `src/omniscribe/core/translation.py` | Keep chunking and evaluation helpers importable without async extras, lazily build the LangGraph workflow, and accept injected translation settings |
| `src/omniscribe/api/routers/config.py` | Adapt the mutable web runtime config into core-owned translation settings without exposing `_config` to core modules |
| `src/omniscribe/api/celery_app.py` | Guard Celery imports and provide an import-safe fallback task facade when async extras are not installed |
| `src/omniscribe/api/tasks.py` | Validate async translation task inputs and pass explicit translation settings into the core workflow |
| `src/omniscribe/api/routers/ocr.py` | Validate async translation route inputs and return deterministic 503 responses when optional async extras are unavailable |
| `pyproject.toml` | Move Celery, Redis, LangGraph, ChromaDB, and sentence-transformers into the `async-translation` extra with `translation` as an alias extra |
| `tests/test_translation_boundary.py` | Cover guarded imports without async extras and explicit translation settings injection |

### 2026-06-03: Spellcheck resource package cleanup

| File | Responsibility |
| --- | --- |
| `src/omniscribe/resources/dictionaries/ara.json.gz` | Packaged Arabic compiled spellcheck dictionary for installed distributions |
| `src/omniscribe/resources/dictionaries/eng.json.gz` | Packaged English compiled spellcheck dictionary for installed distributions |
| `src/omniscribe/core/postprocess.py` | Load packaged dictionaries first while retaining legacy repository-root and user-cache fallbacks |
| `pyproject.toml` | Exclude bytecode cache artifacts from Hatch package builds |
| `tests/test_dictionary_postprocess.py` | Cover packaged dictionary lookup and legacy repository-root fallback |

### 2026-06-03: Lazy web server imports

| File | Responsibility |
| --- | --- |
| `src/omniscribe/__init__.py` | Preserve package-level OCR exports through lazy lookups so `import omniscribe.server` does not load OCR core dependencies first |
| `src/omniscribe/server.py` | Preserve `omniscribe.server:app` and `omniscribe.server:main` while deferring FastAPI, router, static-file, and uvicorn imports until the web app is created or run |
| `tests/test_server_lazy_imports.py` | Verify base-install-safe `omniscribe.server` imports and deterministic missing-web-extra errors without uninstalling FastAPI |
| `ARCHITECTURE.md` | Record the optional-web lazy import boundary for the server module |

### 2026-08-02: Quality Audit & YAGNI Improvements

| File | Responsibility |
| --- | --- |
| `src/omniscribe/core/workflows/hybrid.py` | Re-raise `CircuitOpenError` explicitly in crop/box OCR exception handlers to prevent swallowing endpoint failures |
| `src/omniscribe/core/grounded/prompted.py` | Offload grounded PIL crop and PNG buffer generation to thread pool via `asyncio.to_thread` |
| `src/omniscribe/api/routers/ocr.py` | Handle `asyncio.CancelledError` on client disconnect without logging 500 stack traces, and wrap file cleanup calls in `asyncio.to_thread` |
| `src/omniscribe/api/services/security.py` | Add parent directory confinement check in `cleanup_files` to ensure deleted paths reside in temporary storage |
| `frontend/src/lib/components/workstation/RightControlDock.svelte` | Add `role="button"`, `tabindex="0"`, and `onkeydown` keyboard trigger to target document drop zone for accessibility compliance |
| `frontend/src/lib/components/workstation/BottomProgressDock.svelte` | Rename outer container ID to `workstation-progress-dock` to eliminate duplicate DOM ID conflicts |

### 2026-08-11: Industry-Standards Audit Implementation (P1 & Quick Wins)

| File | Responsibility |
| --- | --- |
| `.github/dependabot.yml` | Dependabot configuration for `pip` and `github-actions` ecosystems with weekly schedule |
| `.github/workflows/test.yml` | Add `pip-audit` vulnerability scan, `pytest-cov` test coverage reporting, and CycloneDX SBOM artifact generation |
| `pyproject.toml` | Add `pytest-cov`, `pip-audit`, and `cyclonedx-python-lib` to `dependency-groups.dev` |
| `.pre-commit-config.yaml` | Sync `ruff-pre-commit` version to `v0.9.0` |
| `AGENTS.md` | Document `surya-ocr` `requests>=2.31` workaround follow-up and `live_llm` manual test run instructions |

### 2026-08-11: Goose-Style Multi-Provider API Handling Architecture

| File | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/provider_manager.py` | `ProviderManager` service with 11-provider catalog templates, system environment variable auto-discovery (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_HOST`, etc.), disk persistence to `~/.config/omniscribe/providers.yaml`, active provider switching, and model listing dispatch |
| `src/omniscribe/core/ocr/multi_format_client.py` | Multi-format LLM completion dispatcher supporting `openai_compatible`, `anthropic_compatible`, and `ollama_compatible` formats with exponential backoff retries and timeout boundaries |
| `src/omniscribe/api/routers/providers.py` | Goose-style provider management API routes (`/api/providers`, `/api/providers/templates`, `/api/providers/active`, `/api/providers/{provider_id}/models`) |
| `src/omniscribe/api/schemas/requests.py` | `ProviderFormatEnum`, `ProviderConfig`, `ProviderTemplate`, `ActiveProviderUpdate`, `ProviderCreateRequest` schemas |
| `src/omniscribe/core/llm_client.py` | Directs VLM/LLM completion calls through `multi_format_client.py` based on active provider configuration |
| `src/omniscribe/api/routers/config.py` | Connects `/api/models` discovery endpoints to `ProviderManager` |
| `tests/test_provider_manager.py` | Unit tests for provider configuration manager, env-var discovery, and persistence |
| `tests/test_multi_format_client.py` | Unit tests for OpenAI, Anthropic, and Ollama multi-format completion execution |
| `tests/test_provider_api_routes.py` | Unit tests for provider REST management API routes |


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
| `tests/test_static_wiring.py` | Added graceful skip guards for when frontend static assets have not yet been built locally |

### 2026-08-14: Core Dependencies Update (Redis & ChromaDB)

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Promoted `redis>=5.0.0` and `chromadb>=0.5.0` to core `[project.dependencies]` so Celery distributed backend state and vector lexicon RAG support are packaged out-of-the-box |

### 2026-08-14: Full Dependency Modernization & Security Audit Resolution

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Upgraded `surya-ocr>=0.22.1`, bounded `openai>=2.11.0,<3`, pinned `numpy<2.3.0` for Python 3.11 typing stub compatibility, removed unmaintained `comet` (`unbabel-comet`) extra to unblock modern `transformers 5.x` and `huggingface-hub>=1.5.0`, and locked `redis>=5.0.0` and `chromadb>=0.5.0` |
| `uv.lock` | Updated 220 resolved packages across runtime, upgrading `transformers` (v4.57.6 -> v5.15.0), `protobuf` (v4.25.9 -> v7.35.1), `huggingface-hub` (v0.36.2 -> v1.27.0), `pypdfium2` (v4.30.0 -> v5.13.0), resolving 45 of 46 known `pip-audit` security advisories |
| `src/omniscribe/core/nllb_engine.py` | Adapted HuggingFace pipeline and tokenizer typing for `transformers` 5.x |
### 2026-08-17: Comprehensive 5-Domain Multi-Agent Codebase Audit

Conducted an exhaustive 5-domain audit across Core Pipeline, API & Security, Frontend, Testing & QA, and DevOps & Configuration:
1. **Core Pipeline:** Identified OpenCV `_deskew` coordinate transposition in `preprocessing.py` causing ~84.3° rotation error; `CircuitOpenError` swallowing in `PromptedGroundedOCR`; preprocessing crop/deskew bounding box coordinate drift at PDF embedding boundary; and script detector 1st-block bias in `TrustOrchestrator`.
2. **API & Security:** Identified `MaxUploadSizeMiddleware` instance state race condition under concurrent streaming uploads; `0.0.0.0` and IPv4-mapped IPv6 SSRF bypasses in `security.py`; in-memory `BearerAuthMiddleware` stale token caching bypassing runtime token rotation; and unbuffered full-file memory reading in `/api/transcribe`.
3. **Frontend:** Identified `ExportModal.svelte` contract break (missing token, 0-byte Markdown, corrupt JSON, undownloaded DOCX); dual disconnected `ProviderModal` stores making "Browse Presets" a no-op; undownloaded HTML/DOCX in `ExtractionView`; and unmanaged `setInterval` leak on tab switch in `TranslationView`.
4. **Testing & QA:** Identified `live_llm` marker phantom (0 tests defined, causing command exit code 5); `slow_dataset` tests leaking into PR fast-tier CI; critical coverage blindspots in `WhisperLocalEngine` (0 tests) and `docx_tree_writer.py`; and assertion bypass antipattern in Celery task test.
5. **DevOps & Config:** Identified missing `curl` in Dockerfile runtime stage breaking `compose.yaml` healthcheck; `stop_app.bat` failing to match `omniscribe-server` CLI entrypoint; and missing `--extra async-translation` in `install.ps1` breaking Celery workers on Windows.

## See Also

- [README.md](README.md) — feature overview, install, web workspace
- [CHANGELOG.md](CHANGELOG.md) — version history and breaking changes
- [DEPLOYMENT.md](DEPLOYMENT.md) — local / LAN / public-internet deployment profiles
- [SECURITY.md](SECURITY.md) — threat model, hardening checklist, vulnerability disclosure
- [AGENTS.md](AGENTS.md) — contributor guide and full env-var reference

_Last updated: 2026-08-17_


