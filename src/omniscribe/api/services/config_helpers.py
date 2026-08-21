"""Per-route helpers for the config router.

Phase C: these lived inline in ``routers/config.py``. They have no
HTTP-aware behaviour — pure data plumbing over the ``ConfigStore``
Protocol — so they belong with the rest of the services.

Backwards-compat re-exports in ``routers/config.py`` keep the old import
path (``from omniscribe.api.routers.config import _load_config_from_store``)
working for in-tree tests and any out-of-tree importers.

The legacy module-level ``_config`` dict stays in ``routers/config.py``
because out-of-tree callers (``extraction.py``, ``provider_manager.py``,
``tasks.py``, etc.) read it directly. The helpers below lazy-import it
at call time so they keep writing through the same in-memory cache the
legacy code expects.
"""

from __future__ import annotations

import os
from typing import Any, cast

from omniscribe.api.services.config_store import ConfigStore

# ---------------------------------------------------------------------------
# Cross-worker persistence helpers (issue H1)
# ---------------------------------------------------------------------------
#
# The legacy ``_config`` dict is process-local. In a multi-worker
# uvicorn deployment, every worker keeps its own copy and a POST
# /api/config only mutates the receiving worker's copy — the other
# workers serve stale config until restart.
#
# The fix is to round-trip the dict through the StateBackend's
# ``config_store`` (a duck-typed attribute on every backend impl).
# When the active backend is cross-worker visible (Redis or SQLite),
# updates are written to the store and every worker sees the new
# value on its next read. When the active backend is the default
# in-memory one, the POST is refused with a 503 + a clear remediation
# message so operators do not see a silently-broken deployment
# (``is_cross_worker_visible()`` returns False; the helpers below
# raise :class:`ConfigBackendIncompatible` which the route handler
# converts to the 503 response).
#
# The legacy module-level ``_config`` dict remains in
# ``routers/config.py`` for two reasons:
#
# 1. Backward compat with code that already imports it (e.g.
#    ``extraction.py``, ``ocr.py``, ``translation.py``,
#    ``transcription.py``, ``provider_manager.py``). It is kept in
#    sync on every read and every write so those consumers always see
#    the latest values within the current process.
# 2. It is the canonical source of the env-derived seed values; the
#    store is lazily seeded from it on the first read so a freshly
#    constructed backend (which starts empty) still serves the
#    operator's environment-tuned defaults until the first POST.


class ConfigBackendIncompatible(Exception):
    """Raised when the active config store cannot propagate updates.

    The route handler catches this and returns 503 with
    :data:`CONFIG_BACKEND_INCOMPATIBLE_MESSAGE` so operators see a
    clear remediation hint instead of a silently-per-worker update.
    """


CONFIG_BACKEND_INCOMPATIBLE_MESSAGE = (
    "Config updates require a persistent state backend so all "
    "uvicorn workers see the same value. Set "
    "OMNISCRIBE_STATE_BACKEND=redis or =sqlite, then restart the server."
)


def _get_config_store() -> ConfigStore:
    """Return the active StateBackend's config store (lazy import).

    The lazy import avoids a circular import at module load
    (``routers.state`` and ``routers.config`` are both routers that
    may be imported by ``server.create_app`` in either order).
    """
    from omniscribe.api.routers import state as router_state

    return router_state.backend.config_store  # type: ignore[attr-defined, no-any-return]


def load_config_from_store() -> dict[str, Any]:
    """Refresh the local module dict from the config store.

    The store is the source of truth for cross-worker visibility. On
    the first read, the env-derived seed values in ``_config`` are
    written into the store so a freshly constructed backend serves
    the operator's environment defaults. Subsequent reads are
    straight ``get_snapshot()`` round-trips.
    """
    from omniscribe.api.routers import config as router_config  # lazy: avoid circular

    store = _get_config_store()
    snapshot = store.get_snapshot()
    if not snapshot:
        seed = cast(dict[str, Any], router_config._config)
        if seed:
            store.update(seed)
            snapshot = dict(seed)
    cache = cast(dict[str, Any], router_config._config)
    cache.clear()
    cache.update(snapshot)
    return cache


_CONFIG_KEY_TO_ENV: dict[str, str] = {
    "api_base": "LLM_API_BASE",
    "api_key": "LLM_API_KEY",
    "model": "LLM_MODEL",
    "ocr_api_base": "OCR_API_BASE",
    "ocr_api_key": "OCR_API_KEY",
    "ocr_model": "OCR_MODEL",
    "ocr_provider": "OCR_PROVIDER",
    "translation_api_base": "TRANSLATION_API_BASE",
    "translation_api_key": "TRANSLATION_API_KEY",
    "translation_model": "TRANSLATION_MODEL",
    "transcription_api_base": "OMNISCRIBE_TRANSCRIPTION_API_BASE",
    "transcription_api_key": "OMNISCRIBE_TRANSCRIPTION_API_KEY",
    "transcription_model": "OMNISCRIBE_TRANSCRIPTION_MODEL",
    "transcription_engine": "OMNISCRIBE_TRANSCRIPTION_ENGINE",
    "dense_mode": "OCR_DENSE_MODE",
    "pipeline_mode": "OCR_PIPELINE_MODE",
    "spellcheck": "OCR_SPELLCHECK",
    "concurrency": "OCR_CONCURRENCY",
    "dpi": "OCR_DPI",
    "dense_threshold": "OCR_DENSE_THRESHOLD",
    "max_image_dim": "OCR_MAX_IMAGE_DIM",
    "refine": "OCR_REFINE",
    "verify_model": "OCR_VERIFY_MODEL",
    "self_correction": "OCR_SELF_CORRECTION",
    "binarize": "OCR_BINARIZE",
    "dual_engine": "OCR_DUAL_ENGINE",
    "cross_page": "OCR_CROSS_PAGE",
    "preprocess_pages": "OCR_PREPROCESS_PAGES",
    "orientation_detection": "OCR_ORIENTATION_DETECTION",
    "deskew": "OCR_DESKEW",
    "denoise": "OCR_DENOISE",
    "normalize_contrast": "OCR_NORMALIZE_CONTRAST",
    "crop_cleanup": "OCR_CROP_CLEANUP",
    "quality_routing": "OCR_QUALITY_ROUTING",
    "quality_loop_enabled": "OMNISCRIBE_QUALITY_LOOP",
    "quality_target": "OMNISCRIBE_QUALITY_TARGET",
    "quality_max_retries": "OMNISCRIBE_QUALITY_MAX_RETRIES",
}


def persist_config(updates: dict[str, Any]) -> None:
    """Write ``updates`` to the config store, .env file, and refresh local cache."""
    from omniscribe.api.routers import config as router_config  # lazy: avoid circular

    store = _get_config_store()
    if not store.is_cross_worker_visible():
        raise ConfigBackendIncompatible(CONFIG_BACKEND_INCOMPATIBLE_MESSAGE)
    store.update(updates)
    cache = cast(dict[str, Any], router_config._config)
    cache.update(updates)

    env_updates: dict[str, Any] = {}
    for k, v in updates.items():
        if k in _CONFIG_KEY_TO_ENV:
            env_updates[_CONFIG_KEY_TO_ENV[k]] = v
    if "PYTEST_CURRENT_TEST" not in os.environ and env_updates:
        from omniscribe.utils.env import update_dotenv

        update_dotenv(env_updates)


# ---------------------------------------------------------------------------
# Masking helpers
# ---------------------------------------------------------------------------


def mask_api_key(value: str | None) -> str | None:
    """Return a ``<first4>...<last4>`` preview of the API key.

    Used both by the legacy ``GET /api/config`` and by the per-namespace
    ``GET /api/config/{ocr,translation}`` endpoints so the operator
    sees the same masked preview everywhere.
    """
    if not value or value == "lm-studio":
        return value
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


__all__ = [
    "CONFIG_BACKEND_INCOMPATIBLE_MESSAGE",
    "ConfigBackendIncompatible",
    "load_config_from_store",
    "mask_api_key",
    "persist_config",
]
