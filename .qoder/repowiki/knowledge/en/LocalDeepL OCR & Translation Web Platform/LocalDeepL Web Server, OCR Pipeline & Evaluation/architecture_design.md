Three cooperating modules form the top of the LocalDeepL stack:
- `server.py` is the FastAPI entry point. It lazily constructs the ASGI app via `create_app()` wrapped in a `LazyASGIApp` so optional web dependencies (FastAPI, uvicorn, static files) are only imported when the server actually starts. Security middleware (`BearerAuthMiddleware`, `MaxUploadSizeMiddleware`, `RateLimitMiddleware`) and CORS are wired through `SecuritySettings.from_env()`. Routers for config, OCR, WebSocket, jobs, artifacts, translation, extraction, and glossary imports are included, and a `/static` mount serves the SPA.
- `pipeline.py` exposes `OCRPipeline`, a thin facade that selects either `GroundedEngine` or `HybridEngine` from `local_deepl.core.workflows` based on whether a `grounded_backend` is supplied. Both engine paths share the same `execute(...)` async interface, making the pipeline uniform for callers. Extension points: `aligner`, `ocr_processor`, `pdf_handler`, `output_writer`, `grounded_backend`, `document_processors`, `page_preprocessor`, `block_callbacks`.
- `evaluation.py` is a standalone benchmarking module: it loads GLM-OCR-format fixture JSONs, auto-detects bbox axis order (`xyxy` vs `yxyx`), normalizes coordinates to 0..1, performs greedy IoU-based block matching, and computes recall, average IoU, and text similarity via `difflib.SequenceMatcher`.

The `core/` package is decomposed into focused sub-packages:
- `core/workflows/` — `EngineBase`, `HybridEngine`, `GroundedEngine`, shared utils
- `core/ocr/` — LiteLLM OCR client, prompts, filters, resilience (retry + circuit breaker)
- `core/pdf/` — rasterizer, sandwich-PDF embedder, `PDFHandler` facade
- `core/grounded/` — bbox-native VLM backends and JSON parsers
- `core/processors/` — deterministic document processors (reading_order, quality, structure, section, layout, table)
- `core/glossary_library/` + `core/glossary_sources/` — multi-format glossary import (CSV, TBX, TMX, XLIFF, JSON, SQL, Git)

Standalone core modules: `block_tree.py` (rich document IR with headings/tables/figures), `translation_tree.py` (structure-preserving translation), `tree_export.py`, `docx_tree_writer.py`, `entity_memory.py`, `nllb_engine.py`, `trocr_engine.py`, `handwriting_preprocessor.py`.

Dependency direction is one-way: `server.py` imports API routers and security services; `pipeline.py` imports core engines/workflows; `evaluation.py` depends only on `local_deepl.core.document.BBox` and stdlib — it has no runtime dependency on the server or pipeline.