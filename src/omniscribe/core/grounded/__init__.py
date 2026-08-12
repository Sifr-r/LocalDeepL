"""Grounded OCR — backends that emit text WITH bounding boxes in one call.

When a VLM can natively ground its output (Qwen2.5-VL, Qwen3-VL,
Florence-2, MinerU, Z.AI hosted GLM-OCR, etc.) the whole
Surya-detect → LLM-transcribe → DP-align → refine dance collapses
to a single call. The model returns a list of ``(bbox, text)``
pairs already bound together, and we just render the page
background and embed them.

Sub-package layout:

- :mod:`.models` — :class:`GroundedBlock`, :class:`GroundedResponse`,
  :class:`GroundedOCRBackend`, :data:`ProgressCallback`,
  :data:`WarningCallback`
- :mod:`.parsers` — :func:`parse_zai_response`,
  :func:`parse_glm_layout_details`, :func:`_parse_grounded_json`
  (and the shared regex/label helpers)
- :mod:`.rasterize` — :func:`_rasterize_to_jpeg_pages` (blocking;
  callers MUST run it on a worker thread)
- :mod:`.prompted` — :data:`DEFAULT_GROUNDING_PROMPT`,
  :class:`PromptedGroundedOCR` (Qwen-VL family default)

The pipeline picks this path automatically when ``grounded_backend``
is passed to :class:`OCRPipeline`; otherwise it falls back to the
hybrid Surya+LLM+DP flow.

This ``__init__`` re-exports the *public* surface exactly as it
appeared on the old ``omniscribe/core/grounded.py`` module so the
test suite (``tests/test_grounded.py``), the public root
``omniscribe/__init__.py``, and downstream callers (pipeline,
routers) keep working without modification.
"""

from __future__ import annotations

from omniscribe.core.grounded.models import (
    GroundedBlock,
    GroundedOCRBackend,
    GroundedResponse,
    ProgressCallback,
    WarningCallback,
)
from omniscribe.core.grounded.parsers import (
    _parse_grounded_json,
    log_grounded_parse_failure,
    parse_glm_layout_details,
)
from omniscribe.core.grounded.prompted import (
    DEFAULT_GROUNDING_PROMPT,
    PromptedGroundedOCR,
)
from omniscribe.core.grounded.rasterize import _rasterize_to_jpeg_pages

__all__ = [
    "DEFAULT_GROUNDING_PROMPT",
    "GroundedBlock",
    "GroundedOCRBackend",
    "GroundedResponse",
    "PromptedGroundedOCR",
    "ProgressCallback",
    "WarningCallback",
    # Underscore-prefixed names: still re-exported for tests that
    # lock in the parser contracts directly.
    "_parse_grounded_json",
    "_rasterize_to_jpeg_pages",
    "log_grounded_parse_failure",
    "parse_glm_layout_details",
]
