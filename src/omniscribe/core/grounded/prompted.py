"""Prompted grounded OCR backend (Qwen-VL and friends).

:class:`PromptedGroundedOCR` is the default grounded backend for any
OpenAI-compatible VLM that emits ``{"bbox_2d": [...], "content": "..."}``
JSON when prompted — confirmed for Qwen2.5-VL (line-level, wrapped in
fences) and Qwen3-VL (line-level, bare JSON). Should also work for
MiniCPM-V, InternVL, etc.

It handles its own rasterization (one VLM call per page) and emits
per-page progress; the OCRPipeline calls ``ocr_document(pdf_path)``
directly and lets this backend double as its own PDF loader.

Reuses :mod:`omniscribe.core.ocr.client` for ``ensure_model_loaded``
so a typo in ``--model`` fails fast with the same diagnostic as the
hybrid path (issue #7 — the grounded path was the original
reproducer for that bug class).
"""

from __future__ import annotations

import asyncio
import logging
import os

from openai import AsyncOpenAI

from omniscribe.core.grounded.models import (
    GroundedBlock,
    GroundedResponse,
    ProgressCallback,
    WarningCallback,
)
from omniscribe.core.grounded.parsers import _parse_grounded_json
from omniscribe.core.grounded.rasterize import _rasterize_to_jpeg_pages
from omniscribe.core.llm_client import call_llm
from omniscribe.core.ocr import (
    ModelNotLoadedError,
    _format_model_not_loaded,
    _list_loaded_model_ids,
    _model_in_loaded,
)
from omniscribe.core.ocr.resilience import (
    get_default_circuit_breaker_registry,
    is_transient_error,
)

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


def _extract_grounded_crops(
    b64: str, blocks: list[GroundedBlock], w: int, h: int
) -> None:
    if not any(b.label in ("image", "figure") for b in blocks):
        return
    import base64
    import io

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
                if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
                    cropped = img.crop(crop_box)
                    buf = io.BytesIO()
                    cropped.save(buf, format="PNG")
                    b.image_bytes = buf.getvalue()


class PromptedGroundedOCR:
    """Grounded backend built on an OpenAI-compatible vision LLM endpoint.

    Works with any VLM that emits ``{bbox_2d:[...], content:"..."}`` when asked.

    Usage::

        backend = PromptedGroundedOCR(
            api_base="http://localhost:1234/v1",
            model="qwen/qwen3-vl-8b",
        )
        pipe = OCRPipeline(pdf_handler=PDFHandler(), grounded_backend=backend)
        await pipe.run("in.pdf", "out.pdf")
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
        # Honor .env / environment overrides the same way OCRProcessor does,
        # so a user with `LLM_API_BASE` set in .env doesn't have to also pass
        # `--api-base` when switching to --grounded.
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
        # Same resilience policy as the hybrid OCRProcessor: retry
        # transient errors with backoff, fail fast once the endpoint is
        # deemed down. Env overrides: OMNISCRIBE_LLM_MAX_RETRIES,
        # OMNISCRIBE_LLM_RETRY_BASE_DELAY, OMNISCRIBE_CB_*.
        self.max_retries = int(os.getenv("OMNISCRIBE_LLM_MAX_RETRIES", "2"))
        self.retry_base_delay_s = float(
            os.getenv("OMNISCRIBE_LLM_RETRY_BASE_DELAY", "1.0")
        )
        self.circuit_breaker = get_default_circuit_breaker_registry().get_or_create(
            self.api_base, self.model
        )

    async def ensure_model_loaded(self) -> None:
        """Pre-flight check that ``self.model`` is loaded on the server.

        Mirrors :meth:`OCRProcessor.ensure_model_loaded` so users on
        ``--grounded`` get the same fail-fast safety net. The grounded
        path is in fact the path that originally surfaced this bug
        (issue #7) — the user had OlmOCR loaded but requested Qwen3-VL,
        and LM Studio silently served bad OCR from the wrong model.
        """
        client = AsyncOpenAI(base_url=self.api_base, api_key=self.api_key)
        loaded = await _list_loaded_model_ids(client, self.api_base)
        if not _model_in_loaded(self.model, loaded):
            raise ModelNotLoadedError(
                _format_model_not_loaded(self.api_base, self.model, loaded)
            )

    async def _call_with_retry(self, image_b64: str) -> str:
        """One grounded VLM page call with retry + circuit-breaker protection.

        Same policy as :meth:`OCRProcessor._chat`: transient failures are
        retried with exponential backoff (capped at 8s); permanent failures
        raise immediately; the shared circuit breaker fails fast once the
        endpoint is deemed down so remaining pages don't each burn a timeout.
        """
        await self.circuit_breaker.check()

        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                await self.circuit_breaker.check()
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
                                        "url": f"data:image/jpeg;base64,{image_b64}",
                                    },
                                },
                            ],
                        }
                    ],
                )
                await self.circuit_breaker.record_success()
                return text
            except Exception as e:
                last_exc = e
                await self.circuit_breaker.record_failure()
                if not is_transient_error(e):
                    break
                if attempt < self.max_retries:
                    delay = min(self.retry_base_delay_s * (2**attempt), 8.0)
                    logger.warning(
                        "Transient grounded OCR error (attempt %d/%d), "
                        "retrying in %.1fs: %s: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                        type(e).__name__,
                        e,
                    )
                    await asyncio.sleep(delay)

        assert last_exc is not None
        raise last_exc

    async def ocr_document(
        self,
        pdf_path: str,
        progress: ProgressCallback | None = None,
        on_warning: WarningCallback | None = None,
    ) -> GroundedResponse:
        # 1. Rasterize every page, remembering dimensions.
        # Offloaded to a worker thread — fitz.open / get_pixmap are blocking
        # CPU+IO work that would otherwise stall the event loop.
        page_imgs = await asyncio.to_thread(
            _rasterize_to_jpeg_pages,
            pdf_path,
            self.max_image_dim,
            self.dpi,
        )

        # 2. Call the VLM per page, streaming progress and isolating failures
        # so one bad page doesn't tank a multi-page document.
        sem = asyncio.Semaphore(max(1, self.concurrency))
        total_pages = len(page_imgs)

        async def run_one(
            page_idx: int,
        ) -> tuple[int, list[GroundedBlock], BaseException | None]:
            b64, w, h = page_imgs[page_idx]
            async with sem:
                try:
                    text = await self._call_with_retry(b64)
                    text = text.strip()
                    blocks = _parse_grounded_json(text, page_idx, w, h)

                    if any(b.label in ("image", "figure") for b in blocks):
                        await asyncio.to_thread(
                            _extract_grounded_crops, b64, blocks, w, h
                        )

                    return page_idx, blocks, None
                except Exception as e:
                    # Per-page isolation: log the failure and return zero
                    # blocks for this page so surviving pages still land in
                    # the output. The exception is bubbled up via the
                    # 3-tuple so the caller can surface it (e.g. via the
                    # pipeline's `on_warning` and the response's
                    # `failed_pages`).
                    logger.warning(
                        f"grounded OCR failed for page {page_idx}: "
                        f"{type(e).__name__}: {e}"
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

        # Flatten in page order for a stable, deterministic output.
        flat_blocks: list[GroundedBlock] = []
        for page_idx in range(total_pages):
            flat_blocks.extend(blocks_by_page.get(page_idx, []))
        return GroundedResponse(
            blocks=flat_blocks,
            page_sizes=[(w, h) for (_, w, h) in page_imgs],
            failed_pages=failed_pages,
        )


__all__ = ["DEFAULT_GROUNDING_PROMPT", "PromptedGroundedOCR"]
