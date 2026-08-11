"""Form-parameter resolution for the OCR upload endpoint.

The route handler ``POST /api/process`` accepts every tuning knob both as a
``Form`` field (per-request override) and as a key in the in-memory config
store (admin-set default). This module centralizes the "form field wins,
config falls back" merge so the route body stays focused on orchestration.

Why a service module (vs. a function on the router): the resolution rules
have grown to 24 string-typed fields; centralizing them keeps the router
readable and gives future endpoints (translation, batch re-process) a
single source of truth for "how do I parse incoming OCR settings".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeAlias

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
        # Phase 2 — trust layer knob; arrives on the form as a JSON-encoded
        # string and is parsed by ``ProcessSettings.validate_quality_options``.
        "quality_options": "quality_options",
    }


def collect_form_kwargs(
    **form_fields: str | None,
) -> dict[str, str | None]:
    """Collect all OCR process form fields into a single kwargs dict.

    The FastAPI route signatures declare 30 individual ``Form`` parameters
    (the 24 settings fields plus ``pages`` and a few meta fields). Instead of
    listing each by name at the resolver call site, the routes unpack a
    captured ``dict`` built by this helper. The dict only contains the keys
    that ``resolve_process_settings`` understands — extra Form fields
    (e.g. ``client_id``, ``progress_channel``) are ignored here and
    consumed by the route handler itself.

    Why a helper vs. a Pydantic model: every field arrives as
    ``str | None`` from multipart/form-data. Wrapping them in a
    Pydantic ``BaseModel`` would force stringly-typed validation that the
    resolver already performs downstream, and FastAPI's Form-binding rules
    (``Annotated[X, Form()]``) proved brittle for a 30-field model. A plain
    dict keeps the per-field schema loose (any caller can send any field)
    while centralizing the field name list in one place — :func:`_form_param_keys`.

    ``pages`` is intentionally NOT a special case in this helper. The
    resolver treats ``pages`` as a required, named kwarg (see
    :func:`resolve_process_settings`), so callers must pass it separately
    and unpack it via ``**collect_form_kwargs(...)`` before adding
    ``pages=pages`` to the resolver call.
    """
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


__all__ = ["resolve_process_settings"]
