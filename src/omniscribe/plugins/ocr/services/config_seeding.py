"""Initial ``/api/config`` store seeding for the OCR service.

Extracted from ``plugins/ocr/service.py`` in Phase 3.8 (4.8,
2026-09-05). Owns the canonical configuration key catalogue and the
seeded defaults that ``OCRServiceImpl`` reads on construction.

The catalogue is documented inline; new keys must be added to both
:data:`_CONFIG_KEY_SET` (for the GET-response allow-list) and the
``_seed_config`` return value (for the boot-time default) in the same
patch — there is no automated check that one stays in sync with the
other.

Public surface:

- :func:`seed_config` — the single public entry point. Returns a
  dict with the canonical keys populated from ``RuntimeSettings`` plus
  the historical defaults.
- :data:`CONFIG_KEY_SET` — re-exported under a non-underscore name
  for callers (and tests) that want to iterate the catalogue.
"""

from __future__ import annotations

from typing import Any

from omniscribe.config import RuntimeSettings

#: Canonical set of keys exposed by ``/api/config`` and seeded in
#: :func:`seed_config`.
#:
#: Documents the exposed configuration keys across endpoints, pipeline
#: tunables, and feature flags:
#:
#: 1. ``api_base``: Base URL of the OpenAI-compatible VLM endpoint (e.g. LM Studio, Ollama).
#: 2. ``api_key``: Authentication key for the VLM endpoint (masked as ``******`` in GET responses).
#: 3. ``model``: Target VLM model identifier loaded on the inference server.
#: 4. ``concurrency``: Number of PDF pages rasterized and processed concurrently.
#: 5. ``dpi``: Target rasterization resolution (DPI) for PDF rendering.
#: 6. ``dense_mode``: Handling strategy for dense pages ('auto', 'always', 'never').
#: 7. ``dense_threshold``: Bounding-box threshold above which dense mode activates.
#: 8. ``max_image_dim``: Maximum pixel dimension for page images fed to the VLM.
#: 9. ``refine``: Re-align sparse OCR text back to bounding boxes using dynamic programming.
#: 10. ``verify_model``: Pre-flight check verifying the requested model is loaded on the VLM server.
#: 11. ``pipeline_mode``: OCR execution pipeline ('hybrid' with Surya or bbox-native 'grounded').
#: 12. ``self_correction``: Automatic re-prompting pass for low-confidence OCR pages.
#: 13. ``binarize``: Binarize scanned document images to enhance high-contrast text.
#: 14. ``dual_engine``: Execute both hybrid and grounded engines in parallel and merge outputs.
#: 15. ``spellcheck``: Post-OCR dictionary spellcheck mode ('none', 'auto', or ISO language code).
#: 16. ``cross_page``: Multi-page cross-page text alignment and paragraph flow reconciliation.
#: 17. ``preprocess_pages``: Master toggle for page preprocessing transforms before OCR.
#: 18. ``orientation_detection``: Automatic detection and correction of 90/180/270 degree rotation.
#: 19. ``deskew``: Image deskewing to straighten tilted or rotated scans.
#: 20. ``denoise``: Noise reduction filtering to eliminate scan artifacts.
#: 21. ``normalize_contrast``: Dynamic contrast adjustment for low-contrast or faded documents.
#: 22. ``crop_cleanup``: Margin cropping and border artifact cleanup.
#: 23. ``quality_routing``: Route pages based on image quality analysis.
#: 24. ``document_processors``: Enabled post-OCR document analysis processors (e.g. reading order).
CONFIG_KEY_SET: frozenset[str] = frozenset(
    {
        "api_base",
        "api_key",
        "model",
        "concurrency",
        "dpi",
        "dense_mode",
        "dense_threshold",
        "max_image_dim",
        "refine",
        "verify_model",
        "pipeline_mode",
        "self_correction",
        "binarize",
        "dual_engine",
        "spellcheck",
        "cross_page",
        "preprocess_pages",
        "orientation_detection",
        "deskew",
        "denoise",
        "normalize_contrast",
        "crop_cleanup",
        "quality_routing",
        "document_processors",
    }
)


def seed_config(settings: RuntimeSettings) -> dict[str, Any]:
    """Initial ``/api/config`` store: LLM coordinates from settings, the
    rest at their historical workstation defaults.

    Seeds the canonical configuration keys defined in
    :data:`CONFIG_KEY_SET`. See :data:`CONFIG_KEY_SET` for the
    detailed description of each exposed key.
    """
    return {
        "api_base": settings.llm_api_base,
        "api_key": settings.llm_api_key,
        "model": settings.llm_model,
        "concurrency": 3,
        "dpi": 192,
        "dense_mode": "auto",
        "dense_threshold": 150,
        "max_image_dim": 1024,
        "refine": True,
        "verify_model": True,
        "pipeline_mode": "hybrid",
        "self_correction": False,
        "binarize": False,
        "dual_engine": False,
        "spellcheck": "none",
        "cross_page": False,
        "preprocess_pages": False,
        "orientation_detection": False,
        "deskew": False,
        "denoise": False,
        "normalize_contrast": False,
        "crop_cleanup": False,
        "quality_routing": False,
        "document_processors": [],
    }


__all__ = ["CONFIG_KEY_SET", "seed_config"]
