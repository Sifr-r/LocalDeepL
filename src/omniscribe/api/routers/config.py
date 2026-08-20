# ruff: noqa: E402
import logging
import math
import os
from typing import TYPE_CHECKING, Any, TypedDict, cast

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.api.schemas import (
    AuthTokenUpdate,
    ConfigUpdate,
    OcrConfigUpdate,
    TranslationConfigUpdate,
)
from omniscribe.api.services.config_store import ConfigStore
from omniscribe.api.services.security import SAFE_API_BASE_ERROR, SERVER_ERROR_MESSAGE
from omniscribe.api.services.security_config import (
    ABSOLUTE_MAX_UPLOAD_MB,
    DEFAULT_MAX_UPLOAD_MB,
    SecuritySettings,
)
from omniscribe.core.translation_config import (
    DEFAULT_TRANSLATION_API_BASE,
    DEFAULT_TRANSLATION_API_KEY,
    DEFAULT_TRANSLATION_MODEL,
    TranslationSettings,
)
from omniscribe.utils.security import is_ssrf_target

if TYPE_CHECKING:
    from omniscribe.api.services.ai import AIRequestSettings

router = APIRouter()
logger = logging.getLogger(__name__)


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        logger.warning("Ignoring invalid integer environment value for %s", name)
        return default
    if (minimum is not None and parsed < minimum) or (
        maximum is not None and parsed > maximum
    ):
        logger.warning(
            "Ignoring out-of-range integer environment value for %s: %s",
            name,
            value,
        )
        return default
    return parsed


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        logger.warning("Ignoring invalid float environment value for %s", name)
        return default
    # NaN/inf parse fine but would poison downstream validation (e.g. a
    # NaN quality target makes every block a permanent repair candidate).
    if (
        not math.isfinite(parsed)
        or (minimum is not None and parsed < minimum)
        or (maximum is not None and parsed > maximum)
    ):
        logger.warning(
            "Ignoring out-of-range float environment value for %s: %s",
            name,
            value,
        )
        return default
    return parsed


class RuntimeConfigDict(TypedDict, total=False):
    api_base: str
    api_key: str
    model: str
    concurrency: int
    dpi: int
    dense_mode: str
    dense_threshold: int
    max_image_dim: int
    refine: bool
    verify_model: bool
    pipeline_mode: str
    self_correction: bool
    binarize: bool
    dual_engine: bool
    spellcheck: str
    cross_page: bool
    preprocess_pages: bool
    orientation_detection: bool
    deskew: bool
    denoise: bool
    normalize_contrast: bool
    crop_cleanup: bool
    quality_routing: bool
    quality_loop_enabled: bool
    quality_target: float
    quality_max_retries: int
    document_processors: list[str]
    transcription_api_base: str
    transcription_api_key: str
    transcription_model: str
    transcription_engine: str
    transcription_language: str
    transcription_prompt: str
    transcription_temperature: float


# ---------------------------------------------------------------------------
# In-memory configuration store – initialised from environment variables
# ---------------------------------------------------------------------------
_config: RuntimeConfigDict = {
    "api_base": os.getenv("LLM_API_BASE", DEFAULT_TRANSLATION_API_BASE),
    "api_key": os.getenv("LLM_API_KEY", DEFAULT_TRANSLATION_API_KEY),
    "model": os.getenv("LLM_MODEL", DEFAULT_TRANSLATION_MODEL),
    "concurrency": _env_int("OCR_CONCURRENCY", 3),
    "dpi": _env_int("OCR_DPI", 200),
    "dense_mode": os.getenv("OCR_DENSE_MODE", "auto"),
    "dense_threshold": _env_int("OCR_DENSE_THRESHOLD", 60),
    "max_image_dim": _env_int("OCR_MAX_IMAGE_DIM", 1024),
    "refine": _env_bool("OCR_REFINE", True),
    "verify_model": _env_bool("OCR_VERIFY_MODEL", True),
    "pipeline_mode": os.getenv("OCR_PIPELINE_MODE", "hybrid"),
    "self_correction": _env_bool("OCR_SELF_CORRECTION", False),
    "binarize": _env_bool("OCR_BINARIZE", False),
    "dual_engine": _env_bool("OCR_DUAL_ENGINE", False),
    "spellcheck": os.getenv("OCR_SPELLCHECK", "none"),
    "cross_page": _env_bool("OCR_CROSS_PAGE", False),
    "preprocess_pages": _env_bool("OCR_PREPROCESS_PAGES", False),
    "orientation_detection": _env_bool("OCR_ORIENTATION_DETECTION", False),
    "deskew": _env_bool("OCR_DESKEW", False),
    "denoise": _env_bool("OCR_DENOISE", False),
    "normalize_contrast": _env_bool("OCR_NORMALIZE_CONTRAST", False),
    "crop_cleanup": _env_bool("OCR_CROP_CLEANUP", False),
    "quality_routing": _env_bool("OCR_QUALITY_ROUTING", False),
    "quality_loop_enabled": _env_bool("OMNISCRIBE_QUALITY_LOOP", True),
    # Bounds mirror ProcessSettings.quality_target / quality_max_retries;
    # the store fallback bypasses schema validation, so seeds must be
    # pre-validated or every plain /api/process request would 422.
    "quality_target": _env_float(
        "OMNISCRIBE_QUALITY_TARGET", 0.98, minimum=0.5, maximum=1.0
    ),
    "quality_max_retries": _env_int(
        "OMNISCRIBE_QUALITY_MAX_RETRIES", 2, minimum=0, maximum=5
    ),
    "document_processors": [],
    "transcription_api_base": os.getenv(
        "OMNISCRIBE_TRANSCRIPTION_API_BASE",
        os.getenv("LLM_API_BASE", "https://api.openai.com/v1"),
    ),
    "transcription_api_key": os.getenv(
        "OMNISCRIBE_TRANSCRIPTION_API_KEY", os.getenv("LLM_API_KEY", "")
    ),
    "transcription_model": os.getenv("OMNISCRIBE_TRANSCRIPTION_MODEL", "whisper-1"),
    "transcription_engine": os.getenv("OMNISCRIBE_TRANSCRIPTION_ENGINE", "api"),
    "transcription_language": os.getenv("OMNISCRIBE_TRANSCRIPTION_LANGUAGE", ""),
    "transcription_prompt": os.getenv("OMNISCRIBE_TRANSCRIPTION_PROMPT", ""),
    "transcription_temperature": float(
        os.getenv("OMNISCRIBE_TRANSCRIPTION_TEMPERATURE", "0.0")
    ),
}


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
# raise :class:`_ConfigBackendIncompatible` which the route handler
# converts to the 503 response).
#
# The legacy module-level ``_config`` dict remains in place for two
# reasons:
#
# 1. Backward compat with code that already imports it (e.g.
#    ``extraction.py``, ``ocr.py``, ``translation.py``,
#    ``transcription.py``). It is kept in sync on every read and
#    every write so those consumers always see the latest values
#    within the current process.
# 2. It is the canonical source of the env-derived seed values; the
#    store is lazily seeded from it on the first read so a freshly
#    constructed backend (which starts empty) still serves the
#    operator's environment-tuned defaults until the first POST.


class _ConfigBackendIncompatible(Exception):
    """Raised when the active config store cannot propagate updates.

    The route handler catches this and returns 503 with
    :data:`_CONFIG_BACKEND_INCOMPATIBLE_MESSAGE` so operators see a
    clear remediation hint instead of a silently-per-worker update.
    """


_CONFIG_BACKEND_INCOMPATIBLE_MESSAGE = (
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


def _load_config_from_store() -> dict[str, Any]:
    """Refresh the local module dict from the config store.

    The store is the source of truth for cross-worker visibility. On
    the first read, the env-derived seed values in ``_config`` are
    written into the store so a freshly constructed backend serves
    the operator's environment defaults. Subsequent reads are
    straight ``get_snapshot()`` round-trips.
    """
    store = _get_config_store()
    snapshot = store.get_snapshot()
    if not snapshot:
        seed = cast(dict[str, Any], _config)
        if seed:
            store.update(seed)
            snapshot = dict(seed)
    cache = cast(dict[str, Any], _config)
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


def _persist_config(updates: dict[str, Any]) -> None:
    """Write ``updates`` to the config store, .env file, and refresh local cache."""
    store = _get_config_store()
    if not store.is_cross_worker_visible():
        raise _ConfigBackendIncompatible(_CONFIG_BACKEND_INCOMPATIBLE_MESSAGE)
    store.update(updates)
    cache = cast(dict[str, Any], _config)
    cache.update(updates)

    env_updates: dict[str, Any] = {}
    for k, v in updates.items():
        if k in _CONFIG_KEY_TO_ENV:
            env_updates[_CONFIG_KEY_TO_ENV[k]] = v
    if "PYTEST_CURRENT_TEST" not in os.environ and env_updates:
        from omniscribe.utils.env import update_dotenv

        update_dotenv(env_updates)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_api_key(value: str | None) -> str | None:
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


def _is_masked_placeholder(value: object) -> bool:
    """Return True for the masked preview shape the GET endpoints return."""
    return isinstance(value, str) and ("..." in value or value == "********")


class _SSRFRejected(Exception):
    """Internal signal that ``api_base`` failed SSRF validation.

    Allows the route handler to convert the rejection into a 403
    response with the shared error envelope (``{"error": "..."}``),
    matching the legacy ``POST /api/config`` contract.
    """


async def _is_ssrf(value: str) -> bool:
    """Async shim so the in-memory patch path can mock the SSRF check.

    Returns True when :func:`is_ssrf_target` flags the URL as
    blocked. Wraps the structured :class:`SSRFCheckResult` into a
    bool for the in-route ``if await _is_ssrf(val):`` callers.
    """
    return not (await is_ssrf_target(value)).allowed


# ---------------------------------------------------------------------------
# Settings resolvers — core code should never poke ``_config`` directly.
# ---------------------------------------------------------------------------


def get_translation_settings() -> TranslationSettings:
    """Return core-owned settings for the optional async translation workflow.

    Namespaced ``translation_*`` keys win over the legacy ``api_*`` keys
    when both are set; the namespaced values persist the operator's
    intentional split without being silently clobbered by a legacy
    POST.

    Reads go through the config store (see
    :func:`_load_config_from_store`) so a value written by another
    worker is visible here in a multi-worker deployment.
    """
    config = _load_config_from_store()
    merged = dict(config)
    for key in ("api_base", "api_key", "model"):
        namespaced = config.get(f"translation_{key}")
        if isinstance(namespaced, str) and namespaced.strip():
            merged[key] = namespaced
    return TranslationSettings.from_mapping(merged)


def get_ocr_settings() -> "AIRequestSettings":
    """Return AI request settings for the OCR pipeline.

    Namespaced ``ocr_*`` keys win over the legacy ``api_*`` keys when
    both are set. Imported lazily to avoid a circular import
    ``api.services.ai -> api.routers.config`` at module load time.

    Reads go through the config store (see
    :func:`_load_config_from_store`) so a value written by another
    worker is visible here in a multi-worker deployment.
    """
    from omniscribe.api.services.ai import AIRequestSettings

    config = _load_config_from_store()
    merged = dict(config)
    for key in ("api_base", "api_key", "model"):
        namespaced = config.get(f"ocr_{key}")
        if isinstance(namespaced, str) and namespaced.strip():
            merged[key] = namespaced
    return AIRequestSettings(
        api_base=merged["api_base"],
        api_key=merged["api_key"],
        model=merged["model"],
    )


# ---------------------------------------------------------------------------
# Legacy /api/config
# ---------------------------------------------------------------------------


def _build_legacy_view() -> dict[str, Any]:
    """Return the legacy config payload with API key masked + upload cap surfaced.

    Reads go through the config store so a value written by another
    worker is visible here in a multi-worker deployment.
    """
    config = _load_config_from_store()
    payload = dict(config)
    payload["api_key"] = _mask_api_key(payload.get("api_key"))
    settings = SecuritySettings.from_env()
    payload["max_upload_bytes"] = settings.max_upload_bytes
    payload["max_upload_mb"] = settings.max_upload_bytes // (1024 * 1024)
    payload["max_upload_env"] = _max_upload_env_raw()
    return payload


def _max_upload_env_raw() -> str:
    """Return the raw string passed to ``OMNISCRIBE_MAX_UPLOAD_MB``.

    Empty string when unset. The Settings tab uses this to render an
    "operator override in effect" hint.
    """
    return (os.getenv("OMNISCRIBE_MAX_UPLOAD_MB") or "").strip()


@router.get("/api/config")
async def get_config():
    """Return the current runtime configuration, masking the API key.

    The payload also surfaces the operator-visible upload cap
    (``max_upload_bytes``, ``max_upload_mb``, ``max_upload_env``) so
    the Settings tab can render the documented 10 GB default.
    """
    return JSONResponse(content=_build_legacy_view())


@router.post("/api/config")
async def update_config(body: ConfigUpdate):
    """Update configuration.

    Mutates the legacy ``api_*`` keys, OCR knobs, and any nested
    namespace updates provided in ``ocr``, ``translation``, or
    ``transcription``.
    """
    values = body.model_dump(exclude_unset=True)
    if "api_base" in values and not (await is_ssrf_target(values["api_base"])).allowed:
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    # Drop masked-placeholders before persisting — keeping them would
    # overwrite a real key with the "ab..wxyz" preview the GET endpoints
    # return.
    updates: dict[str, Any] = {}
    for key, val in values.items():
        if key in ("ocr", "translation", "transcription"):
            if isinstance(val, dict):
                for sub_k, sub_v in val.items():
                    if not (isinstance(sub_v, str) and _is_masked_placeholder(sub_v)):
                        updates[sub_k] = (
                            sub_v.value if hasattr(sub_v, "value") else sub_v
                        )
            continue
        if key == "api_key" and isinstance(val, str) and _is_masked_placeholder(val):
            continue
        updates[key] = val.value if hasattr(val, "value") else val
    try:
        _persist_config(updates)
    except _ConfigBackendIncompatible as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    return JSONResponse(content=_build_legacy_view())


# ---------------------------------------------------------------------------
# Per-namespace /api/config/{ocr,translation}
# ---------------------------------------------------------------------------


async def _build_ocr_update(body: OcrConfigUpdate) -> dict[str, Any]:
    """Validate the OCR-namespace update and return the values to persist.

    Returns the subset of ``body`` keys that should land in the store
    (masked-placeholders and SSRF-rejected bases are dropped). Raises
    :class:`_SSRFRejected` when ``ocr_api_base`` fails SSRF validation
    so the route handler can convert it to a 403 response.
    """
    values = body.model_dump(exclude_unset=True)
    updates: dict[str, Any] = {}
    for key, val in values.items():
        if key == "ocr_api_key" and _is_masked_placeholder(val):
            continue
        if key == "ocr_api_base" and isinstance(val, str) and await _is_ssrf(val):
            raise _SSRFRejected
        if key == "document_processors" and isinstance(val, list):
            updates[key] = [p.value if hasattr(p, "value") else p for p in val]
            continue
        updates[key] = val
    return updates


def _build_translation_update(body: TranslationConfigUpdate) -> dict[str, Any]:
    """Validate the translation-namespace update and return the values to persist.

    Masked-placeholders are dropped so a re-post of the GET view does
    not clobber the real key.
    """
    values = body.model_dump(exclude_unset=True)
    updates: dict[str, Any] = {}
    for key, val in values.items():
        if key == "translation_api_key" and _is_masked_placeholder(val):
            continue
        updates[key] = val
    return updates


@router.get("/api/config/ocr")
async def get_ocr_namespace_config():
    """Return the OCR-namespace view with the API key masked."""
    config = _load_config_from_store()
    return JSONResponse(
        content={
            "ocr_api_base": config.get("ocr_api_base"),
            "ocr_api_key": _mask_api_key(config.get("ocr_api_key")),
            "ocr_model": config.get("ocr_model"),
            "ocr_provider": config.get("ocr_provider"),
        }
    )


@router.post("/api/config/ocr")
async def update_ocr_namespace_config(body: OcrConfigUpdate):
    """Persist the OCR-namespace update and return the masked view.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503.
    """
    try:
        updates = await _build_ocr_update(body)
    except _SSRFRejected:
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    try:
        _persist_config(updates)
    except _ConfigBackendIncompatible as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    config = _load_config_from_store()
    return JSONResponse(
        content={
            "ocr_api_base": config.get("ocr_api_base"),
            "ocr_api_key": _mask_api_key(config.get("ocr_api_key")),
            "ocr_model": config.get("ocr_model"),
            "ocr_provider": config.get("ocr_provider"),
        }
    )


@router.get("/api/config/translation")
async def get_translation_namespace_config():
    """Return the translation-namespace view with the API key masked."""
    config = _load_config_from_store()
    return JSONResponse(
        content={
            "translation_api_base": config.get("translation_api_base"),
            "translation_api_key": _mask_api_key(config.get("translation_api_key")),
            "translation_model": config.get("translation_model"),
            "translation_provider": config.get("translation_provider"),
            "sliding_window_words": config.get("sliding_window_words"),
            "dual_translate": config.get("dual_translate"),
        }
    )


@router.post("/api/config/translation")
async def update_translation_namespace_config(body: TranslationConfigUpdate):
    """Persist the translation-namespace update and return the masked view.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503.
    """
    updates = _build_translation_update(body)
    try:
        _persist_config(updates)
    except _ConfigBackendIncompatible as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    config = _load_config_from_store()
    return JSONResponse(
        content={
            "translation_api_base": config.get("translation_api_base"),
            "translation_api_key": _mask_api_key(config.get("translation_api_key")),
            "translation_model": config.get("translation_model"),
            "translation_provider": config.get("translation_provider"),
            "sliding_window_words": config.get("sliding_window_words"),
            "dual_translate": config.get("dual_translate"),
        }
    )


# ---------------------------------------------------------------------------
# Per-namespace auth-token updates
# ---------------------------------------------------------------------------


@router.post("/api/config/ocr/auth")
async def update_ocr_auth_token(body: AuthTokenUpdate):
    """Persist the per-namespace OCR auth token. ``None`` clears it.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503.
    """
    try:
        _persist_config({"ocr_auth_token": body.auth_token})
    except _ConfigBackendIncompatible as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    return JSONResponse(content={"ocr_auth_token": body.auth_token})


@router.post("/api/config/translation/auth")
async def update_translation_auth_token(body: AuthTokenUpdate):
    """Persist the per-namespace translation auth token. ``None`` clears it.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503.
    """
    try:
        _persist_config({"translation_auth_token": body.auth_token})
    except _ConfigBackendIncompatible as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    return JSONResponse(content={"translation_auth_token": body.auth_token})


@router.post("/api/config/transcription/auth")
async def update_transcription_auth_token(body: AuthTokenUpdate):
    """Persist the per-namespace transcription auth token. ``None`` clears it.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503.
    """
    try:
        _persist_config({"transcription_auth_token": body.auth_token})
    except _ConfigBackendIncompatible as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    return JSONResponse(content={"transcription_auth_token": body.auth_token})


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------


async def _discover_models_for_endpoint(
    api_base: str, api_key: str | None = None
) -> list[str]:
    """Query available models from an arbitrary LLM endpoint with multi-URL and multi-format support."""
    import httpx

    from omniscribe.api.services.provider_manager import extract_model_ids_from_response

    base = api_base.rstrip("/")
    headers = {}
    if api_key and api_key != "lm-studio":
        headers["Authorization"] = f"Bearer {api_key}"

    candidate_urls: list[str] = []
    if base.endswith("/v1"):
        candidate_urls.append(f"{base}/models")
    else:
        candidate_urls.append(f"{base}/v1/models")
        candidate_urls.append(f"{base}/models")
    candidate_urls.append(f"{base}/api/tags")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in candidate_urls:
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        models = extract_model_ids_from_response(resp.json())
                        if models:
                            return models
                except Exception:
                    continue
    except Exception:
        pass

    try:
        from openai import AsyncOpenAI

        client_sdk = AsyncOpenAI(
            base_url=api_base,
            api_key=api_key or "lm-studio",
        )
        response = await client_sdk.models.list()
        if response.data:
            return [m.id for m in response.data]
    except Exception:
        pass

    return []


@router.get("/api/models")
async def list_models():
    """Query available models using the active provider from ProviderManager or configured api_base."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    active_provider = mgr.get_active_provider()
    config = _load_config_from_store()

    custom_base = config.get("api_base")
    if custom_base and custom_base != active_provider.api_url:
        if not (await is_ssrf_target(custom_base)).allowed:
            return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
        try:
            models = await _discover_models_for_endpoint(
                custom_base, config.get("api_key")
            )
            return JSONResponse(content={"models": models})
        except Exception:
            logger.exception("Model discovery failed")
            return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})

    if (
        active_provider.api_url
        and not (await is_ssrf_target(active_provider.api_url)).allowed
    ):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})

    try:
        models = await mgr.async_list_provider_models(active_provider.id)
        return JSONResponse(content={"models": models})
    except Exception:
        logger.exception("Model discovery failed")
        return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})


@router.get("/api/models/ocr")
async def list_ocr_models():
    """Model discovery for the OCR namespace (uses ProviderManager or ``ocr_api_base``)."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    config = _load_config_from_store()
    ocr_provider_id = config.get("ocr_provider")

    if ocr_provider_id and mgr.get_provider(ocr_provider_id):
        provider = mgr.get_provider(ocr_provider_id)
        if (
            provider
            and provider.api_url
            and not (await is_ssrf_target(provider.api_url)).allowed
        ):
            return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
        try:
            models = await mgr.async_list_provider_models(ocr_provider_id)
            return JSONResponse(content={"models": models})
        except Exception:
            logger.exception("OCR model discovery failed")
            return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})

    api_base = config.get("ocr_api_base") or config["api_base"]
    api_key = config.get("ocr_api_key") or config["api_key"]
    if not (await is_ssrf_target(api_base)).allowed:
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    try:
        models = await _discover_models_for_endpoint(api_base, api_key)
        return JSONResponse(content={"models": models})
    except Exception:
        logger.exception("OCR model discovery failed")
        return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})


@router.get("/api/models/translation")
async def list_translation_models():
    """Model discovery for the translation namespace (uses ProviderManager or ``translation_api_base``)."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    config = _load_config_from_store()
    trans_provider_id = config.get("translation_provider")

    if trans_provider_id and mgr.get_provider(trans_provider_id):
        provider = mgr.get_provider(trans_provider_id)
        if (
            provider
            and provider.api_url
            and not (await is_ssrf_target(provider.api_url)).allowed
        ):
            return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
        try:
            models = await mgr.async_list_provider_models(trans_provider_id)
            return JSONResponse(content={"models": models})
        except Exception:
            logger.exception("Translation model discovery failed")
            return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})

    api_base = config.get("translation_api_base") or config["api_base"]
    api_key = config.get("translation_api_key") or config["api_key"]
    if not (await is_ssrf_target(api_base)).allowed:
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    try:
        models = await _discover_models_for_endpoint(api_base, api_key)
        return JSONResponse(content={"models": models})
    except Exception:
        logger.exception("Translation model discovery failed")
        return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})


# ---------------------------------------------------------------------------
# Re-export the upload cap constants so tests and other modules can import
# them from a single place.
# ---------------------------------------------------------------------------


__all__ = [
    "ABSOLUTE_MAX_UPLOAD_MB",
    "DEFAULT_MAX_UPLOAD_MB",
    "get_ocr_settings",
    "get_translation_settings",
    "router",
]
