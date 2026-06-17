# Architecture Ledger

## System Shape

`local-deepl` is a Python 3.11+ Web UI/API OCR application with a shared
pipeline behind the FastAPI server. Inputs are PDFs or images. Outputs are
searchable sandwich PDFs with normalized OCR bounding boxes embedded as an
invisible text layer.

## Pipeline

```text
PDF/image -> raster pages -> Surya detection -> sparse: full-page VLM OCR -> DP alignment --+
                                      \-> dense: per-box VLM OCR ---------------------------+-> optional refine -> optional post-process -> DocumentResult -> optional document processors -> searchable PDF

PDF/image -> grounded bbox-native VLM OCR -> optional post-process -> DocumentResult -> optional document processors -> searchable PDF
```

## Directory Responsibilities

| Path | Single Responsibility |
| --- | --- |
| `src/local_deepl/__init__.py` | Lazy package-level public exports that avoid loading OCR or web dependencies during unrelated submodule imports |
| `src/local_deepl/server.py` | Lazy optional-web dependency loading, FastAPI application setup, CLI argument parsing for `--host/--port/--reload`, and `local-deepl-server` script entry point |
| `src/local_deepl/pipeline.py` | `OCRPipeline` facade — thin orchestration layer that delegates to `HybridEngine` or `GroundedEngine` based on injected components |
| `src/local_deepl/evaluation.py` | Package-root confidence evaluator: GLM-OCR fixture loader, greedy IoU matching, and per-document `ConfidenceReport` for the `scripts/confidence_*.py` tooling |
| `src/local_deepl/core/document.py` | Normalized `DocumentResult` IR, pages, blocks, spans, text aggregation, and legacy pages-data adapter |
| `src/local_deepl/core/processors.py` | Local deterministic document processor protocol, registry, six built-in processors, and the user-facing name-to-factory builder |
| `src/local_deepl/core/aligner.py` | Surya detection and DP text-to-box alignment |
| `src/local_deepl/core/ocr.py` | OpenAI-compatible VLM calls, prompts, limits, and OCR response filters |
| `src/local_deepl/core/pdf.py` | PDF/image conversion and searchable PDF embedding |
| `src/local_deepl/core/grounded.py` | Grounded OCR backends and bbox-native response parsing |
| `src/local_deepl/core/postprocess.py` | Dictionary-based spellcheck post-processing |
| `src/local_deepl/core/preprocessing.py` | Local hybrid-path page preprocessing (orientation detection, deskew, denoise, contrast normalization, crop cleanup) |
| `src/local_deepl/core/routing.py` | Quality routing recommendation metadata and policy recorder |
| `src/local_deepl/core/evaluation.py` | Lightweight `EvaluationMetrics` dataclass and `evaluate_document` helper for in-process processor result scoring |
| `src/local_deepl/core/docx_writer.py` | Markdown → `.docx` converter used by the docx export route |
| `src/local_deepl/core/translation_config.py` | Core-owned typed settings and optional-feature errors for async translation |
| `src/local_deepl/core/translation.py` | Optional LangGraph translation workflow |
| `src/local_deepl/core/workflows/base.py` | `EngineBase`, `OutputWriter`, `ProgressCallback`, `WarningCallback` shared by both engines |
| `src/local_deepl/core/workflows/hybrid.py` | `HybridEngine` — Surya detect → VLM OCR (sparse/dense) → DP align → optional refine → post-process → processors → output |
| `src/local_deepl/core/workflows/grounded.py` | `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/local_deepl/core/workflows/__init__.py` | Re-exports `EngineBase`, `HybridEngine`, `GroundedEngine`, and the callback type aliases |
| `src/local_deepl/resources/dictionaries/` | Packaged compiled spellcheck dictionaries loaded before legacy repository-root dictionaries |
| `src/local_deepl/api/routers/config.py` | Runtime configuration and model discovery routes (`GET/POST /api/config`) |
| `src/local_deepl/api/routers/ocr.py` | OCR upload, process, and synchronous AI routes |
| `src/local_deepl/api/routers/websocket.py` | Token-bound WebSocket progress transport and progress session issuance |
| `src/local_deepl/api/routers/jobs.py` | `GET/DELETE /api/jobs` — recent job history and clear-all |
| `src/local_deepl/api/routers/artifacts.py` | Token-bound artifact download routes for text, metadata, and document exports |
| `src/local_deepl/api/routers/translation.py` | Synchronous `POST /api/translate` and async `POST /api/translate/async` |
| `src/local_deepl/api/routers/extraction.py` | `POST /api/extract` — structured data extraction over OCR text using a built-in template or custom prompt |
| `src/local_deepl/api/routers/state.py` | Module-level singletons: `text_artifacts`, `metadata_artifacts`, `export_artifacts`, `job_history`, `progress_service` |
| `src/local_deepl/api/routers/common.py` | Shared router helpers: `_stable_server_error`, `_extract_bearer_token`, `_path_exists`, `_cleanup` |
| `src/local_deepl/api/routers/ai.py` | Underlying AI service module — `extract_structured_data`, `translate_text`, and the `AIServiceError` base; consumed by `extraction.py` and `translation.py` |
| `src/local_deepl/api/schemas/__init__.py` | Re-exports the typed request models and StrEnums |
| `src/local_deepl/api/schemas/requests.py` | `ConfigUpdate`, `ProcessSettings`, `TranslationRequest`, `ExtractionRequest`, `ExtractionTemplate`, `DocumentExportRequest`, `DocumentExportFormat`, `ExportDocxRequest`; enums: `PipelineMode`, `DenseMode`, `SpellcheckMode`, `DocumentProcessorName` |
| `src/local_deepl/api/services/security.py` | API upload validation, stable error constants, temporary-file cleanup, and opaque text artifact IDs |
| `src/local_deepl/api/services/artifacts.py` | `TextArtifactStore`, `PageText`, `TextArtifactHandle`, and the opaque artifact-id / token primitives shared by text, metadata, and export stores |
| `src/local_deepl/api/services/jobs.py` | `JobHistory`, `JobRecord`, `JobStatus` — durable job history with per-page failure tracking |
| `src/local_deepl/api/services/progress.py` | `ProgressService`, `ProgressChannel`, stage weights, channel/session token validation |
| `src/local_deepl/api/services/document_metadata.py` | Compact JSON report builder and atomic writer for token-bound `DocumentResult` metadata artifacts |
| `src/local_deepl/api/services/document_exports.py` | Token-bound JSON, Markdown, text, Docling-compatible, and MinerU-compatible export artifact builder |
| `src/local_deepl/api/services/workflow.py` | Deterministic Web/API workflow summary builder |
| `src/local_deepl/api/services/ai.py` | AI service module backing `POST /api/extract` and `POST /api/translate` — OpenAI-compatible calls with fenced-JSON parsing, retry, and stable error mapping |
| `src/local_deepl/api/celery_app.py` | Guarded Celery imports and import-safe fallback task facade when async extras are not installed |
| `src/local_deepl/api/tasks.py` | Optional Celery translation task execution |
| `src/local_deepl/utils/image.py` | Image crop, blank-region detection, and crop encoding helpers |
| `src/local_deepl/utils/security.py` | SSRF target validation |
| `src/local_deepl/utils/litellm_provider.py` | LiteLLM provider selection |
| `src/local_deepl/utils/tqdm_patch.py` | Surya progress-bar suppression |
| `src/local_deepl/static/` | Browser workstation assets (`index.html`, CSS, JS modules) |
| `scripts/` | Repo-root developer utilities: confidence eval, fixture builder, debug/inspection scripts, bbox visualizers |
| `examples/` | Sample PDFs and images used by `tests/`, `test_ui.py`, and the confidence scripts |
| `tests/` | Unit, integration, security, and slow-path validation |
| `install.bat` / `install.ps1` | Windows one-click install: `uv` bootstrap, `uv sync --extra web`, Docker check, Desktop/Start-Menu shortcuts |
| `start_app.vbs` / `stop_app.bat` | Windows hidden-start and stop-launcher for Redis + Celery + uvicorn |
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

Process-local singletons live in `src/local_deepl/api/routers/state.py` and are
imported by every router that needs them. Three independent `TextArtifactStore`
instances back the three artifact surfaces:

| Singleton | Surface | Token-bound header | Read endpoint |
| --- | --- | --- | --- |
| `text_artifacts` | Per-job searchable text | `X-Text-Artifact-Id` / `X-Text-Artifact-Token` | `GET /text/{artifact_id}` |
| `metadata_artifacts` | Compact `DocumentResult` page/block metadata | `X-Document-Metadata-Artifact-Id` / `X-Document-Metadata-Artifact-Token` | `GET /metadata/{artifact_id}` |
| `export_artifacts` | JSON / Markdown / text / Docling / MinerU exports | `X-Document-Export-Artifact-Id` / `X-Document-Export-Artifact-Token` | `GET /exports/{artifact_id}` |

`job_history` (`JobHistory`) and `progress_service` (`ProgressService`) round
out the shared state. The store implementation lives in
`api/services/artifacts.py` and the token format is the same opaque
hex-id / bearer-token pair across all three surfaces.

## Web API Surface (non-exhaustive)

| Method | Path | Router | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/config` | `config` | Current runtime config (api_base, model, spellcheck, …) |
| `POST` | `/api/config` | `config` | `ConfigUpdate` — typed config edits |
| `POST` | `/api/ocr` | `ocr` | Multipart OCR; returns a sandwich PDF + token-bound headers |
| `POST` | `/api/translate` | `translation` | Synchronous translation over OCR text |
| `POST` | `/api/translate/async` | `translation` | Celery + Redis job (requires `async-translation` extra) |
| `POST` | `/api/extract` | `extraction` | Structured extraction using `ExtractionTemplate` (`invoice`, `resume`, `academic`, `custom`) |
| `GET` / `DELETE` | `/api/jobs` | `jobs` | Recent job history; `DELETE` clears history and text artifacts |
| `GET` | `/text/{artifact_id}` | `artifacts` | Text artifact body (token in `Authorization: Bearer …`) |
| `GET` | `/metadata/{artifact_id}` | `artifacts` | Metadata artifact body |
| `GET` | `/exports/{artifact_id}` | `artifacts` | Export artifact body |
| `WS` | `/ws/progress/{channel_id}?token=…` | `websocket` | Token-bound per-job progress stream |
| `POST` | `/api/export/document` | `extraction` | Build a token-bound export artifact |
| `POST` | `/api/export/docx` | `extraction` | Build a `.docx` from Markdown page text |

## Change Blueprint

### 2026-06-14: Engine split — `core/workflows/` package

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/workflows/base.py` | New `EngineBase` plus `OutputWriter`, `ProgressCallback`, `WarningCallback`, and `_notify` helpers shared by both engines |
| `src/local_deepl/core/workflows/hybrid.py` | New `HybridEngine` — extract the existing hybrid orchestration from `pipeline.py` (Surya detect → VLM OCR → DP align → refine → post-process → processors → output) |
| `src/local_deepl/core/workflows/grounded.py` | New `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/local_deepl/core/workflows/__init__.py` | Re-export the engines and callback aliases |
| `src/local_deepl/pipeline.py` | Shrink `OCRPipeline` to a facade that picks `HybridEngine` or `GroundedEngine` based on injected components |
| `ARCHITECTURE.md` | Document the new sub-package and the facade pattern in `pipeline.py` |

### 2026-06-14: DOCX export route + `core/docx_writer.py`

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/docx_writer.py` | New `convert_markdown_to_docx(markdown_text: str) -> io.BytesIO` helper |
| `src/local_deepl/api/schemas/requests.py` | New `ExportDocxRequest` typed schema |
| `src/local_deepl/api/routers/extraction.py` | New `POST /api/export/docx` route that streams the generated `.docx` |
| `pyproject.toml` | Already lists `python-docx>=1.1.0` (no change required) |
| `ARCHITECTURE.md` | Document the docx export in the directory table and the Web API surface |

### 2026-06-14: Confidence evaluation scripts and root-level `evaluation.py`

| File | Responsibility |
| --- | --- |
| `src/local_deepl/evaluation.py` | New package-root module: `GTBlock`, `BlockMatch`, `ConfidenceReport`, `load_ground_truth`, `text_similarity`, `compute_report`, `iou` (auto-detects `[x0,y0,x1,y1]` vs `[y0,x0,y1,x1]` fixture axis order) |
| `scripts/confidence_eval.py` | New developer script — runs hybrid and grounded paths against `examples/*.pdf` and reports per-document block recall, IoU, and text similarity |
| `scripts/confidence_image.py` | New developer script — same comparison on a single image, defaults to `examples/image.avif` |
| `examples/` | New sample inputs (`dense.pdf`, `digital.pdf`, `handwritten.pdf`, `hybrid.pdf`, `image.png`, `image.avif`, `notes.pdf`) |
| `tests/test_evaluation.py` | Cover fixture loading, axis-order detection, and `ConfidenceReport` aggregation |
| `ARCHITECTURE.md` | Document the root-level confidence eval vs the lightweight `core/evaluation.py` processor-metrics helper |

### 2026-06-14: `POST /api/extract` and `ExtractionTemplate` enum

| File | Responsibility |
| --- | --- |
| `src/local_deepl/api/schemas/requests.py` | New `ExtractionTemplate` StrEnum (`invoice`, `resume`, `academic`, `custom`) and the `ExtractionRequest` model with `template` and `custom_prompt` fields |
| `src/local_deepl/api/routers/ai.py` | New `extract_structured_data` service with fenced-JSON parsing, retry, and stable error mapping |
| `src/local_deepl/api/routers/extraction.py` | New router that wires the schema, the AI service, and the SSRF guard for `api_base` |
| `tests/test_extraction.py` | Cover template dispatch, custom-prompt fallback, and SSRF fail-closed behavior |
| `ARCHITECTURE.md` | Document the new router and the four extraction templates in the Web API surface |

### 2026-06-09: Local document processors exposed to web/API

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/document.py` | Provide the normalized `DocumentResult` handoff used by post-OCR document processors |
| `src/local_deepl/core/processors.py` | Define built-in local processors and map user-facing names to deterministic processor instances |
| `src/local_deepl/api/schemas/requests.py` | Validate `document_processors` for config JSON and multipart OCR requests |
| `src/local_deepl/api/routers/ocr.py` | Instantiate selected processors, pass them into `OCRPipeline`, and expose quality metadata through `X-Document-Quality` when available |
| `src/local_deepl/static/js/state_and_api.js` | Persist and submit web-selected document processors |
| `src/local_deepl/static/index.html` | Expose Reading Order, Quality Analysis, Structure Analysis, and Section Analysis toggles in Advanced Configuration |
| `tests/test_document_processor_selection.py` | Cover processor selection parsing, validation, and factory mapping |

### 2026-06-09: Stage 2 local structure analysis processor

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/processors.py` | Add `structure_analysis`, a deterministic local processor that classifies blocks as headings, paragraphs, list items, key-values, table candidates, or empty blocks |
| `src/local_deepl/api/routers/ocr.py` | Expose page-level structure summaries through `X-Document-Structure` when structure metadata is present |
| `src/local_deepl/static/index.html` | Add the Structure Analysis opt-in control |
| `tests/test_document.py` | Cover block classification without rewriting output text |

### 2026-06-09: Stage 3 local section analysis processor

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/processors.py` | Add `section_analysis`, a deterministic local processor that assigns blocks to detected heading sections across page boundaries |
| `src/local_deepl/api/routers/ocr.py` | Expose page-level section summaries through `X-Document-Sections` when section metadata is present |
| `src/local_deepl/static/index.html` | Add the Section Analysis opt-in control |
| `tests/test_document.py` | Cover section grouping while preserving original block text |

### 2026-06-09: Stage 4 document metadata artifact surface

| File | Responsibility |
| --- | --- |
| `src/local_deepl/api/services/document_metadata.py` | Build compact JSON-safe metadata reports from `DocumentResult` page/block processor annotations and write them atomically as temporary artifacts |
| `src/local_deepl/api/routers/ocr.py` | Issue `X-Document-Metadata-Artifact-Id` and `X-Document-Metadata-Artifact-Token` only when report content exists, and serve protected `GET /metadata/{artifact_id}` |
| `tests/test_api_safety.py` | Cover token-bound metadata artifact access and payload shape without changing text artifact behavior |

### 2026-06-09: Stage 5-12 Web/API document intelligence

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Deprecate the user-facing `local-deepl` CLI script and drop the CLI-only `rich` dependency; keep `local-deepl-server`. `OCRPipeline` is still importable for in-process programmatic use. |
| `src/local_deepl/core/preprocessing.py` | Add opt-in local page preprocessing diagnostics for the hybrid image path |
| `src/local_deepl/core/processors.py` | Add `layout_enrichment` and `table_extraction` deterministic processors |
| `src/local_deepl/api/services/document_exports.py` | Add token-bound JSON, Markdown, text, Docling-compatible, and MinerU-compatible exports |
| `src/local_deepl/core/routing.py` | Record default-off quality routing recommendations in document metadata |
| `src/local_deepl/api/services/workflow.py` | Expose deterministic Web/API workflow summaries |
| `src/local_deepl/core/evaluation.py` | Add local evaluation metrics for text, bbox, reading-order, and table coverage |

### 2026-06-02: Direct grounded PDF pixmap conversion

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/grounded.py` | Convert PDF pixmaps directly into Pillow images before emitting the final grounded OCR thumbnail JPEG |
| `tests/test_grounded.py` | Guard against restoring the redundant intermediate JPEG decode |
| `ARCHITECTURE.md` | Record the existing module layout and the direct pixmap conversion invariant |

### 2026-06-02: Stage 1 API and browser safety hardening

| File | Responsibility |
| --- | --- |
| `src/local_deepl/api/schemas/requests.py` | Validate config JSON, OCR multipart settings, translation requests, and extraction requests with explicit enums, booleans, and numeric ranges |
| `src/local_deepl/api/services/security.py` | Enforce streaming upload byte limits, content-signature upload type detection, stable API error messages, and server-issued text artifact IDs |
| `src/local_deepl/api/routers/config.py` | Apply typed config validation, SSRF checks, safe environment parsing, and non-leaking model discovery errors |
| `src/local_deepl/api/routers/ocr.py` | Apply typed OCR/AI boundary validation, hardened upload dispatch, opaque text artifact retrieval, SSRF checks, and stable client-facing errors |
| `src/local_deepl/utils/security.py` | Fail closed for malformed, unsupported, or unresolvable URLs and only allow local/private endpoints when `ALLOW_SSRF_LOCAL=true` is explicitly set |
| `src/local_deepl/static/js/app.js` | Use server-issued text artifact IDs and render extraction status/errors/cards without HTML injection |
| `src/local_deepl/static/js/state_and_api.js` | Build model select placeholder with DOM APIs before appending model-controlled option text |
| `src/local_deepl/static/js/workspace_ui.js` | Provide safe DOM helpers for clearing elements and rendering extraction status cards |
| `tests/test_api_safety.py` | Cover config validation, SSRF fail-closed behavior, streaming upload validation, opaque text artifacts, stable API errors, and static JS sink removal |
| `tests/test_security_qa.py` | Keep extraction JSON parsing deterministic under fail-closed SSRF validation |

### 2026-06-03: Optional async translation boundary

| File | Responsibility |
| --- | --- |
| `src/local_deepl/core/translation_config.py` | Own typed translation settings and the deterministic optional-feature error used by core and API boundaries |
| `src/local_deepl/core/translation.py` | Keep chunking and evaluation helpers importable without async extras, lazily build the LangGraph workflow, and accept injected translation settings |
| `src/local_deepl/api/routers/config.py` | Adapt the mutable web runtime config into core-owned translation settings without exposing `_config` to core modules |
| `src/local_deepl/api/celery_app.py` | Guard Celery imports and provide an import-safe fallback task facade when async extras are not installed |
| `src/local_deepl/api/tasks.py` | Validate async translation task inputs and pass explicit translation settings into the core workflow |
| `src/local_deepl/api/routers/ocr.py` | Validate async translation route inputs and return deterministic 503 responses when optional async extras are unavailable |
| `pyproject.toml` | Move Celery, Redis, LangGraph, ChromaDB, and sentence-transformers into the `async-translation` extra with `translation` as an alias extra |
| `tests/test_translation_boundary.py` | Cover guarded imports without async extras and explicit translation settings injection |

### 2026-06-03: Spellcheck resource package cleanup

| File | Responsibility |
| --- | --- |
| `src/local_deepl/resources/dictionaries/ara.json.gz` | Packaged Arabic compiled spellcheck dictionary for installed distributions |
| `src/local_deepl/resources/dictionaries/eng.json.gz` | Packaged English compiled spellcheck dictionary for installed distributions |
| `src/local_deepl/core/postprocess.py` | Load packaged dictionaries first while retaining legacy repository-root and user-cache fallbacks |
| `pyproject.toml` | Exclude bytecode cache artifacts from Hatch package builds |
| `tests/test_dictionary_postprocess.py` | Cover packaged dictionary lookup and legacy repository-root fallback |

### 2026-06-03: Lazy web server imports

| File | Responsibility |
| --- | --- |
| `src/local_deepl/__init__.py` | Preserve package-level OCR exports through lazy lookups so `import local_deepl.server` does not load OCR core dependencies first |
| `src/local_deepl/server.py` | Preserve `local_deepl.server:app` and `local_deepl.server:main` while deferring FastAPI, router, static-file, and uvicorn imports until the web app is created or run |
| `tests/test_server_lazy_imports.py` | Verify base-install-safe `local_deepl.server` imports and deterministic missing-web-extra errors without uninstalling FastAPI |
| `ARCHITECTURE.md` | Record the optional-web lazy import boundary for the server module |
