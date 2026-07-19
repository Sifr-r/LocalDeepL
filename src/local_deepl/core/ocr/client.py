"""Helpers for talking to OpenAI-compatible LLM endpoints.

Three responsibilities live here:

- :func:`_list_loaded_model_ids` — pre-flight query against
  ``GET /v1/models`` so we can verify the configured model is actually
  loaded before paying for image conversion / detection.
- :func:`_model_in_loaded` — case-insensitive membership check.
- :func:`_format_model_not_loaded` — consistent diagnostic message that
  names the loaded models and gives the user a way to fix the
  mismatch (LM Studio, ``--model``, ``--no-verify-model``).

These were extracted from ``core/ocr.py`` so the grounded OCR backend
in ``core/grounded/`` can reuse the same pre-flight check without
re-implementing the diagnostic format (which drifted the first time
around — we lost an entire round of "OCR is silently wrong" bug
reports to that drift).
"""

from __future__ import annotations

from openai import AsyncOpenAI

from local_deepl.core.ocr.exceptions import LLMCallError


async def _list_loaded_model_ids(client: AsyncOpenAI, api_base: str) -> list[str]:
    """Return model IDs loaded on an OpenAI-compatible server.

    Uses the SDK's ``client.models.list()`` (hits ``GET /v1/models``).
    Wraps any transport / auth / response-shape failure in
    :class:`LLMCallError` with the same diagnostic format ``_chat`` uses
    so the caller sees a consistent error message style across the
    pipeline's LLM-facing surfaces.
    """
    try:
        page = await client.models.list()
    except Exception as e:
        raise LLMCallError(
            f"Could not list models on {api_base}: "
            f"{type(e).__name__}: {e}\n"
            f"  - Is your local LLM server (LM Studio / Ollama / vLLM) running at "
            f"{api_base}?\n"
            f"  - Does it expose GET /v1/models? (Most do; some custom servers "
            f"don't — pass --no-verify-model to skip this check.)"
        ) from e
    return [m.id for m in page.data] if page.data else []


def _model_in_loaded(model: str, loaded: list[str]) -> bool:
    """Case-insensitive membership check against a server's loaded model list."""
    target = model.lower()
    return any(m.lower() == target for m in loaded)


def _format_model_not_loaded(api_base: str, model: str, loaded: list[str]) -> str:
    """Render the standard "model not loaded" diagnostic.

    Lists what's loaded, points the user at the CLI flag that names it,
    and explains why the error matters (LM Studio's silent fallback is
    the root cause of issue #7).
    """
    listing = "\n    ".join(loaded) if loaded else "(none)"
    return (
        f"Model {model!r} is not loaded on {api_base}.\n"
        f"  Loaded models:\n    {listing}\n"
        f"  Fix:\n"
        f"    - Load {model!r} in LM Studio (Models -> search -> Load), then retry.\n"
        f"    - Or pass --model with one of the loaded model IDs above.\n"
        f"    - Or pass --no-verify-model to skip this check "
        f"(e.g. on Ollama / vLLM, which auto-load on demand).\n"
        f"  Why this matters: LM Studio silently falls back to whatever model is "
        f"loaded when the requested one is missing, producing subtly wrong OCR "
        f"results with no error. (issue #7)"
    )


__all__ = [
    "_format_model_not_loaded",
    "_list_loaded_model_ids",
    "_model_in_loaded",
]
