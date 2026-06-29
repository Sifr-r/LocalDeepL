# AGENTS.md

This file tells coding agents and contributors how to work with this repository.

## Quick Start

```bash
uv sync
uv sync --extra web
uv sync --extra web --extra async-translation
uv run local-deepl-server --port 8000
```

Real OCR requires an OpenAI-compatible VLM endpoint. The default is LM Studio at `http://localhost:1234/v1`.

## Validation

```bash
uv run pytest
uv run pytest -m "not slow"
uv run pytest -m slow
uv run pytest tests/test_aligner.py -v
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
```

- `pytest-asyncio` uses auto mode. Write `async def test_...` without decorators.
- Slow tests load Surya and may download its model on the first run.
- Markers are `slow` and `live_llm`.

## Conventions

- Python 3.11 or newer. Use `uv`; do not install dependencies with `pip`.
- Prefer self-documenting code and docstrings. Add comments only when they clarify non-obvious behavior.
- Keep `tqdm_patch.apply()` before `from surya.detection import DetectionPredictor` in `core/aligner.py`.
- Keep bboxes normalized as `[x0, y0, x1, y1]` in `0..1` until `PDFHandler.embed_structured_text`.
- Treat image inputs as first-class inputs. PDF and image paths share the output writer.
- LocalDeepL is Web UI/API-first. The user-facing `local-deepl` CLI script has been deprecated; do not add or restore it. `OCRPipeline` is still importable for in-process programmatic use (e.g. an embedded workflow), but no script entry is shipped.
- Keep local document processors selectable through web/API `document_processors`. Current names are `reading_order`, `quality_analysis`, `structure_analysis`, `section_analysis`, `layout_enrichment`, and `table_extraction`; defaults run no processors.

## Pipeline Paths

```text
PDF/image -> pages -> Surya detection -> sparse: full-page OCR -> DP alignment -> refine --+
                                    \-> dense: per-box OCR -------------------------------+-> post-process -> DocumentResult -> optional processors -> searchable PDF

PDF/image -> grounded bbox-native VLM -> post-process -> DocumentResult -> optional processors -> searchable PDF
```

- Hybrid is the default: Surya detection, VLM OCR, DP alignment, optional refine, optional post-processing, embed.
- Dense hybrid pages use per-box OCR. `dense_mode="auto"` switches when box count exceeds `dense_threshold`.
- Grounded OCR uses `grounded_backend=` and skips Surya, DP alignment, and refine.

## Key Files

| File | Role |
| --- | --- |
| `src/local_deepl/server.py` | FastAPI application, server entry point, `local-deepl-server` script |
| `src/local_deepl/pipeline.py` | `OCRPipeline` facade — picks `HybridEngine` or `GroundedEngine` based on injected components |
| `src/local_deepl/evaluation.py` | Package-root confidence eval (fixture loader, IoU matching, `ConfidenceReport`) for `scripts/confidence_*.py` |
| `src/local_deepl/core/document.py` | Normalized DocumentResult IR and legacy pages-data adapter |
| `src/local_deepl/core/processors.py` | Local deterministic document processors and user-facing processor builder |
| `src/local_deepl/core/preprocessing.py` | Local hybrid-path page preprocessing |
| `src/local_deepl/core/routing.py` | Quality routing recommendation metadata |
| `src/local_deepl/core/evaluation.py` | Local evaluation metric helpers (lightweight, for processor result scoring) |
| `src/local_deepl/core/docx_writer.py` | Markdown → `.docx` converter for the docx export route |
| `src/local_deepl/core/aligner.py` | Surya detection and DP alignment |
| `src/local_deepl/core/ocr.py` | LiteLLM OCR calls, prompts, limits, and filters |
| `src/local_deepl/core/pdf.py` | PDF/image conversion and sandwich-PDF embedding |
| `src/local_deepl/core/grounded.py` | Grounded backends and bbox JSON parsers |
| `src/local_deepl/core/postprocess.py` | Dictionary spellcheck |
| `src/local_deepl/core/translation_config.py` | Core-owned async translation settings |
| `src/local_deepl/core/translation.py` | Optional LangGraph translation workflow |
| `src/local_deepl/core/workflows/base.py` | `EngineBase` + `OutputWriter` / `ProgressCallback` / `WarningCallback` shared by both engines |
| `src/local_deepl/core/workflows/hybrid.py` | `HybridEngine` — Surya detect → VLM OCR → DP align → refine → post-process → processors → output |
| `src/local_deepl/core/workflows/grounded.py` | `GroundedEngine` — single bbox-native VLM call → post-process → processors → output |
| `src/local_deepl/resources/dictionaries/` | Packaged spellcheck dictionaries |
| `src/local_deepl/api/routers/config.py` | Runtime configuration and model discovery |
| `src/local_deepl/api/routers/ocr.py` | OCR upload, process, and synchronous AI routes |
| `src/local_deepl/api/routers/websocket.py` | Token-bound WebSocket progress transport |
| `src/local_deepl/api/routers/jobs.py` | `GET/DELETE /api/jobs` — job history and clear-all |
| `src/local_deepl/api/routers/artifacts.py` | Token-bound artifact download routes (text, metadata, exports) |
| `src/local_deepl/api/routers/translation.py` | Synchronous and async translation routes |
| `src/local_deepl/api/routers/extraction.py` | `POST /api/extract` and `POST /api/export/*` routes |
| `src/local_deepl/api/routers/state.py` | Module-level singletons (`text_artifacts`, `metadata_artifacts`, `export_artifacts`, `job_history`, `progress_service`) |
| `src/local_deepl/api/routers/common.py` | Shared router helpers (`_stable_server_error`, `_extract_bearer_token`, `_path_exists`) |
| `src/local_deepl/api/routers/ai.py` | AI service module consumed by `extraction.py` and `translation.py` |
| `src/local_deepl/api/schemas/requests.py` | `ConfigUpdate`, `ProcessSettings`, `TranslationRequest`, `ExtractionRequest`, `ExtractionTemplate`, `DocumentExportRequest`, `DocumentExportFormat`, `ExportDocxRequest`; enums: `PipelineMode`, `DenseMode`, `SpellcheckMode`, `DocumentProcessorName` |
| `src/local_deepl/api/services/security.py` | API upload validation, stable error constants, temporary-file cleanup, opaque text artifact IDs |
| `src/local_deepl/api/services/security_config.py` | `SecuritySettings.from_env()` — env-driven knobs for `LOCAL_DEEPL_AUTH_TOKEN`, `_CORS_ORIGINS`, `_MAX_UPLOAD_MB`, `_RATE_LIMIT_PER_MIN` |
| `src/local_deepl/api/services/security_middleware.py` | ASGI middlewares wired by `server.create_app()`: `BearerAuthMiddleware` (constant-time `secrets.compare_digest`), `MaxUploadSizeMiddleware` (rejects on `Content-Length`), `RateLimitMiddleware` (per-IP 60s sliding window, in-memory). WebSocket handshake auth is still enforced per-channel in `routers/websocket.py` |
| `src/local_deepl/api/services/artifacts.py` | `TextArtifactStore`, `PageText`, `TextArtifactHandle`, opaque id / token primitives |
| `src/local_deepl/api/services/jobs.py` | `JobHistory`, `JobRecord`, `JobStatus` |
| `src/local_deepl/api/services/progress.py` | `ProgressService`, `ProgressChannel`, stage weights |
| `src/local_deepl/api/services/document_metadata.py` | Token-bound metadata report artifacts for optional document processor outputs |
| `src/local_deepl/api/services/document_exports.py` | Token-bound document export artifacts |
| `src/local_deepl/api/services/workflow.py` | Web/API workflow summaries |
| `src/local_deepl/api/services/ai.py` | Backing AI service for extraction and translation routes |
| `src/local_deepl/utils/security.py` | SSRF target validation |
| `src/local_deepl/utils/litellm_provider.py` | LiteLLM provider selection |
| `scripts/` | Developer utilities: confidence eval, fixture builder, debug/inspection scripts, bbox visualizers |
| `examples/` | Sample PDFs and images for `tests/`, `test_ui.py`, and the confidence scripts |
| `install.bat` / `install.ps1` / `start_app.vbs` / `stop_app.bat` / `test_ui.py` | Windows one-click install, hidden-start, stop, and Playwright smoke test |

## Extension Points

`OCRPipeline` accepts injected components:

- `aligner=`: layout detection and text alignment
- `ocr_processor=`: page and crop OCR backend
- `pdf_handler=`: input conversion and default PDF writer
- `output_writer=`: alternate output generation
- `grounded_backend=`: bbox-native OCR path
- `document_processors=`: sequence of `DocumentProcessor` instances run after OCR cleanup and before PDF embedding
- `page_preprocessor=`: opt-in `PagePreprocessor` for orientation/deskew/denoise/contrast/crop preprocessing on the hybrid image path

## Web Notes

- Browser translation and structured extraction use synchronous endpoints and do not require Redis.
- `/api/translate/async` uses Celery, Redis, and LangGraph from the `async-translation` extra.
- `ALLOW_SSRF_LOCAL=true` is the local-development default. Set it to `false` when exposing the server to untrusted users.
- Web runtime settings are initialized in `api/routers/config.py`.
- **Windows quick-start**: run `install.bat` to install `uv`, sync the web extra, and create Desktop / Start-Menu shortcuts. `start_app.vbs` boots Redis + Celery + uvicorn hidden and opens the browser. `stop_app.bat` terminates them. `test_ui.py` is the headless Playwright smoke test against `examples/dense.pdf`.
- **Developer scripts** live in `scripts/`. The most useful for OCR quality work are `scripts/confidence_eval.py` (hybrid + grounded vs the `examples/*.pdf` fixtures) and `scripts/confidence_image.py` (single-image confidence). The rest are debug/inspection/visualization tools.

## Known Tech Debt

- `api/routers/ocr.py` mixes OCR, translation, extraction, and asynchronous task routes.
- The grounded web route instantiates hybrid components even though `OCRPipeline` skips them in grounded mode.
- `ZAIHostedOCR` remains an experimental backend.

## Product-Planning Notes (scout plans, not code)

External scout plans live in `.mavis/plans/scout/`. The most recent
plan (2026-06-14) has four tracks plus a synthesis plan:

- `track-md.md` — Anything-to-Markdown / rich-text converter
  landscape (29 players: Microsoft / Google / Adobe / Apple / OSS).
  Headline finding: OSS has converged on three pipeline patterns
  (local-only / local+VLM / VLM-only) with LocalDeepL in the
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
