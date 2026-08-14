# AGENTS.md

This file tells coding agents and contributors how to work with this repository.

## Quick Start

```bash
uv sync
uv sync --extra web
uv sync --extra web --extra async-translation
uv run omniscribe-server --port 8000
```

Real OCR requires an OpenAI-compatible VLM endpoint. The default is LM Studio at `http://localhost:1234/v1`.

## Validation

```bash
uv run pytest
uv run pytest -m "not slow"
uv run pytest -m slow
uv run pytest -m live_llm
uv run pytest tests/test_aligner.py -v
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
cd frontend && npm run check && npm test && npm run build
```

- `pytest-asyncio` uses auto mode. Write `async def test_...` without decorators.
- Slow tests load Surya and may download its model on the first run.
- Markers are `slow` and `live_llm`. Run `live_llm` tests manually with `uv run pytest -m live_llm` against a local LM Studio instance (`http://localhost:1234/v1`).

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
| `src/omniscribe/core/ocr/` | LiteLLM OCR calls, prompts, limits, filters, and resilience (retry + circuit breaker) |
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
| `src/omniscribe/api/routers/config.py` | Runtime configuration and model discovery |
| `src/omniscribe/api/routers/ocr.py` | OCR upload, process, and synchronous AI routes |
| `src/omniscribe/api/routers/websocket.py` | Token-bound WebSocket progress transport |
| `src/omniscribe/api/routers/jobs.py` | `GET/DELETE /api/jobs` — job history and clear-all |
| `src/omniscribe/api/routers/artifacts.py` | Token-bound artifact download routes (text, metadata, exports) |
| `src/omniscribe/api/routers/translation.py` | Synchronous and async translation routes |
| `src/omniscribe/api/routers/extraction.py` | `POST /api/extract` and `POST /api/export/*` routes |
| `src/omniscribe/api/routers/state.py` | Module-level singletons (`text_artifacts`, `metadata_artifacts`, `export_artifacts`, `job_history`, `progress_service`) |
| `src/omniscribe/api/routers/common.py` | Shared router helpers (`_stable_server_error`, `_extract_bearer_token`, `_path_exists`) |
| `src/omniscribe/api/schemas/requests.py` | `ConfigUpdate`, `ProcessSettings`, `TranslationRequest`, `ExtractionRequest`, `ExtractionTemplate`, `DocumentExportRequest`, `DocumentExportFormat`, `ExportDocxRequest`; enums: `PipelineMode`, `DenseMode`, `SpellcheckMode`, `DocumentProcessorName` |
| `src/omniscribe/api/services/security.py` | API upload validation, stable error constants, temporary-file cleanup, opaque text artifact IDs |
| `src/omniscribe/api/services/security_config.py` | `SecuritySettings.from_env()` — env-driven knobs for `OMNISCRIBE_AUTH_TOKEN`, `_CORS_ORIGINS`, `_MAX_UPLOAD_MB`, `_RATE_LIMIT_PER_MIN` |
| `src/omniscribe/api/services/security_middleware.py` | ASGI middlewares wired by `server.create_app()`: `BearerAuthMiddleware` (constant-time `secrets.compare_digest`), `MaxUploadSizeMiddleware` (rejects on `Content-Length`), `RateLimitMiddleware` (per-IP 60s sliding window, in-memory). WebSocket handshake auth is still enforced per-channel in `routers/websocket.py` |
| `src/omniscribe/api/services/artifacts.py` | `TextArtifactStore`, `PageText`, `TextArtifactHandle`, opaque id / token primitives |
| `src/omniscribe/api/services/jobs.py` | `JobHistory`, `JobRecord`, `JobStatus` |
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

## Web Notes

- Browser translation and structured extraction use synchronous endpoints and do not require Redis.
- `/api/translate/async` uses Celery, Redis, and LangGraph from the `async-translation` extra. The translation module degrades gracefully when ChromaDB is not installed (no lexicon retrieval); install the separate `memory` extra (ChromaDB + sentence-transformers) for the lexicon-backed RAG feature.
- `ALLOW_SSRF_LOCAL=true` is the local-development default. Set it to `false` when exposing the server to untrusted users.
- **Auth**: set `OMNISCRIBE_AUTH_TOKEN` to require `Authorization: Bearer <token>` on every HTTP route (constant-time compare, ASGI middleware). Unset = open (local-desktop default).
- **VLM resilience**: every LLM call retries transient errors (429/5xx/connection resets) with exponential backoff, and a per-request circuit breaker fails fast after `OMNISCRIBE_CB_FAILURE_THRESHOLD` (default 5) consecutive failures. Tunables: `OMNISCRIBE_LLM_MAX_RETRIES` (default 2), `OMNISCRIBE_LLM_RETRY_BASE_DELAY` (default 1.0s), `OMNISCRIBE_CB_COOLDOWN` (default 30s).
- **Model pre-flight**: each `/api/process` request verifies the configured model is actually loaded on the VLM server (`GET /v1/models`) before paying for conversion/detection — one extra HTTP round-trip per request, guarding against LM Studio's silent model fallback (issue #7).
- **Quality repair loop**: `/api/process` re-OCRs blocks whose estimated confidence is below the target (crop-scoped, sequential, accept-only-while-improving) after block emission and before embedding. Defaults ON at the API layer (up to 2 extra VLM passes per low-confidence block); in-process `OCRPipeline.run` callers stay off unless they pass `repair_options=`. Per-request form fields `quality_loop_enabled` / `quality_target` (0.5–1.0) / `quality_max_retries` (0–5); env seeds `OMNISCRIBE_QUALITY_LOOP`, `OMNISCRIBE_QUALITY_TARGET`, `OMNISCRIBE_QUALITY_MAX_RETRIES`. WebSocket frames: `block_retry`, `block_revised`, `quality_summary`.
- Web runtime settings are initialized in `api/routers/config.py`.
- **Windows quick-start**: run `install.bat` to install `uv`, sync the web extra, and create Desktop / Start-Menu shortcuts. `start_app.vbs` boots Redis (via Docker) + Celery + uvicorn hidden and opens the browser; it writes a timestamped append log to `start_app.log` next to itself. `stop_app.bat` terminates the uvicorn + Celery processes. `test_ui.py` is the headless Playwright smoke test against `examples/dense.pdf`.
- **Developer scripts** live in `scripts/`. The most useful for OCR quality work are `scripts/confidence_eval.py` (hybrid + grounded vs the `examples/*.pdf` fixtures) and `scripts/confidence_image.py` (single-image confidence). The rest are debug/inspection/visualization tools.
- **Docker**: `Dockerfile` builds a `python:3.12-slim` runtime with the `web` and `async-translation` extras. `compose.yaml` runs `api` + `redis` by default; add `--profile async` to also start a Celery worker. Image exposes port 8000; bind `LLM_API_BASE` to `http://host.docker.internal:1234/v1` to talk to a host-side LM Studio.
- **Pre-commit**: `.pre-commit-config.yaml` runs ruff (check + format) and `uv-lock` on every commit. Enable with `uv tool run pre-commit install` after cloning.
- **Nightly slow tests**: `.github/workflows/nightly.yml` runs `pytest -m slow` at 03:00 UTC with cached HF Hub snapshots, catching Surya-path regressions the fast tier skips.

## Known Tech Debt

- `/api/process` runs the full OCR pipeline synchronously on the uvicorn worker (no background task queue on the default path); long jobs block other requests on the same worker.
- Job/artifact state is in-memory only (`api/routers/state.py` singletons) — restarts lose history; no horizontal scaling.
- `pages_structured` legacy dict is still the working format inside `HybridEngine`; `DocumentResult` is built at finalize. The output boundary now supports the lossless rich path (`DocumentResultWriter`), but intermediate stages still convert.
- `dense.pdf` and `notes.pdf` ground-truth fixtures are bootstrapped from hybrid output (regression baseline, not absolute quality).
- `surya-ocr 0.17.x` imports `requests` in `surya/common/s3.py` without declaring it. `pyproject.toml` includes a `requests>=2.31` workaround dependency; track for cleanup once `surya-ocr` updates upstream.

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

_Last updated: 2026-08-14_
