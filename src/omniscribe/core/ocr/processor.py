"""OCRProcessor — the main OCR class.

:class:`OCRProcessor` is the single class that performs OCR against a
local vision LLM (OlmOCR via LM Studio by default; any OpenAI-compatible
endpoint works, including GLM OCR via Ollama — set LLM_API_BASE/LLM_MODEL
or pass ``api_base``/``model``).

It composes four sibling modules:

- :mod:`omniscribe.core.ocr.prompts` — OlmOCR/page/crop/dual-engine/
  correction/handwriting prompt constants and selection helpers.
- :mod:`omniscribe.core.ocr.filters` — output sanitization
  (YAML front-matter strip, fallback-phrase suppression, runaway-
  repetition clip).
- :mod:`omniscribe.core.ocr.client` — pre-flight model-loaded checks
  (reused by :mod:`omniscribe.core.grounded.zai`).
- :mod:`omniscribe.core.ocr.exceptions` — :class:`LLMCallError` and
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

from omniscribe.config import load_settings
from omniscribe.core.llm_client import call_llm
from omniscribe.core.llm_temperatures import TEMPERATURE_OCR
from omniscribe.core.ocr.client import (
    _format_model_not_loaded,
    _list_loaded_model_ids,
    _model_in_loaded,
)
from omniscribe.core.ocr.exceptions import LLMCallError, ModelNotLoadedError
from omniscribe.core.ocr.filters import (
    _is_fallback_response,
    _strip_runaway_repetition,
    _strip_yaml_front_matter,
)
from omniscribe.core.ocr.prompts import (
    CROP_PROMPT,
    HANDWRITING_CROP_PROMPT,
    HANDWRITING_PAGE_PROMPT,
    OLMOCR_PAGE_PROMPT,
    fill_correction_crop,
    fill_correction_page,
    fill_dual_engine_crop,
    fill_dual_engine_page,
    model_supports_system_role,
    select_system_message,
)
from omniscribe.core.ocr.resilience import (
    CircuitBreakerRegistry,
    is_transient_error,
)
from omniscribe.utils.env import env_int

if TYPE_CHECKING:
    from omniscribe.core.trocr_engine import TrOCREngine

load_dotenv()

# Resolve the audit H3 knobs once at import time: prefer the validated
# ``RuntimeSettings`` values for the four fields it owns (page / crop
# timeouts, max retries, retry base delay), and fall back to the
# canonical env-int helper for the two token budgets that don't have a
# settings field yet. Re-running the module (e.g. from the timeout-env
# test fixture) re-evaluates these against the current process env.
_settings = load_settings()

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
    # Override timeout via ``OMNISCRIBE_VLM_PAGE_TIMEOUT`` (audit A-11);
    # override the token budget via ``OMNISCRIBE_VLM_PAGE_MAX_TOKENS``
    # for tail-latency tuning on dense pages (Phase 5). Both flow
    # through :mod:`omniscribe.config` / :mod:`omniscribe.utils.env`
    # (audit H3) — no direct ``os.getenv`` in this module.
    PAGE_TIMEOUT_S: float = _settings.vlm_page_timeout
    PAGE_MAX_TOKENS: int = env_int("OMNISCRIBE_VLM_PAGE_MAX_TOKENS", 6144)

    # Crop-level OCR (single box): a sentence at most. Capping much
    # tighter prevents a confused model from emitting a whole-page worth
    # of hallucinated text into one bbox during the refine stage.
    # Override via ``OMNISCRIBE_VLM_CROP_TIMEOUT`` (audit A-11); token
    # budget via ``OMNISCRIBE_VLM_CROP_MAX_TOKENS`` (Phase 5).
    CROP_TIMEOUT_S: float = _settings.vlm_crop_timeout
    CROP_MAX_TOKENS: int = env_int("OMNISCRIBE_VLM_CROP_MAX_TOKENS", 256)

    # Retry policy for transient VLM errors (429, 5xx, connection drops).
    # Exponential backoff: base * 2^attempt, capped at MAX. Env overrides:
    # OMNISCRIBE_LLM_MAX_RETRIES, OMNISCRIBE_LLM_RETRY_BASE_DELAY.
    MAX_RETRIES: int = _settings.llm_max_retries
    RETRY_BASE_DELAY_S: float = _settings.llm_retry_base_delay
    RETRY_MAX_DELAY_S: float = 8.0

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        trocr_engine: TrOCREngine | None = None,
        handwriting_mode: bool = False,
        confidence_threshold: float = 0.75,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
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
        # Per-(api_base, model) circuit breaker. Without an injected
        # registry each OCRProcessor gets a private breaker; with one,
        # processors targeting the same endpoint share one breaker so a
        # tripped breaker is visible to every concurrent caller.
        registry = circuit_breaker_registry or CircuitBreakerRegistry()
        self.circuit_breaker = registry.get_or_create(
            api_base=self.api_base, model=self.model
        )

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

        The OLMOCR-2 page prompt is sent as a plain user message with no
        system role — the model was RL-trained on this exact distribution
        and a system message would shift it. Dual-engine and correction
        paths wrap a system message around their user turns.
        """
        if binarize:
            image_base64 = await asyncio.to_thread(
                self._apply_adaptive_threshold, image_base64
            )

        handwriting_mode = getattr(self, "handwriting_mode", False)
        prompt = HANDWRITING_PAGE_PROMPT if handwriting_mode else OLMOCR_PAGE_PROMPT
        if dual_engine:
            draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)
            if draft:
                prompt = fill_dual_engine_page(draft)

        # OlmOCR-2 page path: pure user message, no system role. Every
        # other page path gets a system message — *unless* the active
        # model is one of the system-role-excluded families
        # (e.g. allenai/olmocr-2-7b), in which case we drop the system
        # message entirely to keep the model's RL-trained distribution
        # intact.
        page_system = self._resolve_page_system(
            prompt=prompt,
            handwriting_mode=handwriting_mode,
            dual_engine=dual_engine,
        )

        text = await self._chat(
            prompt,
            image_base64,
            timeout=self.PAGE_TIMEOUT_S,
            max_tokens=self.PAGE_MAX_TOKENS,
            system_prompt=page_system,
        )
        if not text:
            return []

        if self_correction:
            correction_prompt = fill_correction_page(text)
            text = await self._chat(
                correction_prompt,
                image_base64,
                timeout=self.PAGE_TIMEOUT_S,
                max_tokens=self.PAGE_MAX_TOKENS,
                system_prompt=self._resolve_page_system(
                    prompt=correction_prompt,
                    handwriting_mode=handwriting_mode,
                    dual_engine=dual_engine,
                ),
            )
            if not text:
                return []

        body = _strip_yaml_front_matter(text)
        lines = [line.strip() for line in body.split("\n") if line.strip()]
        return _strip_runaway_repetition(lines)

    async def _run_trocr_arbitration(
        self,
        vlm_result: str,
        image_base64: str,
        vlm_confidence: float,
    ) -> str:
        """Arbitrate between VLM and TrOCR outputs; return the higher-confidence text.

        Args:
            vlm_result: Text from VLM model
            image_base64: Base64-encoded image for TrOCR
            vlm_confidence: Confidence score from VLM heuristic

        Returns:
            Winning text (VLM, TrOCR, or VLM-corrected)
            Returns vlm_result if TrOCR is unavailable or fails.
        """
        if self.trocr_engine is None:
            return vlm_result

        try:
            import base64

            from omniscribe.core.trocr_engine import _heuristic_confidence

            image_bytes = base64.b64decode(image_base64)
            trocr_res = await self.trocr_engine.recognize(image_bytes)
            if trocr_res.confidence > vlm_confidence:
                correction_prompt = fill_dual_engine_crop(trocr_res.text)
                vlm_corrected = await self._chat(
                    correction_prompt,
                    image_base64,
                    timeout=self.CROP_TIMEOUT_S,
                    max_tokens=self.CROP_MAX_TOKENS,
                    system_prompt=self._resolve_crop_system(
                        handwriting_mode=getattr(self, "handwriting_mode", False),
                        dual_engine=True,
                    ),
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
                    return trocr_res.text
                else:
                    return vlm_corrected_res
            else:
                return vlm_result
        except Exception as e:
            # TrOCR is optional; a failure here must not poison the
            # surrounding OCR result. Log and return the VLM's best effort.
            logger.warning("TrOCR arbitration failed: %s", e)
            return vlm_result

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

        handwriting_mode = getattr(self, "handwriting_mode", False)
        prompt = HANDWRITING_CROP_PROMPT if handwriting_mode else CROP_PROMPT
        if dual_engine:
            draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)
            if draft:
                prompt = fill_dual_engine_crop(draft)

        crop_system = self._resolve_crop_system(
            handwriting_mode=handwriting_mode, dual_engine=dual_engine
        )

        text = await self._chat(
            prompt,
            image_base64,
            timeout=self.CROP_TIMEOUT_S,
            max_tokens=self.CROP_MAX_TOKENS,
            system_prompt=crop_system,
        )
        if not text:
            return ""

        if self_correction:
            correction_prompt = fill_correction_crop(text)
            text = await self._chat(
                correction_prompt,
                image_base64,
                timeout=self.CROP_TIMEOUT_S,
                max_tokens=self.CROP_MAX_TOKENS,
                system_prompt=crop_system,
            )
            if not text:
                return ""

        body = _strip_yaml_front_matter(text)
        result = " ".join(line.strip() for line in body.split("\n") if line.strip())
        if _is_fallback_response(result):
            result = ""

        # Phase A.2 (review M3) — TrOCR dual-engine arbitration.
        # See _run_trocr_arbitration() for details on the arbitration logic.
        if getattr(self, "handwriting_mode", False) and self.trocr_engine is not None:
            from omniscribe.core.trocr_engine import _heuristic_confidence

            vlm_conf = _heuristic_confidence(result)
            if vlm_conf < self.confidence_threshold:
                result = await self._run_trocr_arbitration(
                    result, image_base64, vlm_conf
                )

        return result

    async def _chat(
        self,
        prompt: str,
        image_base64: str,
        *,
        timeout: float,
        max_tokens: int,
        system_prompt: str | None = None,
    ) -> str:
        """Call the VLM with retry-on-transient and circuit-breaker protection.

        Transient failures (429, 5xx, connection resets, timeouts) are
        retried up to ``MAX_RETRIES`` times with exponential backoff.
        Permanent failures (context-length exceeded, auth) raise
        immediately. The circuit breaker counts consecutive failures
        (across all attempts) and fails fast once the endpoint is deemed
        down, so a dead server doesn't serialize N page-timeouts.

        ``system_prompt``: when set, sent as a separate system-role
        message. The OLMOCR-2 page path leaves this ``None`` to keep
        the model's RL-trained distribution intact.
        """
        await self.circuit_breaker.check()

        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt > 0:
                # Re-check: a prior attempt may have tripped the breaker.
                # CircuitOpenError propagates directly (not an LLMCallError)
                # so the engine's per-page handler sees "endpoint down".
                await self.circuit_breaker.check()
            try:
                content = await call_llm(
                    model=self.model,
                    api_base=self.api_base,
                    api_key=self.api_key,
                    temperature=TEMPERATURE_OCR,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    system_prompt=system_prompt,
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
                await self.circuit_breaker.record_success()
                return content.strip()
            except Exception as e:
                last_exc = e
                await self.circuit_breaker.record_failure()

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
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            # ``ImportError`` covers the soft-dep case where pytesseract or
            # PIL is not installed in this environment; ``RuntimeError``
            # covers ``pytesseract.TesseractError`` (TesseractError subclasses
            # RuntimeError) and any subprocess failure; ``OSError`` covers
            # PIL file errors and tesseract binary-not-found; ``ValueError``
            # covers malformed base64 input.
            logger.warning(
                "OCR pytesseract fallback failed: %s",
                exc,
                exc_info=True,
            )
            return ""

    def _resolve_page_system(
        self,
        *,
        prompt: str,
        handwriting_mode: bool,
        dual_engine: bool,
    ) -> str | None:
        """Pick the right system message for a page-level OCR call.

        Two reasons to return ``None``:

        1. The canonical OLMOCR-2 page prompt is in use — the model
           was RL-trained on it as a pure user message; a system role
           would shift the distribution.
        2. The active model is one of the system-role-excluded
           families (currently just OlmOCR). Sending a system role
           causes LM Studio + OlmOCR-2 to misbehave on the crop /
           handwriting / dual-engine paths.
        """
        if prompt is OLMOCR_PAGE_PROMPT:
            return None
        if not model_supports_system_role(self.model):
            return None
        return select_system_message(
            handwriting_mode=handwriting_mode, dual_engine=dual_engine
        )

    def _resolve_crop_system(
        self,
        *,
        handwriting_mode: bool,
        dual_engine: bool,
    ) -> str | None:
        """Pick the right system message for a crop-level OCR call.

        Crop calls never use the canonical OLMOCR page prompt, so
        reason #1 from :meth:`_resolve_page_system` doesn't apply.
        The only thing that can suppress the system message here
        is the active model being system-role-excluded.
        """
        if not model_supports_system_role(self.model):
            return None
        return select_system_message(
            handwriting_mode=handwriting_mode, dual_engine=dual_engine
        )

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
        except (ImportError, OSError, ValueError) as exc:
            # ``ImportError`` covers the case where numpy or PIL is not
            # installed in this environment; ``OSError`` covers PIL file
            # errors and array-to-image conversion failures; ``ValueError``
            # covers malformed base64 input and array-shape mismatches.
            logger.warning(
                "OCR adaptive threshold fallback failed: %s",
                exc,
                exc_info=True,
            )
            return image_base64


__all__ = ["OCRProcessor"]
