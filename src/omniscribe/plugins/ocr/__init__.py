"""OCR plugin package — HTTP surface over the core ``OCRPipeline``.

The boot ``plugin`` instance lives in :mod:`omniscribe.plugins.ocr.plugin`;
this package keeps the public surface (schemas, events, bridge) importable
without side effects.
"""

from __future__ import annotations

from omniscribe.plugins.ocr.plugin import (
    OCRPlugin,
    OCRSchema,
    OCRService,
    OCRServiceImpl,
    build_ocr_router,
    plugin,
)

__all__ = [
    "OCRPlugin",
    "OCRSchema",
    "OCRService",
    "OCRServiceImpl",
    "build_ocr_router",
    "plugin",
]
