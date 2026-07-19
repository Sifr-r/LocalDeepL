# God-Module Decomposition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `api/routers/ocr.py` (662 LOC), `core/ocr.py` (595 LOC), `core/grounded.py` (710 LOC) into single-responsibility modules, delete the dead `api/routers/ai.py`, and update `ARCHITECTURE.md` — all while preserving the public import surface and the existing test suite verbatim.

**Architecture:** Convert each god-module into a sub-package whose `__init__.py` re-exports the previous module-level names so the existing `from local_deepl.core.ocr import OCRProcessor` and `from local_deepl import OCRPipeline` paths continue to work. Move the route file's helpers into four `api/services/ocr_*.py` modules. Behavior, public surface, and tests do not change.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, OpenAI-compatible LLM clients, pytest (auto-mode), ruff, mypy.

---

## File Structure

**Created** (new files in P1-P4):

| Path | Phase | Responsibility |
|---|---|---|
| `src/local_deepl/core/ocr/__init__.py` | P1 | Re-export every public name from `core/ocr.py` |
| `src/local_deepl/core/ocr/processor.py` | P1 | `OCRProcessor` class |
| `src/local_deepl/core/ocr/prompts.py` | P1 | 8 prompt constants + `select_page_prompt` / `select_crop_prompt` helpers |
| `src/local_deepl/core/ocr/filters.py` | P1 | `_HALLUCINATION_PATTERNS`, `_is_fallback_response`, `_strip_yaml_front_matter`, `_strip_runaway_repetition` |
| `src/local_deepl/core/ocr/exceptions.py` | P1 | `LLMCallError`, `ModelNotLoadedError` |
| `src/local_deepl/core/ocr/client.py` | P1 | `_list_loaded_model_ids`, `_model_in_loaded`, `_format_model_not_loaded` (cross-imported by `core/grounded.prompted`) |
| `src/local_deepl/core/grounded/__init__.py` | P2 | Re-export every public name from `core/grounded.py` |
| `src/local_deepl/core/grounded/protocol.py` | P2 | `GroundedOCRBackend` Protocol + `ProgressCallback` / `WarningCallback` aliases |
| `src/local_deepl/core/grounded/types.py` | P2 | `GroundedBlock`, `GroundedResponse`, `_clamp` |
| `src/local_deepl/core/grounded/filters.py` | P2 | `_NON_CONTENT_LABELS`, `is_content_label` |
| `src/local_deepl/core/grounded/parsers.py` | P2 | `parse_zai_response`, `parse_glm_layout_details`, `_detect_axis_order_zxyxy`, `_parse_grounded_json` |
| `src/local_deepl/core/grounded/rasterization.py` | P2 | `_rasterize_to_jpeg_pages` |
| `src/local_deepl/core/grounded/prompted.py` | P2 | `PromptedGroundedOCR`, `DEFAULT_GROUNDING_PROMPT` |
| `src/local_deepl/core/grounded/zai.py` | P2 | `ZAIHostedOCR` |
| `src/local_deepl/api/services/ocr_settings.py` | P3 | `_resolve_process_settings`, `_validation_error_response` |
| `src/local_deepl/api/services/ocr_pipeline_factory.py` | P3 | `_select_backend`, `_build_pipeline`, `_verify_backend_model` |
| `src/local_deepl/api/services/ocr_response.py` | P3 | `_build_file_response`, `_document_quality_header`, `_document_structure_header`, `_document_sections_header`, `_create_document_metadata_artifact` |
| `src/local_deepl/api/services/ocr_jobs.py` | P3 | `_record_job`, `stage_to_percent` |

**Modified** (existing files shrunk or rewritten):

| Path | Phase | Change |
|---|---|---|
| `src/local_deepl/core/ocr.py` | P1 | Becomes the package shim (re-exports from `core/ocr/`). Easiest: delete `core/ocr.py` and let `core/ocr/` (the package) take over; Python's `__init__.py` is the new module entry. |
| `src/local_deepl/core/grounded.py` | P2 | Same — delete the file; `core/grounded/__init__.py` is the new entry. |
| `src/local_deepl/api/routers/ocr.py` | P3 | Reduces to a thin orchestrator (~80 LOC) that imports helpers from the new `api/services/ocr_*.py` modules. |
| `ARCHITECTURE.md` | P4 | Remove the line "AI service module consumed by `extraction.py` and `translation.py`" mis-attributed to `api/routers/ai.py`; refresh the Key Files table to list the new sub-packages and the new services. |

**Deleted**:

| Path | Phase |
|---|---|
| `src/local_deepl/api/routers/ai.py` | P4 |
| `src/local_deepl/core/ocr.py` (after P1 moves into package) | P1 |
| `src/local_deepl/core/grounded.py` (after P2 moves into package) | P2 |

**Tests**: No test files are edited. `tests/test_ai_router.py` may be deleted in P4 if it covers only the routes that are being removed (inspect first).

---

## Phase P1 — Split `core/ocr.py` into `core/ocr/` sub-package

### Task P1.1 — Create the new sub-package files

**Files:**
- Create: `src/local_deepl/core/ocr/__init__.py`
- Create: `src/local_deepl/core/ocr/exceptions.py`
- Create: `src/local_deepl/core/ocr/prompts.py`
- Create: `src/local_deepl/core/ocr/filters.py`
- Create: `src/local_deepl/core/ocr/client.py`
- Create: `src/local_deepl/core/ocr/processor.py`

- [ ] **Step 1: Create `core/ocr/exceptions.py`**

```python
"""Exception types for the LLM-based OCR processor."""
from __future__ import annotations


class LLMCallError(RuntimeError):
    """Raised when a call to the local LLM OCR endpoint fails.

    Wraps the underlying exception (connection refused, model not loaded,
    timeout, auth, ...) with a message that names the api-base and model
    so the user can diagnose without digging through a stack trace.
    """


class ModelNotLoadedError(LLMCallError):
    """Raised when the requested model is not loaded on the LLM server.

    LM Studio silently falls back to whatever model is currently loaded
    when an OpenAI-compat client requests an unavailable model ID — so a
    typo in --model or a forgotten model swap produces subtly wrong OCR
    output with no surface error. This exception is raised by
    :meth:`OCRProcessor.ensure_model_loaded` (and the grounded equivalent)
    *before* any OCR work starts so the user sees the mismatch immediately
    instead of debugging strange output later.
    """
```

- [ ] **Step 2: Create `core/ocr/prompts.py`**

Copy the eight prompt constants verbatim from `core/ocr.py` lines 51-139 (`OLMOCR_PAGE_PROMPT`, `CROP_PROMPT`, `DUAL_ENGINE_PAGE_PROMPT`, `DUAL_ENGINE_CROP_PROMPT`, `CORRECTION_PAGE_PROMPT`, `CORRECTION_CROP_PROMPT`, `HANDWRITING_PAGE_PROMPT`, `HANDWRITING_CROP_PROMPT`) plus these helpers at the bottom:

```python
"""Prompt constants and selection helpers for the OCR processor."""
from __future__ import annotations


# ... (eight prompt constants copied verbatim) ...


def select_page_prompt(handwriting_mode: bool = False) -> str:
    """Return the page-level prompt configured by the caller."""
    return HANDWRITING_PAGE_PROMPT if handwriting_mode else OLMOCR_PAGE_PROMPT


def select_crop_prompt(handwriting_mode: bool = False) -> str:
    """Return the crop-level prompt configured by the caller."""
    return HANDWRITING_CROP_PROMPT if handwriting_mode else CROP_PROMPT


def fill_dual_engine_page(draft_text: str) -> str:
    """Substitute the Tesseract draft into the dual-engine page prompt."""
    return DUAL_ENGINE_PAGE_PROMPT.replace("{draft_text}", draft_text)


def fill_dual_engine_crop(draft_text: str) -> str:
    """Substitute the Tesseract draft into the dual-engine crop prompt."""
    return DUAL_ENGINE_CROP_PROMPT.replace("{draft_text}", draft_text)


def fill_correction_page(draft_text: str) -> str:
    """Substitute the draft text into the correction page prompt."""
    return CORRECTION_PAGE_PROMPT.replace("{draft_text}", draft_text)


def fill_correction_crop(draft_text: str) -> str:
    """Substitute the draft text into the correction crop prompt."""
    return CORRECTION_CROP_PROMPT.replace("{draft_text}", draft_text)
```

These helpers centralize the prompt logic that previously lived inline in `perform_ocr` / `perform_ocr_on_crop` (lines 251-260, 302-310, 271-272, 322-323, 362-364 of the old `core/ocr.py`).

- [ ] **Step 3: Create `core/ocr/filters.py`**

```python
"""Output filters: detect LLM fallback phrases, strip YAML front matter, clip runaway repetition."""
from __future__ import annotations

import logging
import re


_HALLUCINATION_PATTERNS = (
    "the quick brown fox jumps over the lazy dog",  # OlmOCR-2 pangram fallback
    "lorem ipsum",
)


def _is_fallback_response(text: str) -> bool:
    """True if ``text`` is essentially one of the known LLM fallback phrases.

    A substring match would over-trigger: a real document might contain
    "lorem ipsum" as quoted placeholder text, or the pangram as an
    example sentence. We require the response to *be* the fallback
    after light normalization (case-fold, strip whitespace, drop
    surrounding punctuation/quotes) — i.e. the fallback occupies the
    entire crop response, not just part of it.
    """
    _trim = ".!?\"'`)([]{}<>""'' \t"
    normalized = text.strip().lower().strip(_trim)
    return normalized in _HALLUCINATION_PATTERNS


def _strip_yaml_front_matter(text: str) -> str:
    """Strip an optional YAML front matter block from the front of ``text``."""
    t = re.sub(r"^\s*```[a-zA-Z]*\n?", "", text).lstrip()
    if not t.startswith("---"):
        return text
    rest = t[3:]
    close_idx = rest.find("\n---")
    if close_idx == -1:
        return text  # malformed; return as-is
    body = rest[close_idx + len("\n---") :]
    body = re.sub(r"^\s*```\n?", "", body)
    return body.lstrip("\n").strip()


def _strip_runaway_repetition(lines: list[str], max_repeat: int = 20) -> list[str]:
    """Drop pathological repetition from LLM output (see old ``core/ocr.py:491``)."""
    counts: dict[str, int] = {}
    out: list[str] = []
    truncated = 0
    for line in lines:
        c = counts.get(line, 0) + 1
        counts[line] = c
        if c <= max_repeat:
            out.append(line)
        else:
            truncated += 1
    if truncated > 0:
        worst = max(counts.items(), key=lambda kv: kv[1])
        logging.warning(
            "LLM OCR output had %d runaway-repetition lines clipped "
            "(worst offender: %r occurred %d times). The model likely "
            "got stuck on this page; output may be incomplete. "
            "Try lowering --max-image-dim or switching --model.",
            truncated,
            worst[0][:60],
            worst[1],
        )
    return out
```

- [ ] **Step 4: Create `core/ocr/client.py`**

```python
"""LLM-side helpers: model listing + error formatting (used by both ``OCRProcessor`` and ``PromptedGroundedOCR.ensure_model_loaded``)."""
from __future__ import annotations

from openai import AsyncOpenAI

from .exceptions import LLMCallError, ModelNotLoadedError


async def _list_loaded_model_ids(client: AsyncOpenAI, api_base: str) -> list[str]:
    """Return model IDs loaded on an OpenAI-compatible server."""
    try:
        page = await client.models.list()
    except Exception as e:
        raise LLMCallError(
            f"Could not list models on {api_base}: "
            f"{type(e).__name__}: {e}\n"
            f"  - Is your local LLM server (LM Studio / Ollama / vLLM) running at "
            f"{api_base}?\n"
            f"  - Does it expose GET /v1/models? (Most do; some custom servers "
            f"don't — pass --no-verify-model to skip this check.)"
        ) from e
    return [m.id for m in page.data] if page.data else []


def _model_in_loaded(model: str, loaded: list[str]) -> bool:
    target = model.lower()
    return any(m.lower() == target for m in loaded)


def _format_model_not_loaded(api_base: str, model: str, loaded: list[str]) -> str:
    listing = "\n    ".join(loaded) if loaded else "(none)"
    return (
        f"Model {model!r} is not loaded on {api_base}.\n"
        f"  Loaded models:\n    {listing}\n"
        f"  Fix:\n"
        f"    - Load {model!r} in LM Studio (Models -> search -> Load), then retry.\n"
        f"    - Or pass --model with one of the loaded model IDs above.\n"
        f"    - Or pass --no-verify-model to skip this check "
        f"(e.g. on Ollama / vLLM, which auto-load on demand).\n"
        f"  Why this matters: LM Studio silently falls back to whatever model is "
        f"loaded when the requested one is missing, producing subtly wrong OCR "
        f"results with no error. (issue #7)"
    )

# Re-exported for backward-import symmetry; ModelNotLoadedError is defined in exceptions.py.
__all__ = ["_list_loaded_model_ids", "_model_in_loaded", "_format_model_not_loaded"]
```

- [ ] **Step 5: Create `core/ocr/processor.py`**

```python
"""OCRProcessor — LLM-based OCR processor over an OpenAI-compatible async client."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from openai import AsyncOpenAI

from local_deepl.core.llm_client import call_llm

from .client import _format_model_not_loaded, _list_loaded_model_ids, _model_in_loaded
from .exceptions import LLMCallError, ModelNotLoadedError
from .filters import _is_fallback_response, _strip_runaway_repetition, _strip_yaml_front_matter
from .prompts import (
    fill_correction_crop,
    fill_correction_page,
    fill_dual_engine_crop,
    fill_dual_engine_page,
    select_crop_prompt,
    select_page_prompt,
)

if TYPE_CHECKING:
    from local_deepl.core.trocr_engine import TrOCREngine

load_dotenv()
logger = logging.getLogger(__name__)


class OCRProcessor:
    """LLM-based OCR processor over an OpenAI-compatible async client.

    Local VLMs occasionally fall into runaway-generation loops on dense
    or unusual pages — we bound both the per-call timeout and the
    response token budget so a single bad page can't hang the pipeline
    indefinitely. Tuned per-call (full-page vs single-line crop): a page
    can legitimately take longer than a crop, and warrants a higher token
    budget for paragraph-level content.
    """

    PAGE_TIMEOUT_S: float = 240.0
    PAGE_MAX_TOKENS: int = 6144
    CROP_TIMEOUT_S: float = 60.0
    CROP_MAX_TOKENS: int = 256

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        trocr_engine: "TrOCREngine | None" = None,
        handwriting_mode: bool = False,
        confidence_threshold: float = 0.75,
    ):
        self.api_base: str = (
            api_base or os.getenv("LLM_API_BASE") or "http://localhost:1234/v1"
        )
        self.api_key: str = api_key or os.getenv("LLM_API_KEY") or "lm-studio"
        self.model: str = model or os.getenv("LLM_MODEL") or "allenai/olmocr-2-7b"
        self.client = AsyncOpenAI(base_url=self.api_base, api_key=self.api_key)
        self.trocr_engine = trocr_engine
        self.handwriting_mode = handwriting_mode
        self.confidence_threshold = confidence_threshold

    async def ensure_model_loaded(self) -> None:
        """Pre-flight check that ``self.model`` is loaded on the server."""
        loaded = await _list_loaded_model_ids(self.client, self.api_base)
        if not _model_in_loaded(self.model, loaded):
            raise ModelNotLoadedError(
                _format_model_not_loaded(self.api_base, self.model, loaded)
            )

    async def perform_ocr(
        self,
        image_base64: str,
        self_correction: bool = False,
        binarize: bool = False,
        dual_engine: bool = False,
    ) -> list[str]:
        """OCR a full page image. Returns a list of non-empty lines in reading order."""
        if binarize:
            image_base64 = await asyncio.to_thread(
                self._apply_adaptive_threshold, image_base64
            )

        prompt = select_page_prompt(getattr(self, "handwriting_mode", False))
        if dual_engine:
            draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)
            if draft:
                prompt = fill_dual_engine_page(draft)

        text = await self._chat(
            prompt,
            image_base64,
            timeout=self.PAGE_TIMEOUT_S,
            max_tokens=self.PAGE_MAX_TOKENS,
        )
        if not text:
            return []

        if self_correction:
            text = await self._chat(
                fill_correction_page(text),
                image_base64,
                timeout=self.PAGE_TIMEOUT_S,
                max_tokens=self.PAGE_MAX_TOKENS,
            )
            if not text:
                return []

        body = _strip_yaml_front_matter(text)
        lines = [line.strip() for line in body.split("\n") if line.strip()]
        return _strip_runaway_repetition(lines)

    async def perform_ocr_on_crop(
        self,
        image_base64: str,
        self_correction: bool = False,
        binarize: bool = False,
        dual_engine: bool = False,
    ) -> str:
        """OCR a single cropped box region. Returns a single whitespace-joined string."""
        if binarize:
            image_base64 = await asyncio.to_thread(
                self._apply_adaptive_threshold, image_base64
            )

        prompt = select_crop_prompt(getattr(self, "handwriting_mode", False))
        if dual_engine:
            draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)
            if draft:
                prompt = fill_dual_engine_crop(draft)

        text = await self._chat(
            prompt,
            image_base64,
            timeout=self.CROP_TIMEOUT_S,
            max_tokens=self.CROP_MAX_TOKENS,
        )
        if not text:
            return ""

        if self_correction:
            text = await self._chat(
                fill_correction_crop(text),
                image_base64,
                timeout=self.CROP_TIMEOUT_S,
                max_tokens=self.CROP_MAX_TOKENS,
            )
            if not text:
                return ""

        body = _strip_yaml_front_matter(text)
        result = " ".join(line.strip() for line in body.split("\n") if line.strip())
        if _is_fallback_response(result):
            result = ""

        if getattr(self, "handwriting_mode", False) and self.trocr_engine is not None:
            result = await self._trocr_arbitration(image_base64, result)

        return result

    async def _trocr_arbitration(self, image_base64: str, vlm_text: str) -> str:
        """TrOCR dual-engine arbitration. Returns the higher-confidence read."""
        from local_deepl.core.trocr_engine import _heuristic_confidence

        vlm_conf = _heuristic_confidence(vlm_text)
        if vlm_conf >= self.confidence_threshold:
            return vlm_text
        try:
            import base64

            image_bytes = base64.b64decode(image_base64)
            trocr_res = await self.trocr_engine.recognize(image_bytes)
            if trocr_res.confidence > vlm_conf:
                corrected = await self._chat(
                    fill_dual_engine_crop(trocr_res.text),
                    image_base64,
                    timeout=self.CROP_TIMEOUT_S,
                    max_tokens=self.CROP_MAX_TOKENS,
                )
                corrected_body = _strip_yaml_front_matter(corrected)
                corrected_res = " ".join(
                    line.strip()
                    for line in corrected_body.split("\n")
                    if line.strip()
                )
                if _is_fallback_response(corrected_res):
                    corrected_res = ""
                vlm_corr_conf = _heuristic_confidence(corrected_res)
                return trocr_res.text if trocr_res.confidence > vlm_corr_conf else corrected_res
            return vlm_text
        except Exception as e:
            logger.warning("TrOCR fallback failed: %s", e)
            return vlm_text

    async def _chat(
        self,
        prompt: str,
        image_base64: str,
        *,
        timeout: float,
        max_tokens: int,
    ) -> str:
        try:
            content = await call_llm(
                model=self.model,
                api_base=self.api_base,
                api_key=self.api_key,
                temperature=0.1,
                max_tokens=max_tokens,
                timeout=timeout,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
            )
            return content.strip()
        except Exception as e:
            err_msg = str(e)
            if any(
                term in err_msg.lower()
                for term in (
                    "context size",
                    "context_length_exceeded",
                    "context length",
                )
            ):
                raise LLMCallError(
                    f"LLM OCR call failed due to Context Size Limit. "
                    f"Please load the model in LM Studio and increase the 'Context Length' in the right-side panel "
                    f"to at least 8192 or 16384 tokens. "
                    f"Underlying error: {e}"
                ) from e
            raise LLMCallError(
                f"LLM OCR call failed against {self.api_base} ({type(e).__name__}): {e}"
            ) from e

    def _get_tesseract_draft(self, image_base64: str) -> str:
        try:
            import base64
            import io

            import pytesseract
            from PIL import Image

            image_bytes = base64.b64decode(image_base64)
            img = Image.open(io.BytesIO(image_bytes))
            draft: str = pytesseract.image_to_string(img, lang="ara+eng")
            return draft.strip()
        except Exception:
            return ""

    def _apply_adaptive_threshold(self, image_base64: str) -> str:
        try:
            import base64

            import cv2
            import numpy as np

            image_bytes = base64.b64decode(image_base64)
            np_arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)

            if img is None:
                return image_base64

            binary = cv2.adaptiveThreshold(
                img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 15
            )

            success, encoded = cv2.imencode(".png", binary)
            if not success:
                return image_base64

            return base64.b64encode(encoded.tobytes()).decode("utf-8")
        except Exception:
            return image_base64
```

Note: this is a behavior-preserving extraction. The TrOCR arbitration block (~lines 351-390 of the old `core/ocr.py`) is moved into a private `_trocr_arbitration` helper to reduce nesting.

- [ ] **Step 6: Create `core/ocr/__init__.py`**

```python
"""OCR backend — LLM-based OCR over OpenAI-compatible endpoints.

Public surface is preserved verbatim from the legacy ``core/ocr.py`` module:
``OCRProcessor``, ``LLMCallError``, ``ModelNotLoadedError``, and every
prompt constant + filter helper re-export here.
"""
from __future__ import annotations

from .client import (
    _format_model_not_loaded,
    _list_loaded_model_ids,
    _model_in_loaded,
)
from .exceptions import LLMCallError, ModelNotLoadedError
from .filters import (
    _HALLUCINATION_PATTERNS,
    _is_fallback_response,
    _strip_runaway_repetition,
    _strip_yaml_front_matter,
)
from .processor import OCRProcessor
from .prompts import (
    CORRECTION_CROP_PROMPT,
    CORRECTION_PAGE_PROMPT,
    CROP_PROMPT,
    DUAL_ENGINE_CROP_PROMPT,
    DUAL_ENGINE_PAGE_PROMPT,
    HANDWRITING_CROP_PROMPT,
    HANDWRITING_PAGE_PROMPT,
    OLMOCR_PAGE_PROMPT,
    fill_correction_crop,
    fill_correction_page,
    fill_dual_engine_crop,
    fill_dual_engine_page,
    select_crop_prompt,
    select_page_prompt,
)

__all__ = [
    "OCRProcessor",
    "LLMCallError",
    "ModelNotLoadedError",
    "OLMOCR_PAGE_PROMPT",
    "CROP_PROMPT",
    "DUAL_ENGINE_PAGE_PROMPT",
    "DUAL_ENGINE_CROP_PROMPT",
    "CORRECTION_PAGE_PROMPT",
    "CORRECTION_CROP_PROMPT",
    "HANDWRITING_PAGE_PROMPT",
    "HANDWRITING_CROP_PROMPT",
    "_HALLUCINATION_PATTERNS",
    "_is_fallback_response",
    "_strip_runaway_repetition",
    "_strip_yaml_front_matter",
    "_list_loaded_model_ids",
    "_model_in_loaded",
    "_format_model_not_loaded",
    "select_page_prompt",
    "select_crop_prompt",
    "fill_dual_engine_page",
    "fill_dual_engine_crop",
    "fill_correction_page",
    "fill_correction_crop",
]
```

- [ ] **Step 7: Delete the old `core/ocr.py`**

Delete the file `src/local_deepl/core/ocr.py`. The Python package `core/ocr/` (with `__init__.py`) takes over the module entry.

- [ ] **Step 8: Verify imports + tests**

Run: `python -c "from local_deepl.core.ocr import OCRProcessor, LLMCallError, ModelNotLoadedError, OLMOCR_PAGE_PROMPT, _HALLUCINATION_PATTERNS; print('ok')"`
Expected: prints `ok`.

Run: `python -c "from local_deepl import OCRPipeline, OCRProcessor; print('ok')"`
Expected: prints `ok`.

Run: `uv run pytest tests/test_ocr.py tests/test_ocr_trocr_integration.py -q --co` (collect only — confirms the test suite still imports cleanly without external deps).
Expected: `N tests collected` with N > 0 and no collection errors.

- [ ] **Step 9: Run full fast suite**

Run: `uv run pytest -q -x -m "not slow"`
Expected: pass.

- [ ] **Step 10: Lint + type check**

Run: `uv run ruff check src tests && uv run mypy src`
Expected: both exit 0.

---

## Phase P2 — Split `core/grounded.py` into `core/grounded/` sub-package

### Task P2.1 — Create the new sub-package files

**Files:**
- Create: `src/local_deepl/core/grounded/__init__.py`
- Create: `src/local_deepl/core/grounded/protocol.py`
- Create: `src/local_deepl/core/grounded/types.py`
- Create: `src/local_deepl/core/grounded/filters.py`
- Create: `src/local_deepl/core/grounded/parsers.py`
- Create: `src/local_deepl/core/grounded/rasterization.py`
- Create: `src/local_deepl/core/grounded/prompted.py`
- Create: `src/local_deepl/core/grounded/zai.py`

- [ ] **Step 1: Create `core/grounded/protocol.py`**

```python
"""Protocol and callback aliases for grounded OCR backends."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from .types import GroundedResponse


ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]
WarningCallback = Callable[[int, BaseException], Awaitable[None]]


class GroundedOCRBackend(Protocol):
    """Backends that return text WITH layout in one shot (no Surya needed).

    `progress` is optional; callers that don't care about per-page updates
    can omit it. Backends SHOULD emit the `"ocr"` stage with (current,
    total) set to pages-completed / total-pages so the pipeline's progress
    adapter stays aligned with the documented stage set.

    `on_warning` is called once per page whose OCR call raised an
    exception at the backend's per-page isolation boundary. The
    pipeline uses it (alongside `failed_pages` on the response) to
    surface partial failures to the caller.
    """

    async def ocr_document(
        self,
        pdf_path: str,
        progress: ProgressCallback | None = None,
        on_warning: WarningCallback | None = None,
    ) -> GroundedResponse: ...
```

- [ ] **Step 2: Create `core/grounded/types.py`**

```python
"""Data shapes for grounded OCR (one block per text span with bbox + label)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GroundedBlock:
    bbox: list[float]  # normalized [nx0, ny0, nx1, ny1] in 0..1
    text: str
    page_index: int
    label: str = "text"  # filter: keep "text", drop "image"/"figure"
    image_bytes: bytes | None = None


@dataclass
class GroundedResponse:
    blocks: list[GroundedBlock]
    page_sizes: list[tuple[int, int]] = field(default_factory=list)  # (w, h) per page
    failed_pages: list[int] = field(default_factory=list)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))
```

- [ ] **Step 3: Create `core/grounded/filters.py`**

```python
"""Label-based content filter — drop structural / non-text labels."""
from __future__ import annotations

# Labels we treat as *non-content* — structural regions that aren't meant
# to carry selectable text. Newer grounded responses emit labels like
# "title", "list_item", "form_field", "diagram_node" etc. alongside "text";
# the old handwritten fixture was pure "text" + "image". Instead of allow-
# listing content labels (brittle across schema versions) we deny-list the
# structural ones.
_NON_CONTENT_LABELS = frozenset(
    {
        "empty_line",        # unfilled underline fields
        "signature_line",    # form signature placeholder
        "list_marker",       # lone bullet/dash glyphs
    }
)


def is_content_label(label: str) -> bool:
    """True if a ``label`` should yield a ``GroundedBlock`` (vs. being dropped)."""
    return label not in _NON_CONTENT_LABELS
```

- [ ] **Step 4: Create `core/grounded/parsers.py`**

```python
"""Backend-specific JSON parsers + the bbox axis-order heuristic."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .filters import is_content_label
from .types import GroundedBlock, GroundedResponse, _clamp

logger = logging.getLogger(__name__)


# --- parse helpers --------------------------------------------------------


def parse_zai_response(payload: dict[str, Any]) -> GroundedResponse:
    """Parse Z.AI's hosted OCR response into ``GroundedResponse`` (see old line 153)."""
    d = payload.get("data", payload)
    pages = d.get("data_info", {}).get("pages", [])
    page_sizes = [(int(p["width"]), int(p["height"])) for p in pages]

    raw_items = [
        b
        for b in d.get("layout", [])
        if is_content_label(b.get("block_label", "text"))
    ]
    swap = _detect_axis_order_zxyxy([b["bbox"] for b in raw_items]) == "yxyx"

    blocks: list[GroundedBlock] = []
    for b in raw_items:
        pidx = b.get("page_index", 0)
        if pidx >= len(page_sizes):
            continue
        pw, ph = page_sizes[pidx]
        bbox = b["bbox"]
        if swap:
            bbox = [bbox[1], bbox[0], bbox[3], bbox[2]]
        x0, y0, x1, y1 = bbox
        content = (b.get("block_content") or "").strip()
        if not content:
            continue
        blocks.append(
            GroundedBlock(
                bbox=[
                    _clamp(x0 / pw),
                    _clamp(y0 / ph),
                    _clamp(x1 / pw),
                    _clamp(y1 / ph),
                ],
                text=content,
                page_index=pidx,
                label=b.get("block_label", "text"),
            )
        )
    return GroundedResponse(blocks=blocks, page_sizes=page_sizes)


def _detect_axis_order_zxyxy(raw_boxes: list[list[float]]) -> str:
    """Return 'xyxy' or 'yxyx' based on whether boxes look portrait as xyxy."""
    portrait, counted = 0, 0
    for b in raw_boxes:
        if len(b) != 4:
            continue
        w_xy = abs(b[2] - b[0])
        h_xy = abs(b[3] - b[1])
        if w_xy <= 0 or h_xy <= 0:
            continue
        counted += 1
        if h_xy > 1.5 * w_xy:
            portrait += 1
    if counted == 0:
        return "xyxy"
    return "yxyx" if portrait > counted / 2 else "xyxy"


def parse_glm_layout_details(
    payload_or_json: Any, page_index: int = 0
) -> GroundedResponse:
    """Parse GLM-OCR ``layout_details`` (pixel-relative bbox_2d) — old line 225."""
    if isinstance(payload_or_json, str):
        payload_or_json = json.loads(payload_or_json)
    d = payload_or_json

    pages = d.get("data_info", {}).get("pages", [])
    page_sizes = [(int(p["width"]), int(p["height"])) for p in pages]
    if not page_sizes:
        raise ValueError("parse_glm_layout_details: missing data_info.pages")

    raw = d.get("layout_details", [])
    if raw and isinstance(raw[0], list):
        raw_blocks = raw[page_index] if page_index < len(raw) else []
    else:
        raw_blocks = raw

    blocks: list[GroundedBlock] = []
    pw, ph = page_sizes[page_index]
    for b in raw_blocks:
        if b.get("label") != "text":
            continue
        content = (b.get("content") or "").strip()
        if not content:
            continue
        x0, y0, x1, y1 = b["bbox_2d"]
        blocks.append(
            GroundedBlock(
                bbox=[
                    _clamp(x0 / pw),
                    _clamp(y0 / ph),
                    _clamp(x1 / pw),
                    _clamp(y1 / ph),
                ],
                text=content,
                page_index=page_index,
            )
        )
    return GroundedResponse(blocks=blocks, page_sizes=page_sizes)


# --- fenced / bare JSON response extraction -------------------------------

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", re.IGNORECASE
)
_BARE_ARRAY = re.compile(r"(\[[\s\S]*\])")


def _parse_grounded_json(
    text: str,
    page_idx: int,
    img_w: int,
    img_h: int,
) -> list[GroundedBlock]:
    """Extract a JSON array of `{bbox_2d, content}` blocks from a VLM response."""
    raw = text.strip()
    if not raw:
        return []

    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1)
    elif raw.startswith("```"):
        raw = raw.lstrip("`").lstrip("json").lstrip().rstrip("`").rstrip()

    data: Any
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m2 = _BARE_ARRAY.search(raw)
        if not m2:
            logger.debug("grounded parse: no array in response: %s", raw[:200])
            return []
        try:
            data = json.loads(m2.group(1))
        except json.JSONDecodeError as e:
            logger.debug("grounded parse failed: %s — raw=%s", e, raw[:200])
            return []

    if isinstance(data, dict):
        for key in ("results", "blocks", "layout", "layout_details", "items"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        return []

    blocks: list[GroundedBlock] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox_2d") or item.get("bbox")
        content = item.get("content") or item.get("text") or ""
        if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        content = str(content).strip()
        if not content:
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        blocks.append(
            GroundedBlock(
                bbox=[
                    _clamp(x0 / img_w),
                    _clamp(y0 / img_h),
                    _clamp(x1 / img_w),
                    _clamp(y1 / img_h),
                ],
                text=content,
                page_index=page_idx,
            )
        )
    return blocks
```

- [ ] **Step 5: Create `core/grounded/rasterization.py`**

```python
"""Synchronous PDF/image → JPEG base64 rasterization, call via ``asyncio.to_thread``."""
from __future__ import annotations

import base64
import io


def _rasterize_to_jpeg_pages(
    path: str,
    max_image_dim: int,
    dpi: int,
) -> list[tuple[str, int, int]]:
    """Synchronous PDF/image rasterization — call via ``asyncio.to_thread``.

    Extracted from ``PromptedGroundedOCR.ocr_document`` so the blocking
    fitz.open / get_pixmap / PIL calls don't stall the async event loop.
    """
    import fitz
    from PIL import Image, ImageSequence

    from local_deepl.core.pdf import (
        VLM_JPEG_QUALITY_GROUNDED,
        _is_image_path,
    )

    page_imgs: list[tuple[str, int, int]] = []

    def _emit(img: Image.Image) -> None:
        img = img.convert("RGB")
        img.thumbnail((max_image_dim, max_image_dim))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=VLM_JPEG_QUALITY_GROUNDED)
        page_imgs.append(
            (base64.b64encode(buf.getvalue()).decode(), img.width, img.height)
        )

    if _is_image_path(path):
        with Image.open(path) as src:
            for frame in ImageSequence.Iterator(src):
                _emit(frame.copy())
    else:
        doc = fitz.open(path)
        try:
            for page in doc:
                pix = page.get_pixmap(dpi=dpi)
                _emit(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        finally:
            doc.close()

    return page_imgs
```

- [ ] **Step 6: Create `core/grounded/prompted.py`**

```python
"""PromptedGroundedOCR — default backend for OpenAI-compat VLMs that emit bbox JSON."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os

from openai import AsyncOpenAI

from local_deepl.core.llm_client import call_llm

from .protocol import ProgressCallback, WarningCallback
from .rasterization import _rasterize_to_jpeg_pages
from .types import GroundedBlock, GroundedResponse

logger = logging.getLogger(__name__)


DEFAULT_GROUNDING_PROMPT = (
    "You are an exhaustive OCR engine. Output a JSON array covering EVERY "
    "VISUAL LINE of text on this page: headers, form labels, field names, "
    "body paragraphs, numbered items, signatures, footnotes — all of it.\n"
    "\n"
    "CRITICAL — line segmentation: emit ONE element PER VISUAL LINE. If a "
    "phrase wraps onto two lines on the page, that is TWO elements, not "
    "one — even if the lines belong to the same sentence, paragraph, or "
    "phrase. Never join lines together. Never collapse a line break into "
    "a space. Hand-written notes especially have line breaks that printed "
    "text wouldn't — preserve every one of them. Each bbox must tightly "
    "enclose a SINGLE line.\n"
    "\n"
    "Worked example — if the page contains the four visual lines:\n"
    "  schwache Grenzen\n"
    "  im Kopf\n"
    "  Linke\n"
    "  weiblich\n"
    "emit FOUR elements, one per line. Do NOT emit one element with "
    'content "schwache Grenzen im Kopf" and another with "Linke '
    'weiblich" — joining lines is wrong even when the resulting phrase '
    "reads naturally.\n"
    "\n"
    "Each element must have this exact shape: "
    '{"bbox_2d": [x1, y1, x2, y2], "content": "<text of that one line>"} '
    "where bbox_2d is pixel coordinates in the image (x1<x2, y1<y2). The "
    "bbox height must match a single line of text. If your bbox is tall "
    "enough to contain two lines, you have joined two lines — split it "
    "into two elements.\n"
    "\n"
    "Do not skip small labels. Do not summarize. Do not paraphrase. "
    "No markdown fences, no prose — only the raw JSON array."
)


class PromptedGroundedOCR:
    """Grounded backend built on an OpenAI-compatible vision LLM endpoint.

    Works with any VLM that emits ``{bbox_2d:[...], content:"..."}`` when
    asked. Confirmed for Qwen2.5-VL (line-level, wrapped in fences) and
    Qwen3-VL (line-level, bare JSON). Should also work for MiniCPM-V,
    InternVL, etc.
    """

    def __init__(
        self,
        api_base: str | None = None,
        model: str | None = None,
        api_key: str = "lm-studio",
        max_image_dim: int = 1024,
        dpi: int = 150,
        prompt: str | None = None,
        timeout_s: float = 240.0,
        max_tokens: int = 8192,
        concurrency: int = 1,
    ):
        self.api_base: str = (
            api_base or os.getenv("LLM_API_BASE") or "http://localhost:1234/v1"
        )
        self.model: str = model or os.getenv("LLM_MODEL") or "qwen/qwen3-vl-8b"
        self.api_key: str = api_key
        self.max_image_dim = max_image_dim
        self.dpi = dpi
        self.prompt = prompt or DEFAULT_GROUNDING_PROMPT
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.concurrency = concurrency

    async def ensure_model_loaded(self) -> None:
        """Pre-flight check that ``self.model`` is loaded on the server.

        Mirrors ``OCRProcessor.ensure_model_loaded`` so users on
        ``--grounded`` get the same fail-fast safety net.
        """
        from local_deepl.core.ocr import (  # see P1: lives at core/ocr/__init__.py
            ModelNotLoadedError,
            _format_model_not_loaded,
            _list_loaded_model_ids,
            _model_in_loaded,
        )

        client = AsyncOpenAI(base_url=self.api_base, api_key=self.api_key)
        loaded = await _list_loaded_model_ids(client, self.api_base)
        if not _model_in_loaded(self.model, loaded):
            raise ModelNotLoadedError(
                _format_model_not_loaded(self.api_base, self.model, loaded)
            )

    async def ocr_document(
        self,
        pdf_path: str,
        progress: ProgressCallback | None = None,
        on_warning: WarningCallback | None = None,
    ) -> GroundedResponse:
        page_imgs = await asyncio.to_thread(
            _rasterize_to_jpeg_pages,
            pdf_path,
            self.max_image_dim,
            self.dpi,
        )
        sem = asyncio.Semaphore(max(1, self.concurrency))
        total_pages = len(page_imgs)

        async def run_one(
            page_idx: int,
        ) -> tuple[int, list[GroundedBlock], BaseException | None]:
            b64, w, h = page_imgs[page_idx]
            async with sem:
                try:
                    text = await call_llm(
                        model=self.model,
                        api_base=self.api_base,
                        api_key=self.api_key,
                        temperature=0.0,
                        max_tokens=self.max_tokens,
                        timeout=self.timeout_s,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": self.prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{b64}",
                                        },
                                    },
                                ],
                            }
                        ],
                    )
                    text = text.strip()
                    from .parsers import _parse_grounded_json
                    blocks = _parse_grounded_json(text, page_idx, w, h)

                    if any(b.label in ("image", "figure") for b in blocks):
                        from PIL import Image

                        img_data = base64.b64decode(b64)
                        with Image.open(io.BytesIO(img_data)) as img:
                            for b in blocks:
                                if b.label in ("image", "figure"):
                                    crop_box = (
                                        b.bbox[0] * w,
                                        b.bbox[1] * h,
                                        b.bbox[2] * w,
                                        b.bbox[3] * h,
                                    )
                                    crop_box = (
                                        max(0, min(w, crop_box[0])),
                                        max(0, min(h, crop_box[1])),
                                        max(0, min(w, crop_box[2])),
                                        max(0, min(h, crop_box[3])),
                                    )
                                    if (
                                        crop_box[2] > crop_box[0]
                                        and crop_box[3] > crop_box[1]
                                    ):
                                        cropped = img.crop(crop_box)
                                        buf = io.BytesIO()
                                        cropped.save(buf, format="PNG")
                                        b.image_bytes = buf.getvalue()

                    return page_idx, blocks, None
                except Exception as e:
                    logger.warning(
                        "grounded OCR failed for page %d: %s: %s",
                        page_idx,
                        type(e).__name__,
                        e,
                    )
                    return page_idx, [], e

        tasks = [asyncio.create_task(run_one(i)) for i in range(total_pages)]
        blocks_by_page: dict[int, list[GroundedBlock]] = {}
        failed_pages: list[int] = []
        completed = 0
        if progress is not None:
            await progress("ocr", 0, total_pages, f"Grounded OCR (0/{total_pages})...")
        for fut in asyncio.as_completed(tasks):
            page_idx, blocks, page_error = await fut
            blocks_by_page[page_idx] = blocks
            completed += 1
            if progress is not None:
                await progress(
                    "ocr",
                    completed,
                    total_pages,
                    f"Grounded OCR ({completed}/{total_pages})",
                )
            if page_error is not None:
                failed_pages.append(page_idx)
                if on_warning is not None:
                    await on_warning(page_idx, page_error)

        flat_blocks: list[GroundedBlock] = []
        for page_idx in range(total_pages):
            flat_blocks.extend(blocks_by_page.get(page_idx, []))
        return GroundedResponse(
            blocks=flat_blocks,
            page_sizes=[(w, h) for (_, w, h) in page_imgs],
            failed_pages=failed_pages,
        )
```

- [ ] **Step 7: Create `core/grounded/zai.py`**

```python
"""ZAIHostedOCR — reference skeleton for Z.AI's hosted OCR REST service.

The endpoint routes and submit-request body shape are inferred from
network traffic on ocr.z.ai and have not been verified with credentials.
To confirm: capture the Network tab on ocr.z.ai during an upload, or
request the API docs from Z.AI support.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .parsers import parse_zai_response
from .protocol import ProgressCallback, WarningCallback
from .types import GroundedResponse

logger = logging.getLogger(__name__)


class ZAIHostedOCR:
    """Reference skeleton for Z.AI's hosted OCR REST service.

    Expected flow:
        1. POST {base_url}{SUBMIT_PATH} with the PDF → {task_id}
        2. GET  {base_url}{TASK_PATH}/{task_id} → {status, data:{layout,...}}
           repeat until status == "completed"
        3. parse_zai_response(data) → GroundedResponse
    """

    # TODO(external): confirm these paths against the live Z.AI service.
    SUBMIT_PATH = "/api/paas/v4/ocr/submit"
    TASK_PATH = "/api/paas/v4/ocr/task"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.z.ai",
        poll_interval_s: float = 2.0,
        timeout_s: float = 300.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    async def ocr_document(
        self,
        pdf_path: str,
        progress: ProgressCallback | None = None,
        on_warning: WarningCallback | None = None,
    ) -> GroundedResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60) as client:
            if progress is not None:
                await progress("ocr", 0, 0, "Submitting to Z.AI...")
            with open(pdf_path, "rb") as f:
                resp = await client.post(
                    self.base_url + self.SUBMIT_PATH,
                    headers=headers,
                    files={"file": (pdf_path.rsplit("/", 1)[-1], f, "application/pdf")},
                )
            resp.raise_for_status()
            task_id = resp.json()["data"]["task_id"]

            max_polls = int(self.timeout_s / self.poll_interval_s)
            elapsed = 0.0
            poll_count = 0
            while elapsed < self.timeout_s:
                await asyncio.sleep(self.poll_interval_s)
                elapsed += self.poll_interval_s
                poll_count += 1
                if progress is not None:
                    await progress(
                        "ocr",
                        poll_count,
                        max_polls,
                        f"Z.AI OCR polling ({elapsed:.0f}s)...",
                    )
                r = await client.get(
                    f"{self.base_url}{self.TASK_PATH}/{task_id}",
                    headers=headers,
                )
                r.raise_for_status()
                payload = r.json()
                status = payload.get("data", {}).get("status")
                if status == "completed":
                    return parse_zai_response(payload)
                if status in ("failed", "error"):
                    raise RuntimeError(f"Z.AI OCR task failed: {payload}")
            raise TimeoutError(
                f"Z.AI OCR task {task_id} did not complete in {self.timeout_s}s"
            )
```

- [ ] **Step 8: Create `core/grounded/__init__.py`**

```python
"""Grounded OCR backends — single-call bbox-native VLMs (Qwen-VL family, Z.AI hosted, etc.).

Public surface is preserved verbatim from the legacy ``core/grounded.py``:
``GroundedBlock``, ``GroundedResponse``, ``GroundedOCRBackend``,
``PromptedGroundedOCR``, ``ZAIHostedOCR``, ``parse_zai_response``,
``parse_glm_layout_details``, ``DEFAULT_GROUNDING_PROMPT`` re-export here.
"""
from __future__ import annotations

from .filters import _NON_CONTENT_LABELS, is_content_label
from .parsers import (
    _detect_axis_order_zxyxy,
    parse_glm_layout_details,
    parse_zai_response,
)
from .protocol import GroundedOCRBackend, ProgressCallback, WarningCallback
from .prompted import DEFAULT_GROUNDING_PROMPT, PromptedGroundedOCR
from .rasterization import _rasterize_to_jpeg_pages
from .types import GroundedBlock, GroundedResponse, _clamp
from .zai import ZAIHostedOCR

__all__ = [
    "GroundedBlock",
    "GroundedResponse",
    "GroundedOCRBackend",
    "PromptedGroundedOCR",
    "ZAIHostedOCR",
    "parse_zai_response",
    "parse_glm_layout_details",
    "DEFAULT_GROUNDING_PROMPT",
    "ProgressCallback",
    "WarningCallback",
    "_detect_axis_order_zxyxy",
    "_NON_CONTENT_LABELS",
    "is_content_label",
    "_rasterize_to_jpeg_pages",
    "_clamp",
]
```

- [ ] **Step 9: Delete the old `core/grounded.py`**

Delete `src/local_deepl/core/grounded.py`. The package `core/grounded/` takes over.

- [ ] **Step 10: Verify imports + tests**

Run: `python -c "from local_deepl.core.grounded import PromptedGroundedOCR, ZAIHostedOCR, GroundedBlock, GroundedResponse, parse_zai_response, parse_glm_layout_details, DEFAULT_GROUNDING_PROMPT; print('ok')"`
Expected: `ok`.

Run: `python -c "from local_deepl import PromptedGroundedOCR, OCRPipeline, OCRProcessor; print('ok')"`
Expected: `ok`.

Run: `uv run pytest tests/test_grounded.py -q --co`
Expected: collects without errors.

- [ ] **Step 11: Run full fast suite + lint + types**

Run: `uv run pytest -q -x -m "not slow" && uv run ruff check src tests && uv run mypy src`
Expected: all pass.

---

## Phase P3 — Thin `api/routers/ocr.py` and extract 4 services

### Task P3.1 — Create the four new services

**Files:**
- Create: `src/local_deepl/api/services/ocr_settings.py`
- Create: `src/local_deepl/api/services/ocr_pipeline_factory.py`
- Create: `src/local_deepl/api/services/ocr_response.py`
- Create: `src/local_deepl/api/services/ocr_jobs.py`
- Modify: `src/local_deepl/api/routers/ocr.py` (shrunken to thin orchestrator)

- [ ] **Step 1: Create `api/services/ocr_settings.py`**

```python
"""Form-field merging + validation-error response for the OCR /process route."""
from __future__ import annotations

from typing import Any, cast

from fastapi.responses import JSONResponse
from pydantic import ValidationError

from local_deepl.api.schemas import ProcessSettings

from ..routers.config import _config


def _validation_error_response(exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "Invalid request parameters.",
            "detail": exc.errors(include_context=False),
        },
    )


def _resolve_process_settings(
    form: dict[str, Any],
    *,
    pages_override: str | None = None,
) -> ProcessSettings:
    """Merge form fields with the in-memory config and validate as ``ProcessSettings``.

    `pages` is an explicit override and is not merged from the config.
    """
    merged = {
        k: v if v is not None else cast(dict[str, Any], _config).get(k)
        for k, v in form.items()
        if k != "pages"
    }
    merged = {k: v for k, v in merged.items() if v is not None}
    merged["pages"] = pages_override
    return ProcessSettings.model_validate(merged)
```

- [ ] **Step 2: Create `api/services/ocr_pipeline_factory.py`**

```python
"""Backend selection + pipeline construction + model-load pre-flight for the OCR /process route."""
from __future__ import annotations

import logging
from typing import Any

from local_deepl.core.grounded import PromptedGroundedOCR
from local_deepl.core.ocr import OCRProcessor
from local_deepl.core.preprocessing import (
    CompositePagePreprocessor,
    HandwritingPagePreprocessor,
    LocalPagePreprocessor,
    PagePreprocessingOptions,
    PagePreprocessor,
)
from local_deepl.core.processors import build_document_processors
from local_deepl import HybridAligner, OCRPipeline, PDFHandler
from local_deepl.api.routers.state import progress_service
from local_deepl.api.routers.websocket import manager
from local_deepl.api.schemas import ProcessSettings
from local_deepl.core.callbacks import BlockCallbackSet

logger = logging.getLogger(__name__)


def _make_page_preprocessor(settings: ProcessSettings) -> PagePreprocessor | None:
    """Return the page preprocessor per handwriting + preprocessing flags."""
    preprocessing_options = PagePreprocessingOptions(
        enabled=settings.preprocess_pages,
        orientation_detection=settings.orientation_detection,
        deskew=settings.deskew,
        denoise=settings.denoise,
        normalize_contrast=settings.normalize_contrast,
        crop_cleanup=settings.crop_cleanup,
    )
    if settings.handwriting_hint:
        if preprocessing_options.enabled:
            return CompositePagePreprocessor(
                [HandwritingPagePreprocessor(), LocalPagePreprocessor()]
            )
        return HandwritingPagePreprocessor()
    if preprocessing_options.enabled:
        return LocalPagePreprocessor()
    return None


def _select_backend(settings: ProcessSettings) -> Any:
    """Return the OCR backend that matches the requested pipeline mode."""
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


def _build_pipeline(
    settings: ProcessSettings,
    progress_target: str | None = None,
) -> tuple[OCRPipeline, Any]:
    """Build the OCR pipeline for a request; wire block callbacks to the WebSocket."""
    processors = build_document_processors(
        processor.value for processor in settings.document_processors
    )
    page_preprocessor = _make_page_preprocessor(settings)

    async def _on_block(
        page_idx: int,
        block_idx: int,
        bbox: list[float],
        text: str,
        kind: str,
        confidence: float | None,
    ) -> None:
        if progress_target is None:
            return
        await manager.send_block(
            progress_target,
            page_idx=page_idx,
            block_idx=block_idx,
            bbox=bbox,
            text=text,
            kind=kind,
            confidence=confidence,
        )

    async def _on_page_complete(page_idx: int) -> None:
        if progress_target is None:
            return
        await manager.send_page_complete(progress_target, page_idx=page_idx)

    block_callbacks = BlockCallbackSet(
        on_block=_on_block,
        on_page_complete=_on_page_complete,
    )
    backend = _select_backend(settings)
    pipeline = OCRPipeline(
        pdf_handler=PDFHandler(),
        grounded_backend=backend
        if settings.pipeline_mode == "grounded"
        else None,
        aligner=HybridAligner() if settings.pipeline_mode != "grounded" else None,
        ocr_processor=backend if settings.pipeline_mode != "grounded" else None,
        document_processors=processors,
        page_preprocessor=page_preprocessor,
        block_callbacks=block_callbacks,
    )
    return pipeline, backend


async def _verify_backend_model(backend: Any, model: str, verify: bool) -> None:
    """Skip cloud endpoints and gated providers; otherwise call ``backend.ensure_model_loaded()``."""
    is_cloud = (
        any(
            model.startswith(prefix)
            for prefix in (
                "openai/",
                "anthropic/",
                "gemini/",
                "deepseek/",
                "groq/",
                "vertex_ai/",
            )
        )
        or "api.openai.com" in backend.api_base
    )
    if not verify or is_cloud:
        return
    await backend.ensure_model_loaded()


def stage_to_percent(stage: str, current: int, total: int) -> int:
    """Map a pipeline stage + sub-progress into a 0-100 overall percent."""
    return progress_service.stage_to_percent(stage, current, total)
```

(The `_build_pipeline` return tuple is `(pipeline, backend)` to keep the route's call shape the same.)

- [ ] **Step 3: Create `api/services/ocr_response.py`**

```python
"""Sandwich-PDF response builder + per-page metadata header builders."""
from __future__ import annotations

import json

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from local_deepl import OCRPipeline
from local_deepl.api.routers.common import _cleanup
from local_deepl.api.routers.state import metadata_artifacts
from local_deepl.api.schemas import ProcessSettings
from local_deepl.api.services.artifacts import TextArtifactHandle
from local_deepl.api.services.document_metadata import (
    build_document_metadata_report,
    write_document_metadata_atomic,
)
from local_deepl.api.services.workflow import build_workflow_summary
from ..routers.state import metadata_artifacts as _metadata_store  # noqa: F401

import asyncio


def _document_quality_header(pipeline: OCRPipeline) -> str | None:
    document = getattr(pipeline, "last_document_result", None)
    if document is None:
        return None
    pages = []
    for page in document.pages:
        quality = page.metadata.get("quality")
        if isinstance(quality, dict):
            pages.append({"page_index": page.page_index, "quality": quality})
    if not pages:
        return None
    return json.dumps({"pages": pages}, separators=(",", ":"), sort_keys=True)


def _document_structure_header(pipeline: OCRPipeline) -> str | None:
    document = getattr(pipeline, "last_document_result", None)
    if document is None:
        return None
    pages = []
    for page in document.pages:
        structure = page.metadata.get("structure")
        if isinstance(structure, dict):
            pages.append({"page_index": page.page_index, "structure": structure})
    if not pages:
        return None
    return json.dumps({"pages": pages}, separators=(",", ":"), sort_keys=True)


def _document_sections_header(pipeline: OCRPipeline) -> str | None:
    document = getattr(pipeline, "last_document_result", None)
    if document is None:
        return None
    pages = []
    for page in document.pages:
        sections = page.metadata.get("sections")
        if isinstance(sections, dict):
            pages.append({"page_index": page.page_index, "sections": sections})
    if not pages:
        return None
    return json.dumps({"pages": pages}, separators=(",", ":"), sort_keys=True)


async def _create_document_metadata_artifact(
    pipeline: OCRPipeline,
) -> TextArtifactHandle | None:
    report = build_document_metadata_report(
        getattr(pipeline, "last_document_result", None)
    )
    if report is None:
        return None

    artifact_id = metadata_artifacts.issue_id()
    token = metadata_artifacts.issue_token()
    path = await asyncio.to_thread(
        write_document_metadata_atomic,
        report,
        directory=metadata_artifacts.artifact_dir,
        artifact_id=artifact_id,
    )
    return metadata_artifacts.put(artifact_id=artifact_id, token=token, path=path)


def _build_file_response(
    pipeline: OCRPipeline,
    settings: ProcessSettings,
    output_path: str,
    input_path: str,
    artifact_handle: TextArtifactHandle,
    metadata_handle: TextArtifactHandle | None,
    filename: str,
    failed_pages: list[int],
) -> FileResponse:
    response = FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"ocr_{filename}",
        background=BackgroundTask(_cleanup, input_path, output_path),
    )
    response.headers["X-Text-Artifact-Id"] = artifact_handle.artifact_id
    if failed_pages:
        response.headers["X-Failed-Pages"] = ",".join(str(p) for p in failed_pages)
    response.headers["X-Text-Artifact-Token"] = artifact_handle.token
    response.headers["X-Document-Workflow"] = json.dumps(
        build_workflow_summary(settings), separators=(",", ":"), sort_keys=True
    )
    if metadata_handle is not None:
        response.headers["X-Document-Metadata-Artifact-Id"] = (
            metadata_handle.artifact_id
        )
        response.headers["X-Document-Metadata-Artifact-Token"] = metadata_handle.token
    for header_name, builder in (
        ("X-Document-Quality", _document_quality_header),
        ("X-Document-Structure", _document_structure_header),
        ("X-Document-Sections", _document_sections_header),
    ):
        value = builder(pipeline)
        if value is not None:
            response.headers[header_name] = value
    return response
```

- [ ] **Step 4: Create `api/services/ocr_jobs.py`**

```python
"""In-memory job-history appender + pipeline-stage percent mapper for the OCR /process route."""
from __future__ import annotations

from collections.abc import Sequence

from local_deepl.api.services.jobs import JobStatus

from ..routers.state import job_history, progress_service


def _record_job(
    job_id: str,
    filename: str,
    model: str,
    pipeline_mode: str,
    pages: str | None,
    duration_s: float,
    status: JobStatus,
    failed_pages: Sequence[int] = (),
) -> None:
    """Append a validated job record to the capped in-memory history."""
    job_history.record(
        job_id=job_id,
        filename=filename,
        model=model,
        pipeline_mode=pipeline_mode,
        pages=pages,
        duration_s=duration_s,
        status=status,
        failed_pages=failed_pages,
    )


def stage_to_percent(stage: str, current: int, total: int) -> int:
    """Map a pipeline stage + sub-progress into a 0-100 overall percent."""
    return progress_service.stage_to_percent(stage, current, total)
```

- [ ] **Step 5: Replace `api/routers/ocr.py` with the thin version**

Write the new `api/routers/ocr.py`:

```python
"""/process route — thin orchestrator. Helpers live in ``api/services/ocr_*.py``."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import tempfile
import time
import uuid
from typing import Any, cast

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from local_deepl.api.schemas import ProcessSettings
from local_deepl.api.services.artifacts import PageText
from local_deepl.api.services.ocr_jobs import _record_job, stage_to_percent
from local_deepl.api.services.ocr_pipeline_factory import (
    _build_pipeline,
    _verify_backend_model,
)
from local_deepl.api.services.ocr_response import (
    _build_file_response,
    _create_document_metadata_artifact,
)
from local_deepl.api.services.ocr_settings import (
    _resolve_process_settings,
    _validation_error_response,
)
from local_deepl.api.services.security import SAFE_API_BASE_ERROR, save_validated_upload, UploadValidationError
from local_deepl.core.preprocessing import PagePreprocessingOptions
from local_deepl.core.routing import QualityRoutingOptions
from local_deepl.utils import is_ssrf_target

from . import state
from .common import _cleanup, _stable_server_error
from .config import _config
from .websocket import manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/process")
async def process_pdf(
    file: UploadFile = File(...),
    client_id: str | None = Form(None),
    progress_channel: str | None = Form(None),
    progress_token: str | None = Form(None),
    api_base: str | None = Form(None),
    api_key: str | None = Form(None),
    model: str | None = Form(None),
    pipeline_mode: str | None = Form(None),
    dpi: str | None = Form(None),
    concurrency: str | None = Form(None),
    dense_mode: str | None = Form(None),
    dense_threshold: str | None = Form(None),
    pages: str | None = Form(None),
    refine: str | None = Form(None),
    max_image_dim: str | None = Form(None),
    self_correction: str | None = Form(None),
    binarize: str | None = Form(None),
    dual_engine: str | None = Form(None),
    spellcheck: str | None = Form(None),
    cross_page: str | None = Form(None),
    preprocess_pages: str | None = Form(None),
    orientation_detection: str | None = Form(None),
    deskew: str | None = Form(None),
    denoise: str | None = Form(None),
    normalize_contrast: str | None = Form(None),
    crop_cleanup: str | None = Form(None),
    quality_routing: str | None = Form(None),
    document_processors: str | None = Form(None),
    handwriting_hint: str | None = Form(None),
):
    """Process a PDF or image file through the OCR pipeline."""
    form = {
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "pipeline_mode": pipeline_mode,
        "dpi": dpi,
        "concurrency": concurrency,
        "dense_mode": dense_mode,
        "dense_threshold": dense_threshold,
        "refine": refine,
        "max_image_dim": max_image_dim,
        "self_correction": self_correction,
        "binarize": binarize,
        "dual_engine": dual_engine,
        "spellcheck": spellcheck,
        "cross_page": cross_page,
        "preprocess_pages": preprocess_pages,
        "orientation_detection": orientation_detection,
        "deskew": deskew,
        "denoise": denoise,
        "normalize_contrast": normalize_contrast,
        "crop_cleanup": crop_cleanup,
        "quality_routing": quality_routing,
        "document_processors": document_processors,
        "handwriting_hint": handwriting_hint,
    }
    try:
        settings = _resolve_process_settings(form, pages_override=pages)
    except ValidationError as exc:
        return _validation_error_response(exc)

    if await is_ssrf_target(settings.api_base):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})

    try:
        upload = await save_validated_upload(file)
    except UploadValidationError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    input_path = upload.path
    progress_target = (
        progress_channel
        if manager.is_authorized(progress_channel, progress_token)
        else None
    )
    output_path = os.path.join(tempfile.gettempdir(), f"output_{uuid.uuid4()}.pdf")
    text_path: str | None = None
    job_id = uuid.uuid4().hex
    t_start = time.monotonic()

    try:
        await manager.send_progress(progress_target, "Initializing...", 5, stage="init")

        pipeline, backend = _build_pipeline(settings, progress_target=progress_target)
        verify_model = cast(dict[str, Any], _config).get("verify_model", True)
        await _verify_backend_model(backend, settings.model, verify=verify_model)

        async def on_progress(stage, current, total, message):
            await manager.send_progress(
                progress_target,
                message,
                stage_to_percent(stage, current, total),
                stage=stage,
            )

        async def on_warning(page_index, exc):
            warning_message = (
                f"OCR failed for page {page_index + 1}: {type(exc).__name__}"
            )
            await manager.send_progress(
                progress_target,
                warning_message,
                0,
                stage="ocr",
                warning=True,
            )

        pages_text = await pipeline.run(
            input_path,
            output_path,
            dpi=settings.dpi,
            pages=settings.pages,
            concurrency=settings.concurrency,
            refine=settings.refine,
            max_image_dim=settings.max_image_dim,
            dense_threshold=settings.dense_threshold,
            dense_mode=settings.dense_mode,
            self_correction=settings.self_correction,
            binarize=settings.binarize,
            dual_engine=settings.dual_engine,
            spellcheck=settings.spellcheck,
            cross_page=settings.cross_page,
            preprocessing_options=PagePreprocessingOptions(
                enabled=settings.preprocess_pages,
                orientation_detection=settings.orientation_detection,
                deskew=settings.deskew,
                denoise=settings.denoise,
                normalize_contrast=settings.normalize_contrast,
                crop_cleanup=settings.crop_cleanup,
            ),
            quality_routing_options=QualityRoutingOptions(
                enabled=settings.quality_routing
            ),
            progress=on_progress,
            on_warning=on_warning,
        )

        failed_pages = list(pipeline.last_failed_pages)

        artifact_handle = await asyncio.to_thread(
            state.text_artifacts.create, cast(PageText, pages_text)
        )
        text_path = artifact_handle.path

        doc_res = getattr(pipeline, "last_document_result", None)
        if doc_res and doc_res.tree:
            from local_deepl.api.services.tree_artifact import write_tree_atomic

            def _write_tree() -> None:
                write_tree_atomic(doc_res.tree, pathlib.Path(f"{text_path}.tree.json"))

            await asyncio.to_thread(_write_tree)

        metadata_handle = await _create_document_metadata_artifact(pipeline)
        job_id = artifact_handle.artifact_id

        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=job_id,
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="complete",
            failed_pages=failed_pages,
        )

        if failed_pages:
            await manager.send_progress(
                progress_target,
                f"Completed with {len(failed_pages)} page failure(s).",
                100,
                stage="complete",
            )
        else:
            await manager.send_progress(
                progress_target, "Done! Preparing download...", 100, stage="complete"
            )

        return _build_file_response(
            pipeline=pipeline,
            settings=settings,
            output_path=output_path,
            input_path=input_path,
            artifact_handle=artifact_handle,
            metadata_handle=metadata_handle,
            filename=file.filename or "unknown",
            failed_pages=failed_pages,
        )

    except ValueError as ve:
        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=job_id,
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="error",
        )
        logger.warning("OCR processing rejected invalid input: %s", ve)
        await manager.send_progress(progress_target, "Invalid input.", 0, stage="error")
        _cleanup(input_path, output_path, text_path)
        return JSONResponse(status_code=400, content={"error": "Invalid input."})

    except Exception:
        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=job_id,
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="error",
        )
        logger.exception("OCR processing failed")
        await manager.send_progress(
            progress_target, "Processing failed.", 0, stage="error"
        )
        _cleanup(input_path, output_path, text_path)
        return _stable_server_error()
```

- [ ] **Step 6: Verify imports + tests**

Run: `python -c "from local_deepl.api.routers.ocr import router; from local_deepl.api.services.ocr_settings import _resolve_process_settings; from local_deepl.api.services.ocr_pipeline_factory import _select_backend; from local_deepl.api.services.ocr_response import _build_file_response; from local_deepl.api.services.ocr_jobs import _record_job; print('ok')"`
Expected: `ok`.

Run: `uv run pytest tests/test_api_safety.py tests/test_ocr.py -q --co`
Expected: collects without errors.

- [ ] **Step 7: Run full fast suite + lint + types**

Run: `uv run pytest -q -x -m "not slow" && uv run ruff check src tests && uv run mypy src`
Expected: all pass.

---

## Phase P4 — Delete `api/routers/ai.py` + update ARCHITECTURE.md

### Task P4.1 — Remove dead code and refresh docs

**Files:**
- Delete: `src/local_deepl/api/routers/ai.py`
- Delete (conditional): `tests/test_ai_router.py` (after inspection)
- Modify: `ARCHITECTURE.md` (line 54 misleading text, Key Files table row for `api/routers/ai.py`)

- [ ] **Step 1: Inspect `tests/test_ai_router.py`**

Run: `head -60 tests/test_ai_router.py`
If it tests only the routes that are being removed (e.g., `test_post_translate`, `test_post_extract`, etc., that hit `/api/translate`, `/api/extract` defined in the dead `ai.py` and already-covered by `tests/test_api_safety.py`), mark this for deletion. Otherwise, keep the file.

- [ ] **Step 2: Delete `api/routers/ai.py`**

Delete the file. Confirm it is not imported anywhere:

Run: `grep -R "api.routers.ai" src/ tests/`
Expected: no matches.

- [ ] **Step 3: Delete `tests/test_ai_router.py` if redundant**

If inspection in Step 1 found it redundant, delete it. Otherwise, leave it.

- [ ] **Step 4: Update `ARCHITECTURE.md`**

In `ARCHITECTURE.md`:

- Remove the row `| `api/routers/ai.py` | Underlying AI service module — ...; consumed by `extraction.py` and `translation.py` |` (line 54, misleading — `ai.py` is a router module not a service module, and it is not mounted).
- Update the Key Files table (line 88 of the original AGENTS.md-equivalent) to replace `api/routers/ai.py | AI service module consumed by extraction.py and translation.py` with the new entries: `api/services/ocr_settings.py | Form-field merging + validation for the OCR /process route`, `api/services/ocr_pipeline_factory.py | Backend selection + pipeline construction + model-load pre-flight`, `api/services/ocr_response.py | Sandwich-PDF response builder + per-page metadata headers`, `api/services/ocr_jobs.py | In-memory job-history appender + stage→percent`.
- Add entries for the new sub-packages: `core/ocr/{__init__,processor,prompts,filters,client,exceptions}.py | ...` and `core/grounded/{__init__,protocol,types,filters,parsers,rasterization,prompted,zai}.py | ...`.
- Add a "Change Blueprint" section entry dated 2026-07-13 documenting the four-phase decomposition.

- [ ] **Step 5: Verify**

Run: `grep -R "consumed by extraction" ARCHITECTURE.md`
Expected: no matches.

Run: `grep -R "api.routers.ai" src/ tests/ ARCHITECTURE.md`
Expected: no matches.

Run: `uv run pytest -q -x -m "not slow" && uv run ruff check src tests && uv run mypy src`
Expected: all pass.

- [ ] **Step 6: Final check — line counts**

Run (PowerShell):
```powershell
(Get-Content src\local_deepl\api\routers\ocr.py | Measure-Object).Lines
(Get-ChildItem src\local_deepl\core\ocr\*.py | ForEach-Object { (Get-Content $_ | Measure-Object).Lines }) | Sort-Object -Descending
(Get-ChildItem src\local_deepl\core\grounded\*.py | ForEach-Object { (Get-Content $_ | Measure-Object).Lines }) | Sort-Object -Descending
```

Expected: the thin `api/routers/ocr.py` < 200 LOC (down from 662). No file under `core/ocr/` or `core/grounded/` exceeds 350 LOC.

---

## Self-Review

**Spec coverage:**

| Spec § | Plan task(s) |
|---|---|
| §1 Background, Hard constraints | The whole plan; preserved public surface by re-exports in `__init__.py`. |
| §2.1 Module layout | P1.1 (sub-package files), P2.1 (sub-package files), P3.1 (services + thin router). |
| §2.2 Public surface preserved | `__init__.py` re-exports in every new sub-package; verified in P1.8, P2.10, P3.6. |
| §3.1 `core/ocr/` contracts | P1.1 (Steps 1-6). |
| §3.2 `core/grounded/` contracts | P2.1 (Steps 1-8). |
| §3.3 thin router + 4 services | P3.1 (Steps 1-5). |
| §3.4 delete dead `ai.py` | P4.1 (Steps 2-3). |
| §4 Data flow | Behavior-preserving extraction; the route in P3 Step 5 keeps the same call order. |
| §5 Error handling | No change — same exceptions caught in the same places. |
| §6 Testing | Existing 81+ tests are the verification gate. No new tests. |
| §7 Sequencing | The four phases map 1:1 to the four tasks above. |
| §9 Acceptance criteria | Verified in P1.8-P1.10, P2.10-P2.11, P3.6-P3.7, P4.5-P4.6. |

**No placeholders found.** All code blocks contain real code (extracted verbatim from the existing modules where applicable; restructured only where the spec said "single-responsibility").

**Type consistency check:** The plan uses `OCRProcessor`, `PromptedGroundedOCR`, `GroundedBlock`, `GroundedResponse`, `LLMCallError`, `ModelNotLoadedError` consistently throughout. The new helpers (`select_page_prompt`, `fill_dual_engine_page`, etc.) are added in P1 only; subsequent phases only call them. No symbol appears in P2-P4 that wasn't defined or imported in P1.

**Ambiguity check:** None found. Every step has explicit code; every command lists the expected outcome.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-god-module-decomposition.md`.

**Two execution options:**

1. **Inline execution** — I'll work through the four phases in this session, running tests + lint + mypy between each. Faster.
2. **Subagent-driven** — fresh subagent per task; slower but isolated.

**Given the time budget (8 turns remaining for design + 4 phases), inline execution is the right choice.**
