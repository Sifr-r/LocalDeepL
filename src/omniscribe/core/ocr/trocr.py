"""TrOCR specialist engine for handwriting OCR.

TrOCR is loaded lazily on first use so the rest of the pipeline stays
importable without ``transformers`` installed.
"""

from __future__ import annotations

import logging
import threading
import typing
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrOCRResult:
    text: str
    confidence: float


class TrOCREngine:
    """Lazy wrapper around ``transformers`` TrOCR pipelines.

    The first call to :meth:`recognize` downloads the model (if not cached)
    and constructs the pipeline. Subsequent calls reuse the singleton.
    """

    def __init__(
        self,
        model_name: str = "microsoft/trocr-base-handwritten",
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self._device = device
        self._lock = threading.Lock()
        self._pipeline: typing.Any = None

    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure_loaded(self) -> None:
        if self._pipeline is not None:
            return
        with self._lock:
            if self._pipeline is not None:
                return
            try:
                import torch
                from transformers import (
                    AutoModelForCausalLM,
                    AutoProcessor,
                    pipeline,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "TrOCREngine requires the 'trocr' extra (transformers + torch)."
                ) from exc

            device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            processor = AutoProcessor.from_pretrained(self.model_name)
            model = AutoModelForCausalLM.from_pretrained(self.model_name).to(device)  # type: ignore
            pipeline_func = typing.cast(typing.Any, pipeline)
            self._pipeline = pipeline_func(
                "image-to-text",
                model=model,
                image_processor=processor.image_processor,
                tokenizer=processor.tokenizer,
                device=0 if device == "cuda" else -1,
            )
            logger.info(
                "TrOCREngine loaded model=%s device=%s", self.model_name, device
            )

    async def recognize(self, image_bytes: bytes) -> TrOCRResult:
        """Recognize text in a single image (PNG/JPEG bytes)."""
        import asyncio
        import io

        from PIL import Image

        self._ensure_loaded()

        def _run() -> TrOCRResult:
            assert self._pipeline is not None
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            out = self._pipeline(image)
            text = ""
            confidence = 0.0
            if isinstance(out, list) and out:
                first = out[0]
                if isinstance(first, dict):
                    text = str(first.get("generated_text", ""))
                    # TrOCR does not expose token-level probs through the
                    # default pipeline; fall back to a length/word heuristic.
                    confidence = _heuristic_confidence(text)
            return TrOCRResult(text=text.strip(), confidence=confidence)

        return await asyncio.to_thread(_run)


def _heuristic_confidence(text: str) -> float:
    """Cheap confidence proxy for TrOCR output.

    Returns a value in [0, 1] based on:
    - non-empty (small bonus)
    - contains a vowel / CJK character (penalty if not — likely garbage)
    - has at least one space or CJK char (suggesting it's "real" text)
    """
    if not text:
        return 0.0
    stripped = text.strip()
    has_vowel = any(c in "aeiouyAEIOUY" for c in stripped)
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in stripped)
    has_arabic = any("\u0600" <= c <= "\u06ff" for c in stripped)
    if not (has_vowel or has_cjk or has_arabic):
        return 0.2
    word_count = len(stripped.split())
    if word_count >= 3:
        return 0.85
    if word_count >= 1:
        return 0.7
    return 0.4
