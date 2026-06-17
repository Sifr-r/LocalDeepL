# LocalDeepL — Internal State Inventory

> **Scout track** — `track-localdeepl-state`
> Source tree: `C:\Users\rahin\LocalDeepL`
> Read-only inventory of the current LocalDeepL architecture, extension points, and gaps.
> Every claim is sourced as `[path:line]` from the actual repo on 2026-06-14.

---

## 1. Executive Summary

LocalDeepL is a FastAPI-hosted Python 3.11+ service that turns scanned PDFs and images into searchable sandwich PDFs (image layer + invisible OCR text layer) using local vision LLMs. Two pipeline paths exist behind a single `OCRPipeline` facade: a **hybrid path** (`Surya detection → VLM OCR → Needleman-Wunsch DP alignment → per-crop refine → post-process → document processors → PDF embed`) and a **grounded path** (one bbox-native VLM call → post-process → document processors → PDF embed) [pipeline.py:33-69]. The user-facing CLI was deprecated; the public surface is the Web UI/API and `OCRPipeline` for in-process use [AGENTS.md:39, pipeline.py:1-12]. The current architecture is mature on the hybrid OCR path, has six local document processors exposed through `document_processors=...`, an `ExtractionTemplate` enum for structured extraction, three independent token-bound artifact stores (text/metadata/exports), a confidence-eval harness with five PDFs and one image fixture, and a web/async-translation split behind extras. Friction is concentrated in: (a) dead `ai.py` router not mounted, (b) grounded path still builds hybrid components upstream, (c) a 50-entry in-memory job history with no persistence, (d) `pages_structured` legacy dict still the inter-stage contract while `DocumentResult` is the public IR, and (e) `ZAIHostedOCR` documented as experimental.

## 2. Architecture Map

### `src/local_deepl/` — package root

| Module | Responsibility | Public contract |
| --- | --- | --- |
| `src/local_deepl/__init__.py` | Lazy package-level exports to keep OCR core out of `import local_deepl.server` | `__version__`, lazy `__getattr__` for 30+ names; `__all__` [__init__.py:1-91] |
| `src/local_deepl/pipeline.py` | `OCRPipeline` facade that picks `HybridEngine` or `GroundedEngine` from injected components | `OCRPipeline(aligner, ocr_processor, pdf_handler, output_writer, grounded_backend, document_processors, page_preprocessor).run(...)` [pipeline.py:33-133] |
| `src/local_deepl/server.py` | FastAPI app factory + `local-deepl-server` CLI | `create_app()` mounts 7 routers + static [server.py:63-94]; `main(argv)` for `--host/--port/--reload` [server.py:153-185] |
| `src/local_deepl/evaluation.py` | Package-root confidence eval for `scripts/confidence_*.py` | `GTBlock`, `BlockMatch`, `ConfidenceReport`, `load_ground_truth`, `compute_report`, `iou`, `_detect_bbox_axis_order` [evaluation.py:39-285] |

### `src/local_deepl/core/` — OCR core (no web deps)

| Module | Responsibility | Public contract |
| --- | --- | --- |
| `core/document.py` | Normalized IR for handoff between stages | `DocumentSpan`, `DocumentBlock`, `DocumentPage`, `DocumentResult.from_pages_data(...)` (legacy → IR), `DocumentResult.text()`, `DocumentResult.to_pages_data()` (IR → legacy) [document.py:17-98] |
| `core/processors.py` | Document-processor protocol, registry, six built-ins, factory | `DocumentProcessor` Protocol [processors.py:34-39], `DocumentProcessorRegistry` [processors.py:45-74], `ReadingOrderProcessor` [77-102], `QualityAnalysisProcessor` [105-161], `StructureAnalysisProcessor` [164-240], `SectionAnalysisProcessor` [243-333], `LayoutEnrichmentProcessor` [336-389], `TableExtractionProcessor` [392-509], `build_document_processors(names)` [512-522], `run_document_processors(...)` [552-560] |
| `core/preprocessing.py` | Local deterministic page preprocessor | `PagePreprocessingOptions` (frozen dataclass with 5 toggles) [preprocessing.py:17-24], `PagePreprocessingResult` [27-30], `PagePreprocessor` Protocol [33-38], `LocalPagePreprocessor` [42-92] |
| `core/aligner.py` | Surya detection-only aligner with DP text-to-box binding | `BBox = list[float]` (normalized `[x0,y0,x1,y1]` in 0..1) [aligner.py:21]; `HybridAligner.get_detected_boxes_batch(...)` [40-84], `HybridAligner.align_text(...)` [86-…] (full body is 440 lines; DP is run twice — row-major and column-major — picking lower cost) [120-…] |
| `core/ocr.py` | LLM-based OCR over OpenAI-compatible endpoint; prompt registry; runaway-repetition filter; pre-flight model-load check | `LLMCallError` [23-29], `ModelNotLoadedError` [32-42]; `OLMOCR_PAGE_PROMPT` [48-58], `CROP_PROMPT` [62-67], `DUAL_ENGINE_PAGE_PROMPT` [69-79], `DUAL_ENGINE_CROP_PROMPT` [81-91], `CORRECTION_PAGE_PROMPT` [93-102], `CORRECTION_CROP_PROMPT` [104-110]; `_HALLUCINATION_PATTERNS` [116-119], `_is_fallback_response` [122-135]; `OCRProcessor(api_base, api_key, model)` [138-171], `ensure_model_loaded()` [174-191], `perform_ocr(...)` [193-242], `perform_ocr_on_crop(...)` [244-291], `_chat(...)` [293-347]; `PAGE_TIMEOUT_S=240`, `PAGE_MAX_TOKENS=6144`, `CROP_TIMEOUT_S=60`, `CROP_MAX_TOKENS=256` [152-159]; `_strip_runaway_repetition(...)` [394-431] |
| `core/pdf.py` | PDF/image conversion + sandwich PDF embedding | `PDFHandler.convert_to_images(...)`, `PDFHandler.embed_structured_text(...)` (referenced in pipeline.py:47) |
| `core/grounded.py` | Grounded OCR backends + bbox JSON parsers | `GroundedBlock` [52-56], `GroundedResponse` [59-63], `GroundedOCRBackend` Protocol [66-85]; `_NON_CONTENT_LABELS` [94-101]; `parse_zai_response(...)` [151-198], `parse_glm_layout_details(...)` [223-271], `_detect_axis_order_zxyxy(...)` [201-220]; `ZAIHostedOCR` [281-373]; `PromptedGroundedOCR` [414-…]; `DEFAULT_GROUNDING_PROMPT` [379-411] |
| `core/postprocess.py` | Dictionary-based spellcheck post-processing | `DictionaryPostProcessor` [postprocess.py:107]; `_ISO_639_MAP` for "ar"/"en-US"/"de"/"es"/"fr" [49-…]; loaded via `core/preprocessing.py:42`-style ensure_loaded; wired through `EngineBase._run_spellcheck` [base.py:63-82] |
| `core/routing.py` | Quality-routing recommendation metadata (records decisions in `page.metadata["routing"]`) | `QualityRoutingOptions` (frozen dataclass) [routing.py:8-11], `QualityRoutingPolicy.apply(...)` [13-60] |
| `core/evaluation.py` | Lightweight processor-result scoring helper | `EvaluationMetrics` [evaluation.py:10-25], `evaluate_document(...)` [28-52] |
| `core/translation_config.py` | Core-owned async-translation settings + feature-availability error | Owns `AsyncTranslationUnavailable` (used by `translation.py:11`) |
| `core/translation.py` | Optional LangGraph translation workflow (chunking + evaluation) | Importable without async extras; lazy-builds workflow |
| `core/docx_writer.py` | Markdown → `.docx` converter | `convert_markdown_to_docx(markdown_text) -> io.BytesIO` |
| `core/workflows/base.py` | Shared engine scaffolding | `EngineBase._cross_page_merge(...)` [base.py:24-61], `EngineBase._run_spellcheck(...)` [63-82]; type aliases `ProgressCallback`, `WarningCallback`, `OutputWriter` [5-7]; `_notify(...)` helper [10-14] |
| `core/workflows/hybrid.py` | Hybrid orchestration | `HybridEngine(aligner, ocr_processor, pdf_handler, output_writer, document_processors, page_preprocessor).execute(...)` [hybrid.py:89-320]; `parse_page_range(page_str, total)` [25-45] |
| `core/workflows/grounded.py` | Grounded orchestration | `GroundedEngine(grounded_backend, output_writer, document_processors).execute(...)` [grounded.py:19-86] |
| `core/workflows/__init__.py` | Re-exports engines + callback aliases | `EngineBase`, `HybridEngine`, `GroundedEngine`, `ProgressCallback`, `WarningCallback`, `OutputWriter`, `_notify` [__init__.py:1-14] |

### `src/local_deepl/api/` — FastAPI layer

| Module | Responsibility | Routes / contract |
| --- | --- | --- |
| `api/routers/config.py` | Runtime config + model discovery | `GET/POST /api/config`, `GET /api/models` [grep results: lines 83, 95, 120] |
| `api/routers/ocr.py` | Multipart OCR upload + process | `POST /process` [ocr.py:172] (525 lines; also houses `_document_quality_header`, `_document_structure_header`, `_document_sections_header`, metadata-artifact issuance, job-history append, response header decoration) |
| `api/routers/websocket.py` | Token-bound WebSocket progress transport | `POST /api/progress/session`, `WS /ws/{channel_id}` [grep: 86, 103] |
| `api/routers/jobs.py` | In-memory job history | `GET/DELETE /api/jobs` [grep: 10, 16] |
| `api/routers/artifacts.py` | Token-bound artifact download | `GET /text/{artifact_id}` [32], `GET /metadata/{artifact_id}` [58], `POST /api/export/document` [92], `GET /export/{artifact_id}` [137], `POST /api/export/docx` [167] |
| `api/routers/translation.py` | Sync + async translation | `POST /api/translate` [18], `POST /api/translate/async` [65], `GET /api/translate/status/{job_id}` [100] |
| `api/routers/extraction.py` | Structured extraction | `POST /api/extract` [18] |
| `api/routers/ai.py` | **Dead router** — defines `/api/translate`, `/api/extract`, `/api/translate/async`, `/api/translate/status/{job_id}` [ai.py:39, 52, 65, 83] but is **NOT mounted** in `server.py:85-91`. Functions duplicated in `translation.py`/`extraction.py`; AI logic is now in `api/services/ai.py` |
| `api/routers/state.py` | Module-level singletons | `text_artifacts`, `metadata_artifacts`, `export_artifacts` (all `TextArtifactStore`), `job_history`, `progress_service` [state.py:1-9] |
| `api/routers/common.py` | Shared helpers | `_stable_server_error`, `_extract_bearer_token`, `_path_exists`, `_cleanup` |
| `api/schemas/requests.py` | Pydantic request models | Enums: `PipelineMode` [10-12], `DenseMode` [15-18], `SpellcheckMode` [21-27], `DocumentProcessorName` [30-36], `ExtractionTemplate` [39-43], `DocumentExportFormat` [46-51]. Models: `ConfigUpdate` [93-166], `ProcessSettings` [169-221], `TranslationRequest` [224-242], `ExtractionRequest` [245-264], `ExportDocxRequest` [267-279], `DocumentExportRequest` [282-291] |
| `api/services/security.py` | Upload validation, opaque artifact IDs, stable error strings | `SAFE_API_BASE_ERROR`, `UploadValidationError`, `save_validated_upload(...)`, `SERVER_ERROR_MESSAGE` |
| `api/services/artifacts.py` | `TextArtifactStore` and friends | `TextArtifactStore` [67-…], `TextArtifactHandle` [51-56], `PageText` [27]; token = 32+ chars hex-id + bearer token [20-25] |
| `api/services/jobs.py` | Capped FIFO job history | `JobHistory`, `JobRecord`, `JobStatus` |
| `api/services/progress.py` | `ProgressService` with stage weights | `ProgressService.stage_to_percent(stage, current, total)` [referenced ocr.py:136] |
| `api/services/document_metadata.py` | Compact JSON report from `DocumentResult` | `build_document_metadata_report(...)`, `write_document_metadata_atomic(...)` |
| `api/services/document_exports.py` | JSON / Markdown / text / Docling / MinerU exports | Per `ARCHITECTURE.md:62` |
| `api/services/workflow.py` | Deterministic web/API workflow summary | `build_workflow_summary(settings)` [referenced ocr.py:36, 473] |
| `api/services/ai.py` | Backing AI service for `/api/extract` and `/api/translate` | `extract_structured_data(...)`, `translate_text(...)`, `AIServiceError` |
| `api/celery_app.py` | Guarded Celery imports with import-safe fallback | `celery_app.AsyncResult(...)` [referenced translation.py:105] |
| `api/tasks.py` | Optional Celery translation task | `process_translation_task.delay(document_id, text)` [referenced translation.py:93] |

### `src/local_deepl/utils/` & `resources/`

| Module | Responsibility |
| --- | --- |
| `utils/image.py` | `crop_for_ocr_from_image(...)`, blank-region detection [referenced hybrid.py:22, 339, 404] |
| `utils/security.py` | `is_ssrf_target(api_base)` — fail-closed SSRF guard, `ALLOW_SSRF_LOCAL=true` default [referenced ocr.py:42, 271] |
| `utils/litellm_provider.py` | `resolve_custom_provider(model)` — LiteLLM provider selection [referenced ocr.py:18, grounded.py:42] |
| `utils/tqdm_patch.py` | `tqdm_patch.apply()` — Surya progress-bar suppression (called at top of `aligner.py:16`) |
| `resources/dictionaries/` | Packaged compiled spellcheck dictionaries (`ara.json.gz`, `eng.json.gz` per ARCHITECTURE.md:269-275) |

### Top-level / repo root

| Path | Purpose |
| --- | --- |
| `pyproject.toml` | Deps + extras; only entry point is `local-deepl-server` [pyproject.toml:65-66] |
| `examples/` | `dense.pdf`, `digital.pdf`, `handwritten.pdf`, `hybrid.pdf`, `image.png`, `image.avif`, `notes.pdf` (7 fixtures) |
| `tests/fixtures/` | 6 ground-truth JSON files: `ground_truth_digital.json`, `ground_truth_hybrid.json`, `ground_truth_handwritten.json`, `ground_truth_dense.json`, `ground_truth_notes.json`, `ground_truth_image.json` |
| `scripts/` | 15 developer utilities (see §8) |
| `install.bat` / `install.ps1` / `start_app.vbs` / `stop_app.bat` / `test_ui.py` | Windows one-click install, hidden-start, stop, Playwright smoke test |

## 3. Pipeline Paths (detailed)

### 3.1 Hybrid path — `HybridEngine.execute` [hybrid.py:110-320]

| Stage | Lines | What happens | Data shape |
| --- | --- | --- | --- |
| 0. Validate `dense_mode` | [132-135] | Must be `auto`/`always`/`never`; else `ValueError` | — |
| 1. Convert PDF → images | [139-150] | `pdf_handler.convert_to_images(input_path, dpi, max_image_dim)` via `asyncio.to_thread`; `parse_page_range(pages, total)` [hybrid.py:25-45] if pages filter present | `images_dict: dict[int, str]` (base64-encoded page images) |
| 2. **Preprocess** (opt-in) | [153-169] | Only if `page_preprocessor is not None` AND `preprocessing_options.enabled`; runs OpenCV/Pillow ops | `images_dict` overwritten; `preprocessing_metadata: dict[int, dict[str, object]]` |
| 3. **Detect layout** (Surya) | [172-196] | Chunked 10 pages/batch; `aligner.get_detected_boxes_batch(chunk_bytes)` via `asyncio.to_thread`; auto-retries on empty-batch (3x) [aligner.py:75-84]; bboxes normalized to 0..1 | `batch_boxes: list[list[BBox]]` |
| 4. Decide sparse vs dense per page | [198-204] | `dense_mode == "always"` OR `(dense_mode == "auto" and n_boxes > dense_threshold)` → per-box page | `per_box_pages: set[int]`, `pages_structured: dict[int, list[tuple[BBox, str]]]` initialized to empty strings |
| 5. **OCR (concurrent)** | [206-269] | `asyncio.Semaphore(concurrency)`; `asyncio.TaskGroup`. Sparse path: `ocr_processor.perform_ocr(page_image, ...)` then `aligner.align_text(structured, llm_lines)` [233-234]. Dense path: `_ocr_per_box(...)` [322-367] decodes the page image once, then runs `perform_ocr_on_crop(...)` per box | `pages_text: dict[int, list[str]]`, `pages_structured: dict[int, list[tuple[BBox, str]]]`, `last_failed_pages: list[int]` |
| 6. **Refine uncertain** (opt-in) | [271-285] | Only if `refine=True` and there are sparse pages. `_refine_uncertain(...)` [369-442] identifies empty text in refinable boxes (`_is_refinable(bbox)`: width>0.03 AND height>0.008) [83-86], re-OCR each, then `_drop_refined_duplicates(...)` [56-80] within a 4-box radius | updates `pages_structured[p_num][idx] = (bbox, text.strip())` |
| 7. **Cross-page merge** (opt-in) | [288-289] | Inherited from `EngineBase._cross_page_merge` [base.py:24-61]; merges trailing line of page `i` into leading line of page `i+1` if no terminal punctuation | mutates `pages_structured` |
| 8. **Spellcheck** (opt-in) | [291-292] | Inherited from `EngineBase._run_spellcheck` [base.py:63-82]; `DictionaryPostProcessor(lang).correct_text(text)` per box | mutates `pages_structured` |
| 9. Build `DocumentResult` | [294-296] | `DocumentResult.from_pages_data(pages_structured, source_path=input_path, source_processor="hybrid")` [document.py:62-89] | `document_result: DocumentResult` |
| 10. Attach preprocessing metadata | [297-300] | `page.metadata["preprocessing"] = preprocessing_metadata[page.page_index]` (only for preprocessed pages) | updates `document_result.pages[*].metadata` |
| 11. **Run document processors** | [301-303] | `await run_document_processors(document_result, self.document_processors)` [processors.py:552-560] — sequential, each gets the mutated result | `self.last_document_result` |
| 12. Apply quality-routing (opt-in) | [304-307] | `QualityRoutingPolicy().apply(...)` [routing.py:16-60] — only if `quality_routing_options.enabled`. Maps `empty_page`→`retry_empty_page`, `sparse_text`→`switch_dense_mode`, `empty_large_block`→`retry_block_or_grounded`; writes `page.metadata["routing"]` | `self.last_document_result` |
| 13. Convert back to pages_data | [308-312] | `self.last_document_result.to_pages_data()` [document.py:94-98]; rebuilds `pages_text` from non-empty blocks | `pages_structured`, `pages_text` |
| 14. **Write output** | [314-319] | `output_writer(input_path, output_path, pages_structured, dpi)` via `asyncio.to_thread` — default is `pdf_handler.embed_structured_text` [pipeline.py:47] | writes sandwich PDF to `output_path` |
| Return | [320] | `pages_text: dict[int, list[str]]` | — |

Progress stages: `convert`, `detect`, `ocr`, `refine`, `embed` (5 stages, all routed through `_notify(progress, stage, current, total, message)` [base.py:10-14]).

### 3.2 Grounded path — `GroundedEngine.execute` [grounded.py:34-86]

| Stage | Lines | What happens | Data shape |
| --- | --- | --- | --- |
| 1. **One bbox-native VLM call** | [49-54] | `await self.grounded_backend.ocr_document(input_path, progress, on_warning)`; default backend is `PromptedGroundedOCR` (Qwen-VL family) | `GroundedResponse(blocks, page_sizes, failed_pages)` [grounded.py:59-63] |
| 2. Bucket by page | [56-60] | `pages_data: dict[int, list[tuple[BBox, text]]] = defaultdict(list)`; sorts pages | `pages_data`, `page_nums` |
| 3. **Cross-page merge** (opt-in) | [62-63] | Same `EngineBase._cross_page_merge` | mutates `pages_data` |
| 4. **Spellcheck** (opt-in) | [65-66] | Same `EngineBase._run_spellcheck` | mutates `pages_data` |
| 5. Build `DocumentResult` | [68-70] | `DocumentResult.from_pages_data(dict(pages_data), source_path=input_path, source_processor="grounded")` | `document_result` |
| 6. **Run document processors** | [71-73] | `await run_document_processors(...)` | `self.last_document_result` |
| 7. Convert back | [74-75] | `self.last_document_result.to_pages_data()`; rebuilds `page_nums` | `pages_data` |
| 8. Build `pages_text` | [77-79] | `pages_text[p] = [text for _, text in pages_data[p] if text.strip()]` | `pages_text: dict[int, list[str]]` |
| 9. **Write output** | [81-85] | `output_writer(input_path, output_path, dict(pages_data), dpi)` | writes PDF |
| Return | [86] | `dict(pages_text)` | — |

Progress stages: only `embed` and whatever the backend emits (the prompt says backends "SHOULD emit the `ocr` stage" [grounded.py:71-72]). The hybrid engine emits 5 stages; the grounded engine emits fewer.

## 4. Extension Points

`OCRPipeline.__init__` [pipeline.py:33-69] accepts seven component slots. Each is optional in isolation but together they are validated at construction.

| Slot | Default if not provided | Current wired in `api/routers/ocr.py` | Notes |
| --- | --- | --- | --- |
| `aligner=` | **Required** for hybrid path (raises `ValueError` if missing) [pipeline.py:57-61] | `HybridAligner()` [ocr.py:340] | Loads Surya `DetectionPredictor` ~hundreds of MB on first call. One class: `HybridAligner` [aligner.py:24]. |
| `ocr_processor=` | **Required** for hybrid path | `OCRProcessor(api_base, api_key, model)` [ocr.py:334-338] | One class: `OCRProcessor` [ocr.py:138-497]. Uses LiteLLM `acompletion` over OpenAI-compat. |
| `pdf_handler=` | **Required** always (raises `ValueError` if `None`) [pipeline.py:45-46] | `PDFHandler()` [ocr.py:327, 342] | Provides `convert_to_images(...)` + `embed_structured_text(...)` (the default `output_writer`) [pipeline.py:47] |
| `output_writer=` | Defaults to `pdf_handler.embed_structured_text` [pipeline.py:47] | Not set — uses default | `OutputWriter = Callable[[str, str, dict, int], None]` [base.py:7] |
| `grounded_backend=` | `None` → hybrid path; non-`None` → grounded path [pipeline.py:50-55] | `PromptedGroundedOCR(...)` only when `settings.pipeline_mode == "grounded"` [ocr.py:319-325] | Two backends implemented: `PromptedGroundedOCR` [grounded.py:414-…], `ZAIHostedOCR` [grounded.py:281-373] (experimental). Contract: `GroundedOCRBackend` Protocol with `async ocr_document(pdf_path, progress, on_warning) -> GroundedResponse` [grounded.py:66-85] |
| `document_processors=` | Empty tuple [pipeline.py implicit via `tuple(document_processors or ())` in engines] | `build_document_processors(p.value for p in settings.document_processors)` [ocr.py:294-296] | `Sequence[DocumentProcessor]`; `DocumentProcessor` Protocol [processors.py:34-39]; run in order via `run_document_processors(...)` [processors.py:552-560] |
| `page_preprocessor=` | `None` | `LocalPagePreprocessor()` if `preprocessing_options.enabled` else `None` [ocr.py:305-307] | `PagePreprocessor` Protocol [preprocessing.py:33-38]; one impl: `LocalPagePreprocessor` [preprocessing.py:42-92] |

The grounded path **does not** consume `aligner`, `ocr_processor`, or `page_preprocessor` (the `GroundedEngine.__init__` does not take them [grounded.py:20-25]), but the web router still **builds** them in some branches — see §9.

## 5. Document Processors

All six are registered in `build_document_processors(...)` [processors.py:512-522] and run sequentially after OCR/spellcheck and before PDF embedding [hybrid.py:301-303, grounded.py:71-73]. Selectable through `document_processors=[DocumentProcessorName.X, ...]` in either `ConfigUpdate` or `ProcessSettings` [requests.py:119, 195]. Defaults are off [AGENTS.md:40].

| Name (`DocumentProcessorName`) | Class | File:line | What it produces | Schemas emitted |
| --- | --- | --- | --- | --- |
| `reading_order` | `ReadingOrderProcessor` | [processors.py:77-102] | Sorts blocks in row-major order using bbox y/x with `row_tolerance=0.02`; assigns `block.reading_order = index` | Mutates `block.reading_order`; no page metadata. (NOTE: only one of the 6 that does not write `page.metadata`.) |
| `quality_analysis` | `QualityAnalysisProcessor` | [processors.py:105-161] | Per-page `page.metadata["quality"]` with `block_count`, `text_char_count`, `text_density`, `findings[]` (advisory: `empty_page`, `sparse_text`, `empty_large_block`) | Exposed as `X-Document-Quality` header in the API [ocr.py:482-484]; consumed by `QualityRoutingPolicy` [routing.py:22-58] |
| `structure_analysis` | `StructureAnalysisProcessor` | [processors.py:164-240] | Per-block `block.metadata["structure"]` (`{kind, confidence, signals}`); per-page `page.metadata["structure"]` (`block_kinds`, `has_key_values`, `has_tables`) | Block kinds: `empty`/`list_item`/`key_value`/`table_candidate`/`heading`/`paragraph`. Exposed as `X-Document-Structure` [ocr.py:485-487] |
| `section_analysis` | `SectionAnalysisProcessor` | [processors.py:243-333] | Per-block `block.metadata["section"]` (`{section_index, title, heading_page_index, heading_block_index, role}`); per-page `page.metadata["sections"]` (`headings`, `section_count`, `active_section`) | Roles: `heading`/`body`/`unsectioned`. Exposed as `X-Document-Sections` [ocr.py:488-490]. Depends on structure metadata if it exists, but has its own `_is_heading` heuristic fallback [305-333] |
| `layout_enrichment` | `LayoutEnrichmentProcessor` | [processors.py:336-389] | Per-block `block.metadata["layout"]` (`{role, region, confidence, signals}`); per-page `page.metadata["layout"]` (`roles`, `has_figures`, `has_captions`, `has_headers`, `has_footers`) | Roles: `header`/`footer`/`page_number`/`caption`/`title_block`/`figure`/`body`; regions: `header` (y1≤0.16)/`footer` (y0≥0.84)/`body`/side variants. NO API header — metadata only. |
| `table_extraction` | `TableExtractionProcessor` | [processors.py:392-509] | Per-block `block.metadata["table"]` (`{table_index, row_index, column_index}`); per-page `page.metadata["tables"]` (list of `{table_index, row_count, column_count, cells[]}`) | Cell dict: `{row_index, column_index, block_index, text, bbox}`. NO API header — metadata only. |

The `TableExtractionProcessor` deliberately does **not** depend on `StructureAnalysisProcessor`'s `table_candidate` label anymore (the dependency was a footgun, see the rationale in `_is_candidate` [processors.py:430-440]); it uses a column-separator heuristic + cell-shape heuristic [415-456].

## 6. Public API Surface

All routes are mounted in `server.py:85-91` with **no** prefix; the route paths below are the final paths.

### 6.1 Multipart OCR

| Method | Path | Router | Source | Accepts |
| --- | --- | --- | --- | --- |
| `POST` | `/process` | `ocr` | [ocr.py:172-525] | `file: UploadFile`, plus all 22 settings as form fields: `client_id`, `progress_channel`, `progress_token`, `api_base`, `api_key`, `model`, `pipeline_mode`, `dpi`, `concurrency`, `dense_mode`, `dense_threshold`, `pages`, `refine`, `max_image_dim`, `self_correction`, `binarize`, `dual_engine`, `spellcheck`, `cross_page`, `preprocess_pages`, `orientation_detection`, `deskew`, `denoise`, `normalize_contrast`, `crop_cleanup`, `quality_routing`, `document_processors` |

`ProcessSettings` fields [requests.py:169-221] map 1:1 to the form fields above. Each has validators that reject bool→int and string→int traps [59-62, 65-67, 70-73], reject empty strings, and normalize `pages` to a regex-validated range (`^\s*\d+\s*(?:-\s*\d+\s*)?(?:,\s*\d+\s*(?:-\s*\d+\s*)?)*\s*$`) [54-56, 209-216]. `document_processors` accepts a comma-separated string and is normalized to a list of `DocumentProcessorName` [83-90, 218-221].

Response: `application/pdf` `FileResponse` [ocr.py:462-467] with these custom headers (all set unconditionally unless noted):

| Header | Source | When present |
| --- | --- | --- |
| `X-Text-Artifact-Id` | `state.text_artifacts.create(...)` [ocr.py:431-433, 468] | Always |
| `X-Text-Artifact-Token` | same [471] | Always |
| `X-Failed-Pages` | `pipeline.last_failed_pages` [469-470] | Only if non-empty |
| `X-Document-Workflow` | `build_workflow_summary(settings)` JSON [472-474] | Always |
| `X-Document-Metadata-Artifact-Id` / `-Token` | `_create_document_metadata_artifact(pipeline)` [435, 475-481] | Only if metadata report non-empty |
| `X-Document-Quality` | `_document_quality_header(pipeline)` [482-484] | Only if `quality_analysis` ran and produced findings |
| `X-Document-Structure` | `_document_structure_header(pipeline)` [485-487] | Only if `structure_analysis` ran |
| `X-Document-Sections` | `_document_sections_header(pipeline)` [488-490] | Only if `section_analysis` ran |

### 6.2 Runtime config

| Method | Path | Router | Source |
| --- | --- | --- | --- |
| `GET` | `/api/config` | `config` | [grep: config.py:83] |
| `POST` | `/api/config` | `config` | [grep: config.py:95]; accepts `ConfigUpdate` [requests.py:93-166] with optional: `api_base`, `api_key`, `model`, `concurrency` (1-64), `dpi` (10-600), `dense_mode`, `dense_threshold` (0-10000), `max_image_dim` (100-4096), `refine`, `verify_model`, `pipeline_mode`, `self_correction`, `binarize`, `dual_engine`, `spellcheck`, `cross_page`, `preprocess_pages`, `orientation_detection`, `deskew`, `denoise`, `normalize_contrast`, `crop_cleanup`, `quality_routing`, `document_processors` (list) |
| `GET` | `/api/models` | `config` | [grep: config.py:120]; model discovery |

### 6.3 Jobs (in-memory, capped at 50, FIFO)

| Method | Path | Router | Source |
| --- | --- | --- | --- |
| `GET` | `/api/jobs` | `jobs` | [grep: jobs.py:10] |
| `DELETE` | `/api/jobs` | `jobs` | [grep: jobs.py:16]; clears history and text artifacts |

### 6.4 Translation (sync + async)

| Method | Path | Router | Source | Body |
| --- | --- | --- | --- | --- |
| `POST` | `/api/translate` | `translation` | [translation.py:18-62] | `TranslationRequest` [requests.py:224-242]: `text`, `target_language` (default "Spanish", 1-80), `api_base?`, `api_key?`, `model?` |
| `POST` | `/api/translate/async` | `translation` | [translation.py:65-97] | Raw dict: `document_id?`, `text`. Returns 503 if `async-translation` extra not installed |
| `GET` | `/api/translate/status/{job_id}` | `translation` | [translation.py:100-127] | Returns Celery task state/info/result |

### 6.5 Extraction

| Method | Path | Router | Source | Body |
| --- | --- | --- | --- | --- |
| `POST` | `/api/extract` | `extraction` | [extraction.py:18-111] | `ExtractionRequest` [requests.py:245-264]: `text`, `template` (`invoice`/`resume`/`academic`/`custom`), `custom_prompt` (≤4000), `api_base?`, `api_key?`, `model?` |

### 6.6 Document exports

| Method | Path | Router | Source | Body |
| --- | --- | --- | --- | --- |
| `POST` | `/api/export/document` | `artifacts` | [grep: artifacts.py:92] | `DocumentExportRequest` [requests.py:282-291]: `text_artifact_id` (32 chars), `text_artifact_token` (32-256), `export_format` (`json`/`markdown`/`text`/`docling`/`mineru`), optional `metadata_artifact_id?`/`metadata_artifact_token?` |
| `GET` | `/export/{artifact_id}` | `artifacts` | [grep: artifacts.py:137] | Token in `Authorization: Bearer …` |
| `POST` | `/api/export/docx` | `artifacts` | [grep: artifacts.py:167] | `ExportDocxRequest` [requests.py:267-279]: `text` |
| `GET` | `/text/{artifact_id}` | `artifacts` | [grep: artifacts.py:32] | Token in `Authorization: Bearer …` |
| `GET` | `/metadata/{artifact_id}` | `artifacts` | [grep: artifacts.py:58] | Token in `Authorization: Bearer …` |

### 6.7 Progress / WebSocket

| Method | Path | Router | Source |
| --- | --- | --- | --- |
| `POST` | `/api/progress/session` | `websocket` | [grep: websocket.py:86] |
| `WS` | `/ws/{channel_id}?token=…` | `websocket` | [grep: websocket.py:103] |

### 6.8 Static + index

| Method | Path | Source |
| --- | --- | --- |
| `GET` | `/` | [server.py:92, 124-127] (single-page frontend `index.html`) |
| `GET` | `/static/*` | [server.py:79-83] (mounted `StaticFiles`) |

## 7. Known Tech Debt

### From `AGENTS.md` [AGENTS.md:125-129]
1. `api/routers/ocr.py` mixes OCR, translation, extraction, and asynchronous task routes.
2. The grounded web route instantiates hybrid components even though `OCRPipeline` skips them in grounded mode.
3. `ZAIHostedOCR` remains an experimental backend.

### New findings from this inventory

4. **Dead `ai.py` router** [api/routers/ai.py:1-108]. Defines `POST /api/translate`, `POST /api/extract`, `POST /api/translate/async`, `GET /api/translate/status/{job_id}` but is **not mounted** in `server.py:85-91`. The functional duplicates live in `translation.py` and `extraction.py`. `ai.py` also imports `from local_deepl.api.services.ai import translate_text as translate_document_text` [ai.py:15-17] but the imported function is never called inside `ai.py` — only `extract_structured_data` is [ai.py:54, 57]. ARCHITECTURE.md:54 still claims `ai.py` is "consumed by extraction.py and translation.py", which is misleading because (a) `ai.py` is not consumed by them, and (b) `ai.py` is itself a router module that isn't mounted.

5. **`ocr.py` constructs dead hybrid components for the grounded path**. When `settings.pipeline_mode == "grounded"`, `ocr.py:312-331` correctly instantiates `PromptedGroundedOCR` and passes only `pdf_handler`, `grounded_backend`, `document_processors`, `page_preprocessor` to `OCRPipeline` (no `aligner` or `ocr_processor`). The inline comment [ocr.py:313-318] acknowledges the wart: "the grounded branch now mirrors the hybrid branch's structure 1:1" (this is overstated — the actual variable construction differs). The pre-flight `verify_model` check [ocr.py:347-371] correctly uses `backend.ensure_model_loaded()` for whichever branch was chosen, so the SSRF-safe `api_base` is used. The wart is that `page_preprocessor` is still built and passed for the grounded path, but `GroundedEngine.__init__` ignores it [grounded.py:20-25].

6. **Two parallel `OCR`-and-process pipelines inside `ocr.py:312-345`**. The if/else that picks `backend` is structurally duplicated; both branches repeat `document_processors=processors, page_preprocessor=page_preprocessor` in the `OCRPipeline(...)` call. Refactor opportunity: a `Backend` protocol + factory pattern would collapse this.

7. **`ocr.py` is 525 lines and owns too many concerns** — Form parsing, ProcessSettings construction, backend selection, pipeline construction, model-load pre-flight, progress/warning callbacks, artifact issuance, job-history append, and response-header decoration all live in one function. This is the AGENTS.md wart #1 in concrete form.

8. **`pages_structured: dict[int, list[tuple[BBox, str]]]` is the de-facto inter-stage contract** [hybrid.py:193-195, 256-257, 311-312; grounded.py:56-60, 74-79; processors.py throughout uses `DocumentResult` then converts back to `pages_structured`]. The `DocumentResult` IR exists but is only a handoff wrapper for processors — every stage that takes a typed shape immediately converts it to/from the legacy dict. This is the cost of "shrunken facade" refactor [ARCHITECTURE.md:147].

9. **`OCRProcessor` is the only class in `core/ocr.py`** (along with two exception classes). The module is 497 lines. Binarize + dual-engine + self-correction are three separate flags with non-overlapping prompt logic; the file could be split into `core/ocr/{processor, prompts, filters}.py`.

10. **`ZAIHostedOCR` is wired into the public API via `__init__.py` export** [__init__.py:43] but its `SUBMIT_PATH` and `TASK_PATH` are unverified placeholders [grounded.py:304-310]. Anyone who reads the public exports and instantiates it gets a skeleton that will 404 on real Z.AI.

11. **No rate limiting, no auth on `/api/*`** (the bearer token is only on artifact GETs and the WebSocket). A single client can flood `/process` and consume the entire GPU/LLM budget. `verify_model` pre-flight hits the LLM server on every OCR call [ocr.py:370-371], adding one HTTP round-trip per request.

12. **`api/routers/state.py` module-level singletons** [state.py:1-9] are mutable process-global state. The job history is capped at 50 in-process [ARCHITECTURE.md:114-117] but the cap and the eviction policy live in `JobHistory`; nothing about the cap is configurable through the API. Job history is **lost on process restart** — there is no persistence.

13. **Three separate `TextArtifactStore` instances** [state.py:5-7] for text, metadata, exports. They share the same token format and TTL semantics [artifacts.py:14-25] but each has independent retention budgets, so a metadata artifact and a text artifact with the same id could live in different states. No cross-store integrity.

14. **`pages_structured` bbox in the legacy dict is just `list[float]`** [hybrid.py:194]. There is no validation in the legacy path that the bbox is normalized 0..1; only `DocumentResult.from_pages_data` validates [document.py:101-107]. A misbehaving custom `aligner` could write pixel-space bboxes and they would silently make it to `embed_structured_text`.

15. **`prompt` argument to `PromptedGroundedOCR` is `str | None = None`** [grounded.py:442] and only one default exists (`DEFAULT_GROUNDING_PROMPT` [grounded.py:379-411]). There is no multi-prompt registry; switching grounding behavior per-document-type requires editing the prompt string.

16. **`_run_spellcheck` is awaited but not run in a thread** [base.py:63-82]. `DictionaryPostProcessor.correct_text(...)` is presumably blocking; on a 100-page document this is a serial CPU loop on the event loop. The dictionary load itself goes through `ensure_loaded` which is async but the actual `correct_text` calls are sync on a per-page, per-box basis.

17. **`_parse_grounded_json`** [grounded.py:594-…] lives in the same 676-line module as `PromptedGroundedOCR`. Likely handles the JSON-parsing-from-LLM-output concern, including fence stripping. Module is doing too much.

18. **No retry / circuit breaker for the LLM endpoint inside `OCRProcessor._chat`** [ocr.py:293-347]. A single transient timeout fails the whole page. The pipeline catches per-page exceptions [hybrid.py:238-242] but the user gets a 50% recall on a flaky run with no diagnostic.

19. **`_page_region` thresholds** in `LayoutEnrichmentProcessor` [processors.py:538-544] are hardcoded (`y1 <= 0.16` → header, `y0 >= 0.84` → footer). Letter/A4 pages; not configurable. Edge cases (3-column legal, foldout) will misclassify.

20. **`tests/`** is referenced in AGENTS.md/ARCHITECTURE.md but not surveyed here. The presence of `tests/test_evaluation.py`, `tests/test_aligner.py`, `tests/test_api_safety.py`, `tests/test_security_qa.py`, `tests/test_extraction.py`, `tests/test_translation_boundary.py`, `tests/test_dictionary_postprocess.py`, `tests/test_server_lazy_imports.py`, `tests/test_document.py`, `tests/test_document_processor_selection.py`, `tests/test_grounded.py` is implied by the changelog entries; whether all exist and pass was not verified.

## 8. Quality Measurement

### 8.1 Confidence-eval harness — `scripts/confidence_eval.py` (192 lines)

- **Job list** [confidence_eval.py:47-61]: 5 PDF jobs + 1 image job
  - `digital.pdf` ↔ `tests/fixtures/ground_truth_digital.json`
  - `hybrid.pdf` ↔ `tests/fixtures/ground_truth_hybrid.json`
  - `handwritten.pdf` ↔ `tests/fixtures/ground_truth_handwritten.json`
  - `dense.pdf` ↔ `tests/fixtures/ground_truth_dense.json` (regression-only — fixture built from hybrid output via `scripts/fixture_from_output.py` because too dense to hand-build)
  - `notes.pdf` ↔ `tests/fixtures/ground_truth_notes.json` (regression-only)
  - Image: `examples/image.avif` ↔ `tests/fixtures/ground_truth_image.json` (handled by `confidence_image.py`)
- **What it measures** for each (PDF, path) pair: `block_recall` (fraction of GT blocks matched at IoU ≥ threshold), `avg_iou` (mean IoU of matched pairs), `avg_text_similarity` (mean `difflib.SequenceMatcher` ratio on text-normalized matched pairs), and the per-document list of unmatched GT blocks with `best_iou` [confidence_eval.py:108-142].
- **Two paths measured**: `grounded` (Qwen3-VL, `PromptedGroundedOCR.ocr_document` direct — no PDF write) [67-76]; `hybrid` (`OCRPipeline` with a custom `output_writer` that smuggled `pages_data` into a dict via closure) [79-102].
- **Default args** [148-156]: `--api-base http://localhost:1234/v1`, `--grounded-model qwen/qwen3-vl-8b`, `--hybrid-model allenai/olmocr-2-7b`, `--max-image-dim 1024`, `--iou-threshold 0.3`.
- **Greedy matching, not Hungarian** [evaluation.py:20-22]: `compute_report` is deterministic and "close enough for a confidence summary"; the project consciously chose greedy IoU over optimal assignment.
- **Axis-order auto-detect** [evaluation.py:8-13]: fixtures can use `[x0,y0,x1,y1]` (handwritten.pdf) or `[y0,x0,y1,x1]` (hybrid.pdf, digital.pdf). Detection by aspect-ratio heuristic in `_detect_bbox_axis_order` — same heuristic used by `parse_zai_response` [grounded.py:201-220].
- **Output**: Rich table with per-document path × metrics, plus up-to-6 unmatched GT snippets per doc [confidence_eval.py:108-142].

### 8.2 Single-image confidence — `scripts/confidence_image.py` (171 lines)

- Defaults to `examples/image.avif` [confidence_image.py:84] and `tests/fixtures/ground_truth_image.json` [87].
- Runs hybrid (default `allenai/olmocr-2-7b`) and grounded (default `qwen/qwen3-vl-4b`) head-to-head on the same image, prints a comparison table, and up-to-10 unmatched GT snippets per path [136-167].
- `--hybrid-model`/`--grounded-model` override defaults [93-94].

### 8.3 In-process evaluation helper — `core/evaluation.py`

Lightweight `evaluate_document(document, expected_text="")` [core/evaluation.py:28-52] returning an `EvaluationMetrics` dataclass [10-25] with `text_similarity`, `block_count`, `invalid_bbox_count`, `reading_order_coverage`, `table_count`. Used by document-processor consumers (e.g. for processor-result scoring), NOT by the confidence-eval harness. Two evaluation paths in the codebase: package-root `evaluation.py` (for `scripts/confidence_*.py`, ground-truth comparison) and `core/evaluation.py` (lightweight, in-process).

### 8.4 Test fixtures inventory

| File | Size (B) | Path |
| --- | --- | --- |
| `ground_truth_digital.json` | 4763 | `tests/fixtures/` |
| `ground_truth_hybrid.json` | 7681 | `tests/fixtures/` |
| `ground_truth_handwritten.json` | 2733 | `tests/fixtures/` |
| `ground_truth_image.json` | 3469 | `tests/fixtures/` |
| `ground_truth_dense.json` | 102951 | `tests/fixtures/` |
| `ground_truth_notes.json` | 133515 | `tests/fixtures/` |

Examples: `dense.pdf` (4.6 MB), `digital.pdf` (126 KB), `handwritten.pdf` (146 KB), `hybrid.pdf` (103 KB), `image.avif` (271 KB), `image.png` (1.0 MB), `notes.pdf` (10.8 MB).

### 8.5 Other developer scripts (`scripts/`, 15 total)

- `build_fixture.py` (3.8 KB), `fixture_from_output.py` (3.7 KB) — fixture builders
- `debug_alignment.py` (3.3 KB), `debug_detection_only.py` (4.2 KB), `debug_image_input.py` (3.1 KB), `debug_llm_raw.py` (1.3 KB) — debug utilities
- `ingest_lexicon.py` (4.9 KB) — dictionary ingestion for spellcheck
- `inspect_grounded_lines.py` (1.3 KB), `inspect_pdf.py` (923 B) — inspection
- `test_check.py` (2.0 KB), `verify_output.py` (2.5 KB) — output verification
- `visualize_bboxes.py` (2.0 KB), `visualize_comparison.py` (4.0 KB) — bbox visualization

## 9. Gaps and Friction

### Production-load concerns

- **No horizontal scaling story.** All state is process-local [state.py:1-9]. Three artifact stores + job history + progress service are module-level. Two workers behind a load balancer will not share job state, progress channels, or artifact IDs. A user with `artifact_id=X` on worker A may get a 404 if their next request lands on worker B.
- **Synchronous `/process` blocks the worker for the entire OCR duration.** A 100-page dense document takes minutes; one request occupies one uvicorn worker the whole time. There is no internal queueing. The async translation path exists [translation.py:65-97] but the OCR path itself is sync.
- **`/api/translate/async` uses Celery, but `/process` does not.** Asymmetric concurrency model. If async OCR is ever added, it would need a Celery task facade mirroring `api/tasks.py`.
- **No streaming/chunked response for `/process`.** The whole sandwich PDF is buffered in `tempfile.gettempdir()` and then `FileResponse`'d. A 500-page document is a large file sitting in temp until the response is sent.
- **Surya detection is loaded on first `HybridAligner()` instantiation** [aligner.py:38]. Every fresh process pays the model load cost on the first `/process` call; `tqdm_patch.apply()` [aligner.py:16] silences the load progress bar so users may think the request hung.
- **No structured logging.** All warnings go to `logging.warning` with no correlation ID [hybrid.py:241, 354, 419; ocr.py:504, 520; ai.py:46, 60]. Multi-page failures produce a stream of indistinguishable lines.
- **No metrics.** No Prometheus/OpenTelemetry. No counter for `pages_processed`, `pages_failed`, `pipeline_latency_seconds`, `llm_call_latency_seconds`. The `_notify(progress, ...)` hook is the only observability channel.

### Friction specific to current extension points

- **`OCRPipeline` does not validate that `aligner` and `ocr_processor` are compatible** [pipeline.py:57-61] — just that both are non-None. A `HybridAligner` paired with a custom `ocr_processor` that returns lines already with bboxes would silently double-process.
- **No seam to inject a custom `OutputWriter` from the web API.** The web router uses the default `pdf_handler.embed_structured_text` [pipeline.py:47] for both paths. Custom output would require a code change.
- **`document_processors` is the only public surface for processors** [requests.py:119, 195]. There is no way for the web API to pass processor options (e.g. `row_tolerance=0.03` for `ReadingOrderProcessor`); the constructor args from `processors.py:88, 117, 170, 249, 397` are all hardcoded by the factory [processors.py:512-522].
- **`PipelineMode` enum is exposed in `ConfigUpdate`** [requests.py:106] but the `/process` endpoint takes it as a form string [ocr.py:181] and validates via the `ProcessSettings.pipeline_mode` field [requests.py:175]. There is no helpful error if the form value is "GHybrid" or `null` — it fails Pydantic validation.
- **`pages_structured` ↔ `DocumentResult` conversion is lossy.** `DocumentResult.from_pages_data` discards `source_processor` for blocks [document.py:80-86] unless explicitly passed (which the engines do: `"hybrid"` [hybrid.py:295] / `"grounded"` [grounded.py:69]). `to_pages_data` [document.py:94-98] loses `kind`, `confidence`, `spans`, and `metadata` from the IR on the way back to the legacy dict. So a custom processor that mutates `block.metadata["custom"]` will have its annotations invisible to the legacy output writer and any future legacy consumers.
- **The `block.reading_order` field is set by `ReadingOrderProcessor` but `ReadingOrderProcessor` runs in the same processor chain that the user can re-order**. If a user puts `structure_analysis` before `reading_order`, structure analysis sees un-sorted blocks; that may be fine, but the metadata side effects are not isolated.

### Quick wins visible from this inventory

- Mount the dead `ai.py` router (or delete it). Currently it adds confusion without runtime effect.
- The `page_preprocessor=page_preprocessor` argument passed to `OCRPipeline` for the grounded path [ocr.py:330] is silently ignored by `GroundedEngine` [grounded.py:20-25] — drop it.
- Inline comments at `ocr.py:313-318` misrepresent the actual branch structure (the branches differ in 2 of 4 args). Update the comment.
- `ocr.py:312-345`'s 33-line if/else for backend selection could collapse to a 4-line factory.
- `ARCHITECTURE.md:54` should be updated to note `ai.py` is a dormant router; the "consumed by extraction.py and translation.py" line is wrong on two counts.
- `_run_spellcheck` should be threaded (`asyncio.to_thread(processor.correct_text, text)`) to avoid serial CPU on the event loop for big docs.
- Add a `--max-image-dim` validation against the per-backend context window (the `LLMCallError` on context-size-exceeded [ocr.py:331-345] happens after a wasted VLM call).

### Tech debt specific to confidence-eval methodology

- Fixture for `dense.pdf` and `notes.pdf` were bootstrapped from the hybrid pipeline's own output [confidence_eval.py:53-58] — measuring "regression against the baseline", not "absolute quality". A regression that *improves* recall against the ground truth by aligning to a different OCR pattern would be flagged as a regression. The `digital.pdf` / `hybrid.pdf` / `handwritten.pdf` fixtures are hand-built and the absolute metrics on those are meaningful.
- Greedy IoU matching is biased toward early high-IoU pairs and may mis-attribute a low-IoU-but-correct-text match when a higher-IoU-but-wrong-text match is in the candidate pool. Hungarian matching would be a small upgrade.
- No measurement of binarize/dual_engine/self_correction/deskew/denoise/normalize_contrast impact. Each toggle exists in `ProcessSettings` but none have an A/B test scaffold.
- No measurement of `document_processors` impact on text quality. Processors are metadata-only (they don't rewrite text — see `processors.py:131-161, 341-361` for examples) so the text-similarity should be invariant, but the contract is not documented in `confidential_eval.py`.

### Open questions worth flagging to the synthesis task

1. Should the `ai.py` router be revived (it has a `translate_document_text` wrapper that's not used) or deleted (it duplicates `translation.py`)?
2. Is the `PipelineMode` enum string-comparison (`settings.pipeline_mode == "grounded"` at `ocr.py:312`) intended to be the contract, or should the engine itself advertise its mode?
3. Does the `core/workflows/__init__.py` re-export of `_notify` [__init__.py:2] count as a public API? It's an underscore-prefixed helper.
4. Is the `quality_routing` field placeholder (records decisions, but no consumer acts on them) deliberate or aspirational? `core/routing.py:30-53` writes recommendations to `page.metadata["routing"]` but no API surface exposes them.
5. The `layout_enrichment` and `table_extraction` processors write metadata that **never appears in any response header** (compare to `X-Document-Quality`, `X-Document-Structure`, `X-Document-Sections`). They are only reachable via the metadata-artifact route. Is this an oversight or intentional?
