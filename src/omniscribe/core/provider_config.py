"""Core-owned provider configuration types.

This module is the **canonical** definition of ``ProviderConfig`` and
``ProviderFormatEnum`` for the OCR pipeline, grounded backend, and
any other in-process consumer. The API layer (``omniscribe.api.*``)
imports from here and re-exports — it does not redefine the schema.

Why this module exists
----------------------
Prior to this module, ``core/llm_client.py`` and
``core/ocr/multi_format_client.py`` imported ``ProviderConfig`` and
``ProviderFormatEnum`` from ``omniscribe.api.schemas`` at runtime.
That inverted the documented layering (``core/`` is below ``api/``)
and meant any in-process caller (test, embedded workflow, Jupyter
notebook) doing ``from omniscribe.core.ocr import OCRProcessor``
dragged in the entire FastAPI / Pydantic / settings stack.

Defining the types here in ``core/`` (the lower layer) means
``core`` code can construct ``ProviderConfig`` instances without any
upward dependency. The API layer can still import this module and
add HTTP-bound validation (e.g. ``extra="forbid"`` on request models)
on top.

Note on filename
----------------
The audit's recommendation was ``omniscribe/core/providers.py`` but
that filename was already in use for the LLM provider catalog
(``LLMProvider`` dataclass + ``PROVIDERS_CATALOG`` list). Using a
distinct filename (``provider_config.py``) keeps the two concerns
separable; the LLM provider catalog is metadata about external
services, while this module is the runtime configuration type.

Compatibility
-------------
The field names and types are intentionally identical to the previous
``omniscribe.api.schemas.requests.ProviderConfig``. The default
``model_config`` is ``extra="ignore"`` (lenient) so that the API
layer can pass a Pydantic-validated instance and any extra fields
the API might add later are silently dropped at the core boundary
instead of raising.

The ``omniscribe.api.schemas.requests.ProviderConfig`` symbol is now
an alias of this class, so existing imports continue to work.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProviderFormatEnum(StrEnum):
    """Provider dispatch format.

    Mirrors the prior ``omniscribe.api.schemas.ProviderFormatEnum``
    values so the alias is a drop-in replacement.
    """

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC_COMPATIBLE = "anthropic_compatible"
    OLLAMA_COMPATIBLE = "ollama_compatible"


class ProviderConfig(BaseModel):
    """Canonical provider configuration used by the OCR pipeline.

    This is the lowest-layer definition; the API layer re-exports
    it (or subclasses it for additional request validation). Field
    names and types are stable contract.

    The model is intentionally lenient (``extra="ignore"``) so the
    API layer can pass a Pydantic-validated instance carrying extra
    fields without the core layer rejecting it.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    display_name: str
    format: ProviderFormatEnum
    api_url: str
    base_path: str = ""
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    supports_streaming: bool = True
    requires_auth: bool = True
    configured: bool = False
    enabled: bool = True


__all__ = [
    "ProviderConfig",
    "ProviderFormatEnum",
]
