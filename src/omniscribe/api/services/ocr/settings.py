"""Form-parameter resolution for the OCR upload endpoint.

The route handler ``POST /api/process`` accepts every tuning knob both as a
``Form`` field (per-request override) and as a key in the in-memory config
store (admin-set default). This module centralizes the "form field wins,
config falls back" merge so the route body stays focused on orchestration.

Why a service module (vs. a function on the router): the resolution rules
have grown to 24+ string-typed fields; centralizing them keeps the router
readable and gives future endpoints (translation, batch re-process) a
single source of truth for "how do I parse incoming OCR settings".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from fastapi import Form

from omniscribe.api.schemas import ProcessSettings

# `settings_dict` is the in-memory config store keyed by the same names
# as ProcessSettings field names. Re-aliased here so callers don't need
# a separate `api.routers.config` import just to type-hint the dict.
#
# Typed as ``Mapping[str, Any]`` (rather than ``dict[str, Any]``) so the
# TypedDict ``RuntimeConfigDict`` from ``routers.config`` is structurally
# compatible at the ``resolve_process_settings(...)`` call site. TypedDicts
# are dict subclasses at runtime, so ``.get(field)`` below works on both
# shapes without a cast.
SettingsDict: TypeAlias = Mapping[str, Any]


@dataclass
class OCRProcessForm:
    """Reusable Form dependency encapsulating OCR tuning knobs and request options.

    Groups the 30+ multipart/form-data parameters for ``/api/process`` and
    ``/api/process/async`` into a single dependency to eliminate parameter repetition.
    """

    client_id: str | None = Form(None)  # accepted for backward compat
    progress_channel: str | None = Form(None)
    progress_token: str | None = Form(None)
    api_base: str | None = Form(None)
    api_key: str | None = Form(None)
    model: str | None = Form(None)
    pipeline_mode: str | None = Form(None)
    dpi: str | None = Form(None)
    concurrency: str | None = Form(None)
    dense_mode: str | None = Form(None)
    dense_threshold: str | None = Form(None)
    pages: str | None = Form(None)
    refine: str | None = Form(None)
    max_image_dim: str | None = Form(None)
    self_correction: str | None = Form(None)
    binarize: str | None = Form(None)
    dual_engine: str | None = Form(None)
    spellcheck: str | None = Form(None)
    cross_page: str | None = Form(None)
    preprocess_pages: str | None = Form(None)
    orientation_detection: str | None = Form(None)
    deskew: str | None = Form(None)
    denoise: str | None = Form(None)
    normalize_contrast: str | None = Form(None)
    crop_cleanup: str | None = Form(None)
    quality_routing: str | None = Form(None)
    document_processors: str | None = Form(None)
    handwriting_hint: str | None = Form(None)
    chunk_pages: str | None = Form(None)
    # Phase 2 — optional trust-layer configuration (JSON-encoded). When the
    # frontend's TrustPanel is open, the front-end posts a JSON object string
    # here; when closed, the field is omitted and the trust layer stays off.
    quality_options: str | None = Form(None)
    # P1 — quality repair loop knobs (spec §3.2). Omitted fields fall
    # back to the env-seeded runtime config; the API-level defaults
    # enable the loop (target 0.98, two repair passes).
    quality_loop_enabled: str | None = Form(None)
    quality_target: str | None = Form(None)
    quality_max_retries: str | None = Form(None)

    def to_dict(self) -> dict[str, str | None]:
        """Return a dict of all form fields."""
        return {k: v for k, v in vars(self).items() if not k.startswith("_")}


def _form_param_keys() -> dict[str, str]:
    """Return the mapping from ProcessSettings field name → HTTP Form key.

    Single source of truth so the FastAPI route signature and the
    resolver below can't drift apart on field naming.
    """
    return {
        "api_base": "api_base",
        "api_key": "api_key",
        "model": "model",
        "pipeline_mode": "pipeline_mode",
        "dpi": "dpi",
        "concurrency": "concurrency",
        "dense_mode": "dense_mode",
        "dense_threshold": "dense_threshold",
        "refine": "refine",
        "max_image_dim": "max_image_dim",
        "self_correction": "self_correction",
        "binarize": "binarize",
        "dual_engine": "dual_engine",
        "spellcheck": "spellcheck",
        "cross_page": "cross_page",
        "preprocess_pages": "preprocess_pages",
        "orientation_detection": "orientation_detection",
        "deskew": "deskew",
        "denoise": "denoise",
        "normalize_contrast": "normalize_contrast",
        "crop_cleanup": "crop_cleanup",
        "quality_routing": "quality_routing",
        "document_processors": "document_processors",
        "handwriting_hint": "handwriting_hint",
        "chunk_pages": "chunk_pages",
        # Phase 2 — trust layer knob; arrives on the form as a JSON-encoded
        # string and is parsed by ``ProcessSettings.validate_quality_options``.
        "quality_options": "quality_options",
        # P1 — quality repair loop knobs (spec §3.2); plain form fields
        # coerced by ``ProcessSettings`` lax validation.
        "quality_loop_enabled": "quality_loop_enabled",
        "quality_target": "quality_target",
        "quality_max_retries": "quality_max_retries",
    }


def collect_form_kwargs(
    form: Any = None,
    **form_fields: str | None,
) -> dict[str, str | None]:
    """Collect all OCR process form fields into a single kwargs dict.

    Accepts a model with a ``model_dump`` method, an :class:`OCRProcessForm`,
    a dict, or plain keyword args, and extracts only the settings fields that
    :func:`resolve_process_settings` understands.
    """
    if form is not None:
        if hasattr(form, "to_dict"):
            form_fields = {**form.to_dict(), **form_fields}
        elif hasattr(form, "model_dump"):
            form_fields = {**form.model_dump(), **form_fields}
        elif hasattr(form, "__dict__"):
            form_fields = {**vars(form), **form_fields}
        elif isinstance(form, dict):
            form_fields = {**form, **form_fields}

    keys = _form_param_keys()
    return {
        form_key: form_fields.get(form_key)
        for form_key in keys.values()
        if form_key in form_fields
    }


def resolve_process_settings(
    *,
    settings_store: SettingsDict,
    pages: str | None,
    **form_params: str | None,
) -> ProcessSettings:
    """Merge ``Form`` overrides with the in-memory config and return validated settings.

    - ``form_params`` values win when present.
    - Falls back to ``settings_store`` key when a form value is ``None``.
    - ``pages`` is the special case: it does NOT fall back to the
      config store — callers always pass it explicitly (the form
      override semantics here would be confusing, since omitting the
      form field would silently mean "process all pages" only when
      there's no admin-set default, which makes the request ambiguous).
    - Pydantic fills any remaining gaps with the schema defaults.

    Validation errors propagate as :class:`pydantic.ValidationError`
    so the caller can render a 422 response.
    """
    keys = _form_param_keys()
    merged: dict[str, Any] = {}
    for field, form_key in keys.items():
        value = form_params.get(form_key)
        if value is not None:
            merged[field] = value
            continue
        fallback = settings_store.get(field)
        if fallback is not None:
            merged[field] = fallback
    merged["pages"] = pages
    return ProcessSettings.model_validate(merged)


__all__ = ["OCRProcessForm", "collect_form_kwargs", "resolve_process_settings"]
