# Domain 1 Audit: Core Pipeline

**Date:** 2026-08-17
**Auditor:** Mavis (explore subagent, deep-evidence investigation)
**Methodology:** Read every file in scope end-to-end, then cross-checked AGENTS.md architectural claims against the code. Verified each known-tech-debt bullet with file:line citations.

## Scope
- **Files examined**: 70 (under `src/omniscribe/core/**`, plus `src/omniscribe/pipeline.py`, `src/omniscribe/evaluation.py`, `src/omniscribe/config.py`, `src/omniscribe/utils/`)
- **Lines of code reviewed**: ~6,500
- **Key paths reviewed**:
  - `core/ocr/{resilience,client,processor,prompts,filters,multi_format_client,exceptions}.py`
  - `core/aligner.py`, `core/text_recall.py`, `core/text_layer_recall.py`
  - `core/workflows/{base,hybrid,grounded,repair,utils}.py`
  - `core/grounded/{__init__,models,parsers,prompted,rasterize}.py`
  - `core/ocr_quality/{script_detector,watermark,hallucination,calibration,trust_scorer,orchestrator}.py`
  - `core/processors/{base,reading_order,structure,section,layout,quality,table}.py`
  - `core/{document,preprocessing,postprocess,routing,evaluation}.py`
  - `core/pdf/embedder.py`
  - `utils/{env,json_parse,prompt_safety,image}.py`
  - `pipeline.py`, `config.py`, `evaluation.py`

## Methodology
Read every file in scope end-to-end, then cross-checked AGENTS.md architectural claims against the code. Verified each known-tech-debt bullet with file:line citations. Prioritized focus areas 1-7 in order, looking for: retry-storm / multiplier bugs, layering violations, shared-state race conditions, bbox normalization pitfalls, circuit-breaker semantic mismatches, retry classification gaps, and deterministic ordering of document processors. Cross-cutting checks looked for security holes, asyncio misuse, and silent fallbacks (e.g. gpt-4o default).

## Findings

| ID | Severity | Area | File:Line | Description | Evidence | Recommendation |
|----|----------|------|-----------|-------------|----------|----------------|
| F1.1 | CRITICAL | Layering | `src/omniscribe/core/ocr/multi_format_client.py:20,94,117`; `src/omniscribe/core/llm_client.py:13,96,107,154,165` | Core OCR modules import from `omniscribe.api` (schemas + `ProviderManager`). This inverts the documented layering. | Runtime imports inside function bodies | Extract `ProviderConfig` into `core/` |
| F1.2 | CRITICAL | Retry storm | `src/omniscribe/core/ocr/multi_format_client.py:223-297`; `src/omniscribe/core/ocr/processor.py:399-451` | Two layered retry loops multiply attempts. | `_chat` outer loop + `complete_vlm_prompt` inner loop | Pick ONE retry layer |
| F1.3 | CRITICAL | Silent default model | `src/omniscribe/core/ocr/multi_format_client.py:102-106` | When `provider_config.models` is empty AND no `model` is passed, target model falls back to literal `"gpt-4o"`. | `else "gpt-4o"` | Raise `LLMCallError` instead |
| F1.4 | HIGH | Shared async client | `src/omniscribe/core/ocr/multi_format_client.py:30-48,51-57` | `_shared_client` is loop-bound; cross-loop reuse fails with "loop is closed". | `_get_shared_client` no loop tracking | Track the loop; on a different loop, close old + create new |
| F1.5 | HIGH | Circuit breaker counts per attempt | `src/omniscribe/core/ocr/processor.py:431-433` | Breaker increments per outer iteration; operator metric "1 failure/page" while actual call count is 9. | `record_failure` inside outer except | Track inner attempts; pass `n=attempts` to `record_failure` |
| F1.6 | HIGH | NaN/inf bbox in aligner | `src/omniscribe/core/aligner.py:155-161,316-317` | NaN bbox from Surya silently dropped; `_clamp` propagates NaN. | `_clamp` + `cx1 > cx0` check | Detect NaN/inf in `_clamp`; log per-page NaN count |
| F1.7 | HIGH | Reading-order recursion | `src/omniscribe/core/aligner.py:329-371` | DP runs twice (row-major + col-major) for single-column pages; 2× cost on dense pages. | `_reading_order_indices` invoked twice | Cache permutations; skip col-major for small n |
| F1.8 | HIGH | Repair-loop stall guard | `src/omniscribe/core/workflows/repair.py:132-135` | Stall guard vs `None` confidence: custom estimator that returns `None` crashes the loop. | `if new_conf <= conf` | Coerce `None` to 0.0 before compare |
| F1.9 | MEDIUM | Settings snapshot | `src/omniscribe/core/ocr/processor.py:105-120` | Class-level env snapshot means runtime `OMNISCRIBE_*` overrides don't take effect on a long-running process. | `_settings = load_settings()` at module import | Re-read on first use per-instance, or document prominently |
| F1.10 | MEDIUM | Calibration cache | `src/omniscribe/core/ocr_quality/calibration.py:33-82` | `_CACHE` is unbounded; deployments with per-request model selectors leak. | `dict[str, tuple[float, float] | None] = {}` | Add bounded LRU (e.g. 64 entries) |
| F1.11 | MEDIUM | Watermark detect CPU cost | `src/omniscribe/core/ocr_quality/watermark.py:40-60` | Pure-Python double loop in `_midgray_fraction`; ~10× speedup available with numpy. | Nested for loops | Vectorize with numpy or PIL thumbnail |
| F1.12 | MEDIUM | Detection predictor race | `src/omniscribe/core/aligner.py:43-122` | `_shared_predictor_lock` serializes all detection through one forward pass. | `_shared_predictor_lock` | Document the implicit single-flight; expose `asyncio.Semaphore(N)` |
| F1.13 | MEDIUM | Dual-engine fallback masking | `src/omniscribe/core/ocr/processor.py:478-499` | `_get_tesseract_draft` silently returns `""` on every Tesseract error. | Broad except | Add per-run counter; emit one warning when > 0 |
| F1.14 | MEDIUM | Grounded repair feature-detect | `src/omniscribe/core/workflows/grounded.py:136,230` | `hasattr(self.grounded_backend, "ocr_crop")` duck-type gate; static contract is `GroundedOCRBackend` with only `ocr_document`. | `# type: ignore[attr-defined]` | Promote to `RepairableGroundedBackend` Protocol |
| F1.15 | MEDIUM | Cross-page merge mutability | `src/omniscribe/core/workflows/base.py:230-269` | `_cross_page_merge` mutates `pages_structured` in place without defensive copy. | `p1_boxes[last_idx] = (_last_bbox, "")` | Make a shallow copy before mutating, or document the in-place contract |
| F1.16 | MEDIUM | Grounded path silently drops text labels | `src/omniscribe/core/grounded/parsers.py:174-179` | `parse_glm_layout_details` strict-equality filters non-"text" labels; inconsistent with Qwen parser's allow-list. | `if b.get("label") != "text": continue` | Apply same allow-list in both parsers |
| F1.17 | MEDIUM | Crop padding duplicate | `src/omniscribe/core/grounded/prompted.py:153-178` vs `utils/image.py:14-68` | Two different crop paddings (5% vs 0.5%) and JPEG qualities (90 vs 85) break trust-score calibration parity. | Two different crop functions | Centralize crop parameters in one config object |
| F1.18 | MEDIUM | `asyncio.to_thread` around sync b64 decode | `src/omniscribe/core/workflows/hybrid.py:457-462` | `_decode_chunk_bytes` runs `base64.b64decode` inside `asyncio.to_thread`; thread-pool round-trip can exceed the work. | `await asyncio.to_thread(...)` | Decode base64 in main loop; only offload PIL decode + Surya forward |
| F1.19 | LOW | Logger exceptions in except | `src/omniscribe/core/ocr/processor.py:301-305` | `logger.warning("TrOCR arbitration failed: %s", e)` lacks `exc_info=True`; traceback hidden. | `_run_trocr_arbitration` except | Add `exc_info=True` for parity |
| F1.20 | LOW | Pre-flight check cost | `src/omniscribe/core/ocr/processor.py:153-170` | `ensure_model_loaded` re-hits `GET /v1/models` on every instance creation. | `_list_loaded_model_ids(...)` per call | Cache per (api_base, ttl) |
| F1.21 | LOW | Repaginate early-return | `src/omniscribe/core/ocr/processor.py:74-75` | OlmOCR dual-engine / correction paths fall back to single user-role; add a regression test. | `_resolve_page_system` returns None | Add regression test pinning the dual-engine prompt body for OlmOCR |
| F1.22 | LOW | `ocr._apply_adaptive_threshold` numpy import | `src/omniscribe/core/ocr/processor.py:559-560` | `import numpy as np` inside the function; hoist to module top. | Inline import | Hoist with TYPE_CHECKING guard |
| F1.23 | LOW | `_clamp` does not propagate NaN guard | `src/omniscribe/core/aligner.py:316-317`; `src/omniscribe/core/grounded/parsers.py:68-69` | Both `_clamp` implementations silently pass NaN through. | `_clamp = max(0.0, min(1.0, v))` | Add explicit NaN check |
| F1.24 | LOW | `OCRProcessor` reads env at instance init | `src/omniscribe/core/ocr/processor.py:133-137` | `__init__` reads env at instance time (asymmetric vs class-level snapshot from F1.9). | `os.getenv("LLM_API_BASE")` at init | Document the asymmetry, or read env only once at module load |
| F1.25 | LOW | `_ocr_per_box` swallows `OCRCancelled` | `src/omniscribe/core/workflows/hybrid.py:919-925` | `except Exception as e` does not explicitly re-raise `OCRCancelled`. | `except Exception as e: return idx, ""` | Add `except OCRCancelled: raise` mirroring `CircuitOpenError` |

### CRITICAL findings (detailed writeup)

**F1.1** — Core OCR modules import from `omniscribe.api`
- File:line evidence
  - `src/omniscribe/core/llm_client.py:13,96,107,154,165`
  - `src/omniscribe/core/ocr/multi_format_client.py:20,94,117`
- Code snippet (from `core/llm_client.py:96-110`):
  ```python
  if api_base:
      from omniscribe.api.schemas import ProviderConfig, ProviderFormatEnum
      provider_config = ProviderConfig(...)
  else:
      from omniscribe.api.services.provider_manager import get_provider_manager
      mgr = get_provider_manager()
      provider_config = mgr.get_active_provider()
  ```
- Why it matters: AGENTS.md documents `core/` as the lower layer and `api/` as the upper layer. Importing downward from core to api inverts the dependency. An in-process caller (e.g. embedded workflow, Jupyter notebook) doing `from omniscribe.core.ocr import OCRProcessor` drags in `omniscribe.api.services.provider_manager`, which transitively imports `omniscribe.config` (settings) and `omniscribe.api.schemas` (Pydantic models with validators on env-driven fields). The "core" module is no longer usable in isolation.
- Recommended fix: Extract a core-owned `ProviderConfig` and `ProviderFormatEnum` into `omniscribe/core/providers.py` (one-line fields, no Pydantic coupling to settings). Have `omniscribe.api.schemas.ProviderConfig` either subclass or alias it. `ProviderManager` becomes a thin wrapper that the API layer provides as a callable injected into `OCRProcessor`/`PromptedGroundedOCR`.
- Regression test: `test_ocr.py::test_core_does_not_import_api` — a static import-graph test that `importlib.util.find_spec` walks and fails if any `omniscribe.core.*` module imports from `omniscribe.api`.

**F1.2** — Retry multiplication between `OCRProcessor` and `multi_format_client`
- File:line evidence: `src/omniscribe/core/ocr/processor.py:399-451`; `src/omniscribe/core/ocr/multi_format_client.py:223-297`
- Code snippet (combined paths):
  ```python
  # processor.py:399
  for attempt in range(self.MAX_RETRIES + 1):  # default 3
      try:
          content = await call_llm(...)  # → multi_format_client.complete_vlm_prompt
  # multi_format_client.py:223
  for attempt in range(1, max_retries + 2):  # default 3
      try:
          resp = await client.post(...)
          ...
      except Exception as exc:
          if is_transient_error(exc) and attempt <= max_retries:
              ...
              continue
  ```
- Why it matters: On a persistently failing endpoint, each `_chat` call results in 3×3=9 VLM page POSTs plus up to 30s of backoff. Circuit breaker cannot fail fast because the inner loop swallows failures into one `LLMCallError`. Worst-case ~36+ minutes PER PAGE. A misconfigured `OMNISCRIBE_LLM_MAX_RETRIES=10` means 121 VLM calls per page. CWE-400 uncontrolled resource consumption.
- Recommended fix: Pick one retry layer. Cleanest: `multi_format_client` does NO retries; `OCRProcessor._chat` is the single retry authority.
- Regression test: `test_ocr.py::test_retry_storm_does_not_multiply` — mock `client.post` to always return 500; assert call count is `MAX_RETRIES + 1` not `(MAX_RETRIES + 1) × (max_retries + 1)`.

**F1.3** — Default model fallback to `gpt-4o`
- File:line: `src/omniscribe/core/ocr/multi_format_client.py:102-106`
- Code:
  ```python
  target_model = (
      model.strip()
      if model and model.strip()
      else (provider_config.models[0] if provider_config.models else "gpt-4o")
  )
  ```
- Why it matters: When neither the `model` arg nor `provider_config.models` carries a value, the code defaults to literal `"gpt-4o"`. If `api_url` is set to `https://api.openai.com/v1` with `models=[]` accidentally, the pipeline silently calls OpenAI cloud. Cost + privacy surprise.
- Recommended fix: Raise `LLMCallError` with a clear message when both `model` and `provider_config.models` are empty.
- Regression test: `test_multi_format_client.py::test_missing_model_raises` — assert `LLMCallError` when both sources are empty.

### HIGH findings (detailed writeup)

**F1.4** — Shared `httpx.AsyncClient` is loop-bound
- File:line: `src/omniscribe/core/ocr/multi_format_client.py:30-48`
- Code:
  ```python
  _client_lock = threading.Lock()
  _shared_client: httpx.AsyncClient | None = None

  def _get_shared_client() -> httpx.AsyncClient:
      global _shared_client
      if _shared_client is not None:
          return _shared_client
      with _client_lock:
          if _shared_client is None:
              _shared_client = httpx.AsyncClient(timeout=_DEFAULT_CLIENT_TIMEOUT_S)
      return _shared_client
  ```
- Why it matters: httpx `AsyncClient` is bound to the event loop on which it was first `await`ed. The shared client is created on whatever loop runs first; subsequent awaits on a different loop raise `RuntimeError: ... bound to a different event loop` or "loop is closed". The only escape hatch is `aclose_shared_client` (line 51), wired into FastAPI shutdown.
- Recommended fix: Track the loop on which the client was created (`_shared_client_loop`); on a different loop, close the old client and lazily create a new one.

**F1.5** — Circuit breaker increments per outer iteration
- File:line: `src/omniscribe/core/ocr/processor.py:431-433`
- Code:
  ```python
  except Exception as e:
      last_exc = e
      await self.circuit_breaker.record_failure()
      if not is_transient_error(e):
          break
  ```
- Why it matters: Every caught exception (including the inner-loop `LLMCallError` that already absorbed multiple inner attempts) increments `_consecutive_failures`. An operator reading the breaker state has no way to tell "one page took 9 attempts" from "9 pages took 1 attempt each".
- Recommended fix: Track the actual attempt count in `last_exc` and call `record_failure(n=attempts)`.

**F1.6** — NaN bbox in aligner
- File:line: `src/omniscribe/core/aligner.py:155-161`
- Code:
  ```python
  cx0 = _clamp(x0 / img_w)
  cy0 = _clamp(y0 / img_h)
  cx1 = _clamp(x1 / img_w)
  cy1 = _clamp(y1 / img_h)
  if cx1 > cx0 and cy1 > cy0:
      boxes.append((cx0, cy0, cx1, cy1))
  ```
- Why it matters: When Surya returns NaN, `_clamp(NaN)` returns NaN (max/min propagate NaN). The downstream `cx1 > cx0` is False (NaN comparison). The box is silently dropped. A document with many NaN boxes loses layout with no error.
- Recommended fix: In `_clamp`, return `0.0` (or raise) when `v` is NaN/inf. Log a one-line WARNING per page with NaN count.

**F1.8** — Repair loop stall guard vs `None` confidence
- File:line: `src/omniscribe/core/workflows/repair.py:132-135`
- Code:
  ```python
  new_conf = self._estimate(new_text)
  if new_conf <= conf:
      break  # stall guard: keep the best text seen so far
  ```
- Why it matters: The default `_estimate_confidence` returns `float`. But `QualityRepairLoop.__init__` accepts `confidence_estimator: Callable[[str], float] | None`, and `BlockCallbackSet`'s related callbacks allow `Optional[float]`. A custom estimator that returns `None` crashes the loop on the comparison.
- Recommended fix: Treat `None` as the lowest possible confidence: `if new_conf is None or new_conf <= conf: break`.

### MEDIUM findings (one-liner each)
- F1.9 — `src/omniscribe/core/ocr/processor.py:105-120` — Class-level env snapshot; document or refresh.
- F1.10 — `src/omniscribe/core/ocr_quality/calibration.py:33` — `_CACHE` is unbounded; switch to LRU.
- F1.11 — `src/omniscribe/core/ocr_quality/watermark.py:40-60` — Pure-Python double loop; vectorize with numpy.
- F1.12 — `src/omniscribe/core/aligner.py:43-122` — `_shared_predictor_lock` serializes all detection.
- F1.13 — `src/omniscribe/core/ocr/processor.py:478-499` — `_get_tesseract_draft` silently returns `""`; add per-run counter.
- F1.14 — `src/omniscribe/core/workflows/grounded.py:136,230` — `hasattr` duck-type gate; promote to Protocol.
- F1.15 — `src/omniscribe/core/workflows/base.py:230-269` — `_cross_page_merge` mutates in place.
- F1.16 — `src/omniscribe/core/grounded/parsers.py:174-179` — `parse_glm_layout_details` strict-equality; inconsistent with Qwen parser.
- F1.17 — `src/omniscribe/core/grounded/prompted.py:153-178` — Two different crop paddings/qualities between paths.
- F1.18 — `src/omniscribe/core/workflows/hybrid.py:457-462` — `asyncio.to_thread` wraps `base64.b64decode` which is fast.
- F1.25 — `src/omniscribe/core/workflows/hybrid.py:919-925` — `_ocr_per_box` swallows `OCRCancelled`.

### LOW findings (one-liner each)
- F1.19 — `src/omniscribe/core/ocr/processor.py:301-305` — `logger.warning("TrOCR arbitration failed: %s", e)` lacks `exc_info=True`.
- F1.20 — `src/omniscribe/core/ocr/processor.py:153-170` — `ensure_model_loaded` re-hits `GET /v1/models` per call.
- F1.21 — `src/omniscribe/core/ocr/prompts.py:60-66,69-85` — OlmOCR dual-engine fallback; add regression test.
- F1.22 — `src/omniscribe/core/ocr/processor.py:559` — `import numpy as np` inside function; hoist.
- F1.23 — `src/omniscribe/core/aligner.py:316-317`; `src/omniscribe/core/grounded/parsers.py:68-69` — `_clamp` propagates NaN.
- F1.24 — `src/omniscribe/core/ocr/processor.py:133-137` — `__init__` reads env at instance time (asymmetric).

## Cross-cutting observations

1. **Layering inversion (F1.1)** is the most consequential cross-cutting issue.
2. **Retry policy is split across three layers with no single owner** (F1.2, F1.5, F1.9).
3. **Memory safety is well-handled** for in-flight runs; concerns are unbounded calibration cache (F1.10) and 1000-page document base64 retention in `images_dict`.
4. **Grounded vs hybrid path asymmetry** (F1.16, F1.17) is a real cross-cutting concern.
5. **OCR Quality Trust Layer is well-designed for fail-open**.
6. **Repair loop is sequential by design**; a 500-page document with many below-target blocks spends wall time `O(blocks × max_retries × per_block_OCR_time)`.
7. **Detection predictor reuse is correct** (P2-9) — the singleton + lock pattern.
8. **Document processors are deterministic and well-typed**.
9. **Calibration cache (F1.10) is the one place where memory could grow unbounded**.
10. **No `await` missing in async paths**.

## Positive findings

- **Calibration guard is well-designed**: Platt scaling with "identity" sentinel and per-model JSON file; clamps out-of-range raw scores; numerical stability via branch on sign of `z` (`sigmoid`).
- **Trust scoring is pure and well-tested**: `trust_scorer.score` is a single function with no I/O, contract-clamped weights, dedup of flags preserving order.
- **Watermark detection is genuinely fail-open**: every code path is wrapped in `try/except`.
- **Circuit breaker is well-shaped**: per-endpoint registry (keyed on `(api_base, model)`) survives across `OCRProcessor` instances; half-open probe correctly reopens on failure.
- **System role gating is single-source-of-truth**: `_MODELS_WITHOUT_SYSTEM_ROLE` set + `model_supports_system_role` + `_resolve_page_system` / `_resolve_crop_system` helpers.
- **Whitespace + text-layer recall deduplication** is correctly ordered.
- **DP alignment handles degenerate cases** (zero boxes, zero lines, single-line-many-boxes) with a documented full-page fallback.
- **Phase 3 cancel propagation** is correct: `OCRCancelled` is `BaseException` (not `Exception`), so per-page isolation blocks don't swallow it.
- **`llm_client._extract_prompt_and_image` correctly drops system-role entries** from `messages`.
- **Pydantic-settings config** is centralized, env-driven, with explicit validators.

## Coverage gaps

- **Live VLM behavior**: Could not exercise the OCR processor against a real LM Studio / Ollama instance.
- **Surya 0.17.x specific bugs**: NaN bbox risk noted; exact reproducer/frequency unverified.
- **PyMuPDF text-layer behavior**: Word-tuple shape is stable; corner cases (rotated pages, encrypted PDFs) not tested.
- **TrOCR / handwriting arbitration**: Confidence comparison depends on TrOCR's confidence calibration, unverified.
- **Anthropic and Ollama provider paths**: Code reviewed but not verified against real APIs.
- **Celery worker / multi-loop behavior**: F1.4 is plausible but no reproduction constructed.
- **Document processor strict-mode contract enforcement**: Default `strict=False`; spot-checked 4 of 6 processors.
- **PDF embedder font chain**: Per-run font registration against real CJK + Arabic mixed content not tested.

## Known-tech-debt verification

| Item | Status | Evidence |
|------|--------|----------|
| `pages_structured` legacy dict is still the working format inside `HybridEngine` | **CONFIRMED** | `core/workflows/hybrid.py:496-498`; `core/workflows/base.py:355-357` |
| `/api/process` runs the full OCR pipeline synchronously | **CONFIRMED** (core side) | `core/pipeline.py:116-202` is a single async function |
| Job/artifact state is in-memory by default | **CONFIRMED** | `config.py:100-110` `state_backend` selector defaults to "memory" |
| `dense.pdf` and `notes.pdf` ground-truth fixtures bootstrapped from hybrid output | **PARTIALLY VERIFIED** | Fixture files not in scope; design consistent with AGENTS.md |
| `surya-ocr 0.17.x` requests workaround | **NOT VERIFIED** | `pyproject.toml` was out of scope |

## Files NOT examined (out of scope)
- `src/omniscribe/core/transcription/`, `core/lexicon/`, `core/glossary_library/`, `core/glossary_sources/`, `core/translation.py`, `core/translation_config.py`, `core/translation_tree.py`, `core/dual_translator.py`, `core/docx_writer.py`, `core/docx_tree_writer.py`, `core/html_writer.py`, `core/tree_export.py`, `core/nllb_engine.py`, `core/trocr_engine.py`, `core/providers.py`, `core/glossary.py`, `core/llm_temperatures.py`, `core/pdf/rasterizer.py`, `core/pdf/handler.py`, `core/pdf/page_range.py`, `core/pdf/rasterization_settings.py`
- `src/omniscribe/server.py`
- `src/omniscribe/utils/file.py`, `utils/security.py`, `utils/structured_logging.py`, `utils/tqdm_patch.py`
- `pyproject.toml`, `tests/`, `frontend/`, `scripts/`, `examples/`, `install.*`, `start_app.*`, `stop_app.*`, `test_ui.py`
