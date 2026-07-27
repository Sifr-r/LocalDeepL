"""OCRProcessor — the main OCR class.

:class:`OCRProcessor` is the single class that performs OCR against a
local vision LLM (OlmOCR via LM Studio by default; any OpenAI-compatible
endpoint works, including GLM OCR via Ollama — set LLM_API_BASE/LLM_MODEL
or pass ``api_base``/``model``).

It composes four sibling modules:

- :mod:`local_deepl.core.ocr.prompts` — OlmOCR/page/crop/dual-engine/
  correction/handwriting prompt constants and selection helpers.
- :mod:`local_deepl.core.ocr.filters` — output sanitization
  (YAML front-matter strip, fallback-phrase suppression, runaway-
  repetition clip).
- :mod:`local_deepl.core.ocr.client` — pre-flight model-loaded checks
  (reused by :mod:`local_deepl.core.grounded.zai`).
- :mod:`local_deepl.core.ocr.exceptions` — :class:`LLMCallError` and
  :class:`ModelNotLoadedError`.

Call :meth:`ensure_model_loaded` once at pipeline startup before paying
for image conversion or detection (LM Studio silently falls back to
whatever model is currently loaded when the requested one is missing —
see :class:`ModelNotLoadedError` for why this matters). Then use
:meth:`perform_ocr` for full-page OCR or :meth:`perform_ocr_on_crop`
for single-box OCR.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from openai import AsyncOpenAI

from local_deepl.core.llm_client import call_llm
from local_deepl.core.ocr.client import (
    _format_model_not_loaded,
    _list_loaded_model_ids,
    _model_in_loaded,
)
from local_deepl.core.ocr.exceptions import LLMCallError, ModelNotLoadedError
from local_deepl.core.ocr.filters import (
    _is_fallback_response,
    _strip_runaway_repetition,
    _strip_yaml_front_matter,
)
from local_deepl.core.ocr.prompts import (
    CORRECTION_CROP_PROMPT,
    CORRECTION_PAGE_PROMPT,
    CROP_PROMPT,
    DUAL_ENGINE_CROP_PROMPT,
    DUAL_ENGINE_PAGE_PROMPT,
    HANDWRITING_CROP_PROMPT,
    HANDWRITING_PAGE_PROMPT,
    OLMOCR_PAGE_PROMPT,
)
from local_deepl.core.ocr.resilience import CircuitBreaker, is_transient_error

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

    # Page-level OCR (full image): up to ~4 minutes, ~6k tokens of output.
    # Dense handwritten pages with tables can easily produce 2-3k tokens
    # of markdown, so 6k leaves headroom without enabling endless loops.
    PAGE_TIMEOUT_S: float = 240.0
    PAGE_MAX_TOKENS: int = 6144

    # Crop-level OCR (single box): a sentence at most. Capping much
    # tighter prevents a confused model from emitting a whole-page worth
    # of hallucinated text into one bbox during the refine stage.
    CROP_TIMEOUT_S: float = 60.0
    CROP_MAX_TOKENS: int = 256

    # Retry policy for transient VLM errors (429, 5xx, connection drops).
    # Exponential backoff: base * 2^attempt, capped at MAX. Env overrides:
    # LOCAL_DEEPL_LLM_MAX_RETRIES, LOCAL_DEEPL_LLM_RETRY_BASE_DELAY.
    MAX_RETRIES: int = int(os.getenv("LOCAL_DEEPL_LLM_MAX_RETRIES", "2"))
    RETRY_BASE_DELAY_S: float = float(
        os.getenv("LOCAL_DEEPL_LLM_RETRY_BASE_DELAY", "1.0")
    )
    RETRY_MAX_DELAY_S: float = 8.0

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        trocr_engine: TrOCREngine | None = None,
        handwriting_mode: bool = False,
        confidence_threshold: float = 0.75,
    ):
        self.api_base: str = (
            api_base or os.getenv("LLM_API_BASE") or "http://localhost:1234/v1"
        )
        self.api_key: str = api_key or os.getenv("LLM_API_KEY") or "lm-studio"
        self.model: str = model or os.getenv("LLM_MODEL") or "allenai/olmocr-2-7b"
        self.client = AsyncOpenAI(base_url=self.api_base, api_key=self.api_key)
        # Optional TrOCR specialist (lazy-loaded). When set, low-confidence
        # crops are re-OCR'd with TrOCR and the higher-confidence candidate wins.
        self.trocr_engine = trocr_engine
        self.handwriting_mode = handwriting_mode
        self.confidence_threshold = confidence_threshold
        # Per-request circuit breaker: after LOCAL_DEEPL_CB_FAILURE_THRESHOLD
        # consecutive failures the remaining calls in this job fail fast
        # instead of each waiting for a full timeout against a dead endpoint.
        self.circuit_breaker = CircuitBreaker()

    async def ensure_model_loaded(self) -> None:
        """Pre-flight check that ``self.model`` is loaded on the server.

        Hits ``GET /v1/models`` via the OpenAI SDK and verifies the
        configured model ID appears in the loaded list (case-insensitive).
        Raises :class:`ModelNotLoadedError` on mismatch with a message
        that names what's loaded and how to fix it. Wraps any underlying
        transport / auth failure in :class:`LLMCallError`.

        Why we do this: see :class:`ModelNotLoadedError`. Cheap call (one
        GET, no inference); call once at pipeline startup before paying
        for image conversion or detection.
        """
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
        """OCR a full page image. Returns non-empty lines in reading order.

        YAML front matter emitted by OlmOCR (rotation/language/is_table flags)
        is stripped before returning. Runaway repetition (the model getting
        stuck emitting the same line over and over) is detected and clipped
        — this happens occasionally on dense handwritten pages even with
        max_tokens set, and pollutes downstream alignment with junk lines.
        """
        if binarize:
            image_base64 = await asyncio.to_thread(
                self._apply_adaptive_threshold, image_base64
            )

        prompt = (
            HANDWRITING_PAGE_PROMPT
            if getattr(self, "handwriting_mode", False)
            else OLMOCR_PAGE_PROMPT
        )
        if dual_engine:
            draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)
            if draft:
                prompt = DUAL_ENGINE_PAGE_PROMPT.replace("{draft_text}", draft)

        text = await self._chat(
            prompt,
            image_base64,
            timeout=self.PAGE_TIMEOUT_S,
            max_tokens=self.PAGE_MAX_TOKENS,
        )
        if not text:
            return []

        if self_correction:
            correction_prompt = CORRECTION_PAGE_PROMPT.replace("{draft_text}", text)
            text = await self._chat(
                correction_prompt,
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
        """OCR a single cropped box region. Returns a single whitespace-joined string.

        Empty-string for blank/uncertain crops (filtered hallucination).
        """
        if binarize:
            image_base64 = await asyncio.to_thread(
                self._apply_adaptive_threshold, image_base64
            )

        prompt = (
            HANDWRITING_CROP_PROMPT
            if getattr(self, "handwriting_mode", False)
            else CROP_PROMPT
        )
        if dual_engine:
            draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)
            if draft:
                prompt = DUAL_ENGINE_CROP_PROMPT.replace("{draft_text}", draft)

        text = await self._chat(
            prompt,
            image_base64,
            timeout=self.CROP_TIMEOUT_S,
            max_tokens=self.CROP_MAX_TOKENS,
        )
        if not text:
            return ""

        if self_correction:
            correction_prompt = CORRECTION_CROP_PROMPT.replace("{draft_text}", text)
            text = await self._chat(
                correction_prompt,
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

        # Phase A.2 (review M3) — TrOCR dual-engine arbitration.
        # The VLM gets first crack at every handwriting crop. Only when its
        # output looks low-confidence (heuristic < threshold) do we hand the
        # same image bytes to TrOCR, which is purpose-built for handwriting.
        # If TrOCR is more confident than the VLM, we send the TrOCR text
        # back to the VLM as a "draft" and let it produce a corrected read;
        # whichever side is more confident wins. This avoids the failure
        # mode where the VLM hallucinates cursive characters and the user's
        # only recourse is to manually re-transcribe.
        #
        # Pre-fix this branch was dead code: it called `self.trocr_engine.ocr`
        # (no such method) with `image_base64` (wrong arg type; the real
        # `recognize` takes raw bytes). The `try/except` swallowed the
        # AttributeError, so the bug was invisible to the fast test suite.
        if getattr(self, "handwriting_mode", False) and self.trocr_engine is not None:
            from local_deepl.core.trocr_engine import _heuristic_confidence

            vlm_conf = _heuristic_confidence(result)
            if vlm_conf < self.confidence_threshold:
                try:
                    import base64

                    image_bytes = base64.b64decode(image_base64)
                    trocr_res = await self.trocr_engine.recognize(image_bytes)
                    if trocr_res.confidence > vlm_conf:
                        correction_prompt = DUAL_ENGINE_CROP_PROMPT.replace(
                            "{draft_text}", trocr_res.text
                        )
                        vlm_corrected = await self._chat(
                            correction_prompt,
                            image_base64,
                            timeout=self.CROP_TIMEOUT_S,
                            max_tokens=self.CROP_MAX_TOKENS,
                        )
                        vlm_corrected_body = _strip_yaml_front_matter(vlm_corrected)
                        vlm_corrected_res = " ".join(
                            line.strip()
                            for line in vlm_corrected_body.split("\n")
                            if line.strip()
                        )
                        if _is_fallback_response(vlm_corrected_res):
                            vlm_corrected_res = ""

                        vlm_corr_conf = _heuristic_confidence(vlm_corrected_res)
                        if trocr_res.confidence > vlm_corr_conf:
                            result = trocr_res.text
                        else:
                            result = vlm_corrected_res
                except Exception as e:
                    # TrOCR is optional; a failure here must not poison the
                    # surrounding OCR result. Log and return the VLM's
                    # best-effort output.
                    logger.warning("TrOCR fallback failed: %s", e)

        return result

    async def _chat(
        self,
        prompt: str,
        image_base64: str,
        *,
        timeout: float,
        max_tokens: int,
    ) -> str:
        """Call the VLM with retry-on-transient and circuit-breaker protection.

        Transient failures (429, 5xx, connection resets, timeouts) are
        retried up to ``MAX_RETRIES`` times with exponential backoff.
        Permanent failures (context-length exceeded, auth) raise
        immediately. The circuit breaker counts consecutive failures
        (across all attempts) and fails fast once the endpoint is deemed
        down, so a dead server doesn't serialize N page-timeouts.
        """
        self.circuit_breaker.check()

        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt > 0:
                # Re-check: a prior attempt may have tripped the breaker.
                # CircuitOpenError propagates directly (not an LLMCallError)
                # so the engine's per-page handler sees "endpoint down".
                self.circuit_breaker.check()
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
                self.circuit_breaker.record_success()
                return content.strip()
            except Exception as e:
                last_exc = e
                self.circuit_breaker.record_failure()

                if not is_transient_error(e):
                    break  # permanent failure — do not retry
                if attempt < self.MAX_RETRIES:
                    delay = min(
                        self.RETRY_BASE_DELAY_S * (2**attempt),
                        self.RETRY_MAX_DELAY_S,
                    )
                    logger.warning(
                        "Transient LLM error (attempt %d/%d), retrying in "
                        "%.1fs: %s: %s",
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                        delay,
                        type(e).__name__,
                        e,
                    )
                    await asyncio.sleep(delay)

        assert last_exc is not None
        err_msg = str(last_exc)
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
                f"Underlying error: {last_exc}"
            ) from last_exc
        raise LLMCallError(
            f"LLM OCR call failed against {self.api_base} "
            f"({type(last_exc).__name__}): {last_exc}"
        ) from last_exc

    def _get_tesseract_draft(self, image_base64: str) -> str:
        try:
            import base64
            import io

            import pytesseract
            from PIL import Image

            image_bytes = base64.b64decode(image_base64)
            img = Image.open(io.BytesIO(image_bytes))
            # Fallback to multiple common languages (or just Arabic/English for this workload)
            draft: str = pytesseract.image_to_string(img, lang="ara+eng")
            return draft.strip()
        except Exception:
            return ""

    def _apply_adaptive_threshold(self, image_base64: str) -> str:
        """Adaptive mean threshold using only PIL (no OpenCV dependency).

        Approximates ``cv2.adaptiveThreshold(..., ADAPTIVE_THRESH_GAUSSIAN_C,
        THRESH_BINARY, 21, 15)`` with a box-blur local mean. The Gaussian
        vs uniform kernel difference is negligible for handwriting
        binarization at block_size=21.
        """
        try:
            import base64
            import io

            import numpy as np
            from PIL import Image, ImageFilter

            img = Image.open(io.BytesIO(base64.b64decode(image_base64))).convert("L")

            # Local mean via box blur (radius 10 ≈ block_size 21).
            local_mean = img.filter(ImageFilter.BoxBlur(radius=10))

            # Adaptive threshold: pixel is white (255) if src > local_mean - C.
            # C=15 matches the old cv2.adaptiveThreshold constant parameter.
            src_arr = np.asarray(img, dtype=np.int16)
            mean_arr = np.asarray(local_mean, dtype=np.int16)
            binary_arr = np.where(src_arr > mean_arr - 15, 255, 0).astype(np.uint8)
            binary = Image.fromarray(binary_arr, mode="L")

            buf = io.BytesIO()
            binary.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            return image_base64


__all__ = ["OCRProcessor"]
