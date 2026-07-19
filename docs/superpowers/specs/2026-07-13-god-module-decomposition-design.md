# God-Module Decomposition Design — LocalDeepL

> **Audience**: solo maintainer of LocalDeepL (FastAPI/OCR service, Windows / uv / pytest-uv workflow, hybrid OCR + grounded pipeline).
> **Date**: 2026-07-13.
> **Status**: Design approved in direction (questions 1-3 closed). Awaiting user review of this document.
> **Scope**: Decompose three "god modules" (`api/routers/ocr.py`, `core/ocr.py`, `core/grounded.py`) into single-responsibility sub-packages and services. Delete the dead `api/routers/ai.py` router. Update `ARCHITECTURE.md` accordingly. **No new features; no behavior changes; no test edits; the public import surface is preserved verbatim.**

## 1. Background and Constraints

LocalDeepL is a mature, narrowly-scoped local-first OCR service. The scout plan (`.mavis/plans/scout/`) and `AGENTS.md` (line 130-134, "Known Tech Debt") already call out specific tech debt:

- `api/routers/ocr.py` mixes OCR, translation, extraction, and asynchronous task routes (AGENTS.md wart #1).
- The grounded web route instantiates hybrid components even though `OCRPipeline` skips them in grounded mode.
- `ZAIHostedOCR` remains an experimental backend (placeholder URLs).
- Plus 20 more findings the scout added.

A 2026-06 commit series (`ca386e9 refactor: decompose god engines; lift shared state into EngineBase (PR-C)`) already extracted the engines into `core/workflows/`. This spec continues that pattern at the next level: the three remaining god modules.

### Hard constraints (user-confirmed)

1. **God-module decomposition is the primary objective** of this refactor. Specific modules in scope: `api/routers/ocr.py` (662 LOC), `core/ocr.py` (595 LOC), `core/grounded.py` (710 LOC), plus the dead `api/routers/ai.py`.
2. **Public import surface must be preserved exactly**. Any `from X import Y` that works today works after the refactor. The package's lazy `__getattr__` exports in `__init__.py` and the test suite's imports are the contract.
3. **Behavior is preserved**. No new features, no API endpoint changes, no runtime logic changes. The 81+ existing tests pass unchanged at every phase boundary.
4. **Documentation policy**: each new module opens with a 1-3 line module-level docstring. The route docstring on `/process` is rewritten to reference the new helpers. `ARCHITECTURE.md` Key Files table updated to list the new sub-packages. **No new top-level docs file** (per AGENTS.md: "NEVER proactively create documentation files unless explicitly requested").

### Non-goals (explicit)

- No IR contract redesign (the lossy `pages_structured` ↔ `DocumentResult` round-trip is a separate piece of work — scout finding #8).
- No async `/process` (separate production-readiness work).
- No new document processors, no new LLM backends, no IR/schema improvements.
- No renaming of public symbols; no removal of underscored helpers from public modules.

## 2. Architecture

### 2.1 Module layout

Three new sub-packages, one thin-router reduction, one deletion, one doc update. Each new file is single-responsibility.

```
src/local_deepl/
├── core/
│   ├── ocr/                          # NEW package (was core/ocr.py, 595 LOC)
│   │   ├── __init__.py               # re-exports the public surface
│   │   ├── processor.py              # OCRProcessor class
│   │   ├── prompts.py                # prompt constants + select_page_prompt / select_crop_prompt helpers
│   │   ├── filters.py                # fallback detection + runaway stripping + normalize_ocr_text
│   │   └── exceptions.py             # LLMCallError + ModelNotLoadedError
│   ├── grounded/                     # NEW package (was core/grounded.py, 710 LOC)
│   │   ├── __init__.py               # re-exports the public surface
│   │   ├── protocol.py               # GroundedOCRBackend Protocol + ProgressCallback / WarningCallback aliases
│   │   ├── types.py                  # GroundedBlock, GroundedResponse, _clamp helper
│   │   ├── filters.py                # _NON_CONTENT_LABELS + is_content_label helper
│   │   ├── parsers.py                # parse_zai_response, parse_glm_layout_details, _detect_axis_order_zxyxy
│   │   ├── rasterization.py          # _rasterize_to_jpeg_pages (moved out of PromptedGroundedOCR body)
│   │   ├── prompted.py               # PromptedGroundedOCR + DEFAULT_GROUNDING_PROMPT
│   │   └── zai.py                    # ZAIHostedOCR (skeleton; experimental)
│   └── (every other module unchanged)
└── api/
    ├── routers/
    │   ├── ocr.py                    # THIN: only the /process route (~80 LOC orchestration)
    │   └── (ai.py DELETED — 115 LOC, never mounted)
    └── services/
        ├── ocr_settings.py           # NEW: _resolve_process_settings + _validation_error_response
        ├── ocr_pipeline_factory.py  # NEW: _build_pipeline, _verify_backend_model, _select_backend factory
        ├── ocr_response.py           # NEW: _build_file_response + _document_quality/_structure/_sections_header
        └── ocr_jobs.py               # NEW: _record_job + stage_to_percent helper
```

### 2.2 Public surface preserved (verbatim re-exports)

The following imports must work unchanged after every phase:

```python
# Already worked before, must still work after every phase:
from local_deepl import (OCRPipeline, HybridAligner, OCRProcessor, PDFHandler,
                         PromptedGroundedOCR, build_document_processors)
from local_deepl.core.ocr import (
    OCRProcessor, LLMCallError, ModelNotLoadedError,
    OLMOCR_PAGE_PROMPT, CROP_PROMPT, DUAL_ENGINE_PAGE_PROMPT, DUAL_ENGINE_CROP_PROMPT,
    CORRECTION_PAGE_PROMPT, CORRECTION_CROP_PROMPT,
    HANDWRITING_PAGE_PROMPT, HANDWRITING_CROP_PROMPT,
    _HALLUCINATION_PATTERNS, _is_fallback_response,
)
from local_deepl.core.grounded import (
    GroundedBlock, GroundedResponse, GroundedOCRBackend,
    PromptedGroundedOCR, ZAIHostedOCR,
    parse_zai_response, parse_glm_layout_details,
    DEFAULT_GROUNDING_PROMPT,
)
from local_deepl.api.routers.ocr import router  # FastAPI router object
# `api.routers.ai` is the only public name being removed — see §4.4.
```

**Verification**: `python -c "from local_deepl import OCRPipeline, OCRProcessor, PromptedGroundedOCR"` runs clean at every phase boundary.

## 3. Components and Contracts

### 3.1 `core/ocr/` sub-package

| Module | Responsibility | Imports | Public surface |
|---|---|---|---|
| `__init__.py` | Re-export everything from siblings | siblings | re-exports |
| `exceptions.py` | Define exception hierarchy | — | `LLMCallError`, `ModelNotLoadedError` |
| `prompts.py` | Hold prompt constants and selection helpers | — | `OLMOCR_PAGE_PROMPT`, `CROP_PROMPT`, `DUAL_ENGINE_PAGE_PROMPT`, `DUAL_ENGINE_CROP_PROMPT`, `CORRECTION_PAGE_PROMPT`, `CORRECTION_CROP_PROMPT`, `HANDWRITING_PAGE_PROMPT`, `HANDWRITING_CROP_PROMPT`, `select_page_prompt`, `select_crop_prompt` |
| `filters.py` | LLM-output text filtering | — | `_HALLUCINATION_PATTERNS`, `_is_fallback_response`, `_strip_runaway_repetition` |
| `processor.py` | The OCR backend (LiteLLM wrapper) | `openai.AsyncOpenAI`, `dotenv`, sibling modules | `OCRProcessor` |

**Boundary rules**:
- `processor.py` calls `filters._is_fallback_response` and `filters._strip_runaway_repetition` directly.
- `prompts.select_page_prompt` is the single source of truth for which page prompt a config implies (printed, dual-engine correction, handwriting).
- No file imports from `api/`, `core/grounded/`, or `core/workflows/`.

### 3.2 `core/grounded/` sub-package

| Module | Responsibility | Imports | Public surface |
|---|---|---|---|
| `__init__.py` | Re-export everything from siblings | siblings | re-exports |
| `protocol.py` | Define the backend Protocol and callback aliases | — | `GroundedOCRBackend`, `ProgressCallback`, `WarningCallback` |
| `types.py` | Shared dataclasses and helpers | — | `GroundedBlock`, `GroundedResponse`, `_clamp` |
| `filters.py` | Label-based content filtering | `types` | `_NON_CONTENT_LABELS`, `is_content_label` |
| `parsers.py` | Parse backend-specific JSON into `GroundedResponse` | `types`, `filters` | `parse_zai_response`, `parse_glm_layout_details`, `_detect_axis_order_zxyxy` |
| `rasterization.py` | Synchronous PDF/image → JPEG base64 | `PIL`, `fitz` (runtime), `core.pdf` | `_rasterize_to_jpeg_pages` |
| `prompted.py` | The `PromptedGroundedOCR` backend | siblings, `core.llm_client`, `core.pdf` | `PromptedGroundedOCR`, `DEFAULT_GROUNDING_PROMPT` |
| `zai.py` | The `ZAIHostedOCR` backend (experimental) | siblings, `httpx`, `core.llm_client` | `ZAIHostedOCR` |

**Boundary rules**:
- Each backend (`prompted.py`, `zai.py`) imports `parsers.parse_*` and `rasterization._rasterize_to_jpeg_pages`.
- The Protocol lives in `protocol.py` and is implemented by both backends — `isinstance(x, GroundedOCRBackend)` works because the Protocol is structural (not ABC).
- `parsers.py` does not import any backend — it parses payloads into shapes; backends call it.
- `rasterization.py` does not import any backend — it is an async wrapper for a synchronous I/O routine.
- No file imports from `api/`, `core/ocr/`, `core/workflows/`.

### 3.3 `api/routers/ocr.py` (thin) + 4 new `api/services/`

The router file becomes a thin orchestrator that delegates to 4 siblings in `api/services/`.

| New module | Responsibility | Public surface | Imports |
|---|---|---|---|
| `api/services/ocr_settings.py` | Form-field merging + validation-error response | `_resolve_process_settings`, `_validation_error_response` | `api.schemas.ProcessSettings`, `api.routers.config._config` |
| `api/services/ocr_pipeline_factory.py` | Pipeline + backend construction + model-load pre-flight | `_build_pipeline`, `_verify_backend_model`, `_select_backend` | `core.ocr.processor.OCRProcessor`, `core.grounded.prompted.PromptedGroundedOCR`, `core.trocr_engine.TrOCREngine`, `core.preprocessing.*`, `core.processors.build_document_processors`, `api.routers.state`, `api.routers.websocket.manager` |
| `api/services/ocr_response.py` | Sandwich-PDF response builder + per-page metadata header builders | `_build_file_response`, `_document_quality_header`, `_document_structure_header`, `_document_sections_header` | `api.services.document_metadata`, `api.services.workflow`, `api.routers.state` |
| `api/services/ocr_jobs.py` | Append to in-memory job history; map stage→percent | `_record_job`, `stage_to_percent` | `api.routers.state`, `api.services.jobs.JobStatus` |

The thin `api/routers/ocr.py` keeps only:
- `router = APIRouter()` declaration
- `@router.post("/process")` handler that calls services in order
- Lazy `from .ocr_settings import _resolve_process_settings` etc. as needed to keep cycle-free imports

The `_select_backend` factory collapses the 33-line if/else:

```python
def _select_backend(settings: ProcessSettings) -> Any:
    """Return the OCR backend that matches the requested pipeline mode.

    For grounded mode, returns a `PromptedGroundedOCR` backend that
    performs single-call bbox-native OCR.
    For hybrid mode, returns an `OCRProcessor` (LiteLLM-based) — and
    optionally wraps it with a `TrOCREngine` when `handwriting_mode`
    is enabled.
    """
    if settings.pipeline_mode == "grounded":
        return PromptedGroundedOCR(
            api_base=settings.api_base,
            api_key=settings.api_key,
            model=settings.model,
            max_image_dim=settings.max_image_dim,
            concurrency=settings.concurrency,
        )
    ocr_kwargs: dict[str, Any] = dict(
        api_base=settings.api_base,
        api_key=settings.api_key,
        model=settings.model,
        handwriting_mode=settings.handwriting_hint,
    )
    if settings.handwriting_hint:
        from local_deepl.core.trocr_engine import TrOCREngine
        ocr_kwargs["trocr_engine"] = TrOCREngine()
    return OCRProcessor(**ocr_kwargs)
```

**Boundary rules**:
- `api/services/ocr_*` modules import from `core/`, `api/services/`, `api/routers/state.py`, `api/routers/websocket.py` (manager). They do not import from `api/routers/ocr.py`.
- `api/routers/ocr.py` imports from the new services. The router is the only file that exports the `router` object.
- The `_cleanup` helper already lives in `api/routers/common.py` and stays there.

### 3.4 Dead `api/routers/ai.py` deletion

The file `api/routers/ai.py` (115 LOC) defines 4 routes that are NOT mounted in `server.py:85-91`. The functional duplicates already exist in `api/routers/translation.py` and `api/routers/extraction.py`. `ARCHITECTURE.md` line 54 incorrectly claims `ai.py` is "consumed by extraction.py and translation.py". 

**Action**: delete `api/routers/ai.py` and update `ARCHITECTURE.md` line 54 + line 133 (Key Files row). Verify `server.py` does NOT include this router (it doesn't — confirmed).

## 4. Data Flow

### 4.1 OCR request flow (before and after — unchanged)

```
POST /process (multipart)
    ↓
api/services/ocr_settings._resolve_process_settings  [P3]
    ↓
api/services/ocr_pipeline_factory._select_backend    [P3]
    ↓
api/services/ocr_pipeline_factory._verify_backend_model  [P3]
    ↓
api/services/ocr_pipeline_factory._build_pipeline    [P3]
    ↓
OCRPipeline.run(...)
    ↓ (internally)
HybridEngine.execute(...) | GroundedEngine.execute(...)
    ↓
api/services/ocr_jobs._record_job                     [P3]
    ↓
api/services/ocr_response._build_file_response       [P3]
    ↓
FileResponse + custom headers
```

### 4.2 HybridEngine internal flow (unchanged — out of scope)

`core/workflows/hybrid.py` and `core/workflows/grounded.py` stay byte-for-byte. `core/workflows/base.py` stays unchanged.

### 4.3 Grounded backend internal flow (preserved by PromptedGroundedOCR)

```
PromptedGroundedOCR.ocr_document(input_path, ...)
    ↓ await asyncio.to_thread(_rasterize_to_jpeg_pages, ...)   [P2: import from rasterization.py]
    ↓ for each page: call_llm(prompt, image)
    ↓ parse response with parsers.parse_zai_response (or JSON parser)  [P2]
    ↓ return GroundedResponse
```

### 4.4 OCRProcessor internal flow (preserved by core.ocr.processor)

```
OCRProcessor.perform_ocr(...) / perform_ocr_on_crop(...)
    ↓ _chat(page_base64, prompt)
    ↓ openai.AsyncOpenAI -> LiteLLM
    ↓ filters._is_fallback_response(text) → discard
    ↓ filters._strip_runaway_repetition(text) → clean
    ↓ return text
```

## 5. Error Handling

No error-handling behavior changes. The decomposition must preserve:

- `LLMCallError` continues to wrap connection refused, timeout, auth, model-not-loaded with a message naming the api-base + model.
- `ModelNotLoadedError` continues to fire from `OCRProcessor.ensure_model_loaded` *before* any OCR work.
- The `/process` route's `ValidationError → JSONResponse(status_code=422)` path is preserved.
- The `_stable_server_error()` (in `api/routers/common.py`) and `_cleanup` helpers stay where they are.
- The `_create_document_metadata_artifact` helper from P3 reads `pipeline.last_document_result`; if no metadata exists, return `None` (header gets dropped, not errored).
- `_record_job` continues to record `status="error"` on the existing exception catches in the route.

The new `_select_backend` factory never raises; it just builds. The validation of `api_base` against SSRF happens earlier, in the route (`is_ssrf_target(settings.api_base)`).

## 6. Testing

### 6.1 Policy

- **Behavior preservation is proven by the existing test suite passing unmodified** at every phase boundary. No new tests are added in this scope.
- The full suite (`uv run pytest -q`) is the verification gate. No new tests added.
- `uv run ruff check src tests && uv run mypy src` must be clean at every phase boundary.
- A smoke check `python -c "from local_deepl import OCRPipeline, OCRProcessor, PromptedGroundedOCR"` runs at every phase boundary.

### 6.2 Test files touched (none expected to change)

Existing tests already exercise:
- `tests/test_ocr.py` — covers `core/ocr.py::OCRProcessor` → continues to cover `core/ocr/processor.py::OCRProcessor` via re-export.
- `tests/test_grounded.py` — covers parsers + backends → continues to cover the new `core/grounded/` sub-package.
- `tests/test_ocr_trocr_integration.py` — exercises handwriting-mode wiring in the route factory.
- `tests/test_api_safety.py` — covers upload validation, SSRF, opaque artifact IDs, header behavior.
- `tests/test_ai_router.py` — covers `api/routers/ai.py` routes; will be **deleted** in P4 because that router is deleted.
- `tests/test_ai_services.py` — covers `api/services/ai.py` (the SERVICE module — not the dead ROUTER); this test continues unchanged.

### 6.3 Test file deletion in P4

`tests/test_ai_router.py` tests routes that are being deleted. Inspect the file before deletion; if it covers any behavior retained elsewhere, port the relevant tests to the right test file (`tests/test_api_safety.py` or similar). Otherwise, delete it together with `api/routers/ai.py` in P4.

## 7. Sequencing and PR Boundaries

Each phase is one PR. Each PR's diff keeps the test suite green and the public surface stable.

| Phase | Touch | Why | PR Title |
|---|---|---|---|
| **P1** | `core/ocr.py` → `core/ocr/{__init__,processor,prompts,filters,exceptions}.py` | Single-responsibility split of OCR backend | `refactor(core): split core/ocr.py into core/ocr sub-package` |
| **P2** | `core/grounded.py` → `core/grounded/{__init__,protocol,types,filters,parsers,rasterization,prompted,zai}.py` | Single-responsibility split of grounded backends | `refactor(core): split core/grounded.py into core/grounded sub-package` |
| **P3** | Thin `api/routers/ocr.py` + `api/services/{ocr_settings,ocr_pipeline_factory,ocr_response,ocr_jobs}.py` | Extract 4 concerns out of the route file | `refactor(api): thin api/routers/ocr.py and extract 4 ocr_* services` |
| **P4** | Delete `api/routers/ai.py` (and possibly `tests/test_ai_router.py`); update `ARCHITECTURE.md` line 54 + Key Files row | Remove dead code, fix misleading docs | `refactor(api): delete dead api/routers/ai.py and update docs` |

### Discipline rules (applied to every PR)

1. `python -c "from local_deepl import OCRPipeline, OCRProcessor, PromptedGroundedOCR, HybridAligner, PDFHandler, build_document_processors"` exits 0.
2. `uv run pytest -q` exits 0 (slow tests excluded; mark "not slow" if full suite is the audit).
3. `uv run ruff check src tests` exits 0.
4. `uv run mypy src` exits 0.
5. No file in the diff exceeds 350 LOC (soft target — prompts.py + filters.py may be tighter).
6. No new public symbol is added or removed.
7. No `api/`, `core/document.py`, `core/workflows/`, `core/processors.py`, `core/aligner.py`, `core/pdf.py`, or web frontend code is touched in P1-P3.

## 8. Open Questions (deferred)

These are explicitly out of scope and noted for future work:

- **Lossy `pages_structured` ↔ `DocumentResult` round-trip** (scout finding #8) — separate IR contract rework.
- **`_run_spellcheck` not threaded** (scout finding #16) — separate perf fix.
- **`ZAIHostedOCR` placeholder URLs** (scout finding #10) — separate backend-completion work; P2 just moves the skeleton, doesn't fix it.
- **No auth/rate-limit/metrics on `/api/*`** — separate production-readiness work.
- **Hungarian matching in confidence harness** (scout finding, PLAN.md R11) — separate scoring work.

## 9. Acceptance Criteria

The refactor is complete when:

1. `find src/local_deepl -name "*.py" -size +350c` returns no file with LOC > 350 for the three in-scope god modules (the others were already under that bar).
2. `python -c "from local_deepl import OCRPipeline, OCRProcessor, PromptedGroundedOCR, GroundedOCRBackend, HybridAligner, PDFHandler, build_document_processors"` exits 0.
3. `python -c "from local_deepl.core.ocr import OCRProcessor, LLMCallError; from local_deepl.core.grounded import GroundedBlock, GroundedResponse, PromptedGroundedOCR, ZAIHostedOCR"` exits 0.
4. `uv run pytest -q` exits 0 at the final state (sum of phases).
5. `uv run ruff check src tests` exits 0.
6. `uv run mypy src` exits 0.
7. `grep -R "api.routers.ai" src/ tests/` returns 0 matches after P4.
8. `grep -R "consumed by extraction" ARCHITECTURE.md` returns 0 matches after P4.
9. The thin `api/routers/ocr.py` is < 100 LOC (down from 662).
10. `core/ocr/*.py` and `core/grounded/*.py` each have a 1-3 line module-level docstring naming their single responsibility.
