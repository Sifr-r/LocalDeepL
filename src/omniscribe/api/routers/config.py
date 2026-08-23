# ruff: noqa: E402
import logging
import math
import os
from typing import TYPE_CHECKING, Any, TypedDict

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.api.middleware.settings import (
    ABSOLUTE_MAX_UPLOAD_MB,
    DEFAULT_MAX_UPLOAD_MB,
    SecuritySettings,
)

# Back-compat re-exports — Phase C / Task 9 extracted ``/api/models*``
# into :mod:`omniscribe.api.routers.models`. Old import paths
# (``from omniscribe.api.routers.config import list_models`` etc.) still
# work for any plugin-context provider or out-of-tree consumer that
# registered against them. The 4 route handlers themselves live in
# ``routers/models.py`` now and are mounted by ``server.create_app``.
from omniscribe.api.routers.models import (
    list_models,
    list_ocr_models,
    list_translation_models,
)
from omniscribe.api.schemas import (
    AuthTokenUpdate,
    ConfigUpdate,
    OcrConfigUpdate,
    TranslationConfigUpdate,
)
from omniscribe.api.services.envelope import BackendUnavailable, SSRFBlocked
from omniscribe.api.services.helpers import (
    CONFIG_BACKEND_INCOMPATIBLE_MESSAGE as _CONFIG_BACKEND_INCOMPATIBLE_MESSAGE,
)
from omniscribe.api.services.helpers import (
    ConfigBackendIncompatible as _ConfigBackendIncompatible,
)
from omniscribe.api.services.helpers import (
    _get_config_store as _get_config_store,
)
from omniscribe.api.services.helpers import (
    load_config_from_store as _load_config_from_store,
)
from omniscribe.api.services.helpers import (
    mask_api_key as _mask_api_key,
)
from omniscribe.api.services.helpers import (
    persist_config as _persist_config,
)
from omniscribe.core.translate.config import (
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
# Phase C / Task 8: the helpers (``_get_config_store``,
# ``_load_config_from_store``, ``_persist_config``, ``_mask_api_key``,
# ``_ConfigBackendIncompatible``) live in
# :mod:`omniscribe.api.services.helpers` now. The legacy module-level
# ``_config`` dict below remains the canonical env-derived seed source and
# the in-process cache that ``load_config_from_store`` writes through.
#
# See ``services/helpers.py`` for the rationale + ``StateBackend``
# contract. The helpers are re-exported above for backwards compat with
# code that already imports them from ``routers.config``.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_masked_placeholder(value: object) -> bool:
    """Return True for the masked preview shape the GET endpoints return."""
    return isinstance(value, str) and ("..." in value or value == "********")


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
    if "api_base" in values:
        ssrf_check = await is_ssrf_target(values["api_base"])
        if not ssrf_check.allowed:
            raise SSRFBlocked(
                url=str(values["api_base"]),
                reason=ssrf_check.reason or "blocked",
            )
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
        raise BackendUnavailable(detail=str(exc)) from exc
    return JSONResponse(content=_build_legacy_view())


# ---------------------------------------------------------------------------
# Per-namespace /api/config/{ocr,translation}
# ---------------------------------------------------------------------------


async def _build_ocr_update(body: OcrConfigUpdate) -> dict[str, Any]:
    """Validate the OCR-namespace update and return the values to persist.

    Returns the subset of ``body`` keys that should land in the store
    (masked-placeholders and SSRF-rejected bases are dropped). Raises
    :class:`SSRFBlocked` when ``ocr_api_base`` fails SSRF validation so
    the envelope handler can convert it to a 403 response.
    """
    values = body.model_dump(exclude_unset=True)
    updates: dict[str, Any] = {}
    for key, val in values.items():
        if key == "ocr_api_key" and _is_masked_placeholder(val):
            continue
        if key == "ocr_api_base" and isinstance(val, str):
            ssrf_check = await is_ssrf_target(val)
            if not ssrf_check.allowed:
                raise SSRFBlocked(url=val, reason=ssrf_check.reason or "blocked")
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
    default in-memory one, the request is refused with a 503 envelope
    (``backend_unavailable``).
    """
    updates = await _build_ocr_update(body)
    try:
        _persist_config(updates)
    except _ConfigBackendIncompatible as exc:
        raise BackendUnavailable(detail=str(exc)) from exc
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
    default in-memory one, the request is refused with a 503 envelope
    (``backend_unavailable``).
    """
    updates = _build_translation_update(body)
    try:
        _persist_config(updates)
    except _ConfigBackendIncompatible as exc:
        raise BackendUnavailable(detail=str(exc)) from exc
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
    default in-memory one, the request is refused with a 503 envelope
    (``backend_unavailable``).
    """
    try:
        _persist_config({"ocr_auth_token": body.auth_token})
    except _ConfigBackendIncompatible as exc:
        raise BackendUnavailable(detail=str(exc)) from exc
    return JSONResponse(content={"ocr_auth_token": body.auth_token})


@router.post("/api/config/translation/auth")
async def update_translation_auth_token(body: AuthTokenUpdate):
    """Persist the per-namespace translation auth token. ``None`` clears it.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503 envelope
    (``backend_unavailable``).
    """
    try:
        _persist_config({"translation_auth_token": body.auth_token})
    except _ConfigBackendIncompatible as exc:
        raise BackendUnavailable(detail=str(exc)) from exc
    return JSONResponse(content={"translation_auth_token": body.auth_token})


@router.post("/api/config/transcription/auth")
async def update_transcription_auth_token(body: AuthTokenUpdate):
    """Persist the per-namespace transcription auth token. ``None`` clears it.

    Writes through the StateBackend's config_store so every worker
    sees the new value (issue H1). When the active backend is the
    default in-memory one, the request is refused with a 503 envelope
    (``backend_unavailable``).
    """
    try:
        _persist_config({"transcription_auth_token": body.auth_token})
    except _ConfigBackendIncompatible as exc:
        raise BackendUnavailable(detail=str(exc)) from exc
    return JSONResponse(content={"transcription_auth_token": body.auth_token})


# (Model discovery handlers were extracted to routers/models.py in Phase C
# / Task 9 — see the back-compat re-exports at the top of this module.)


# ---------------------------------------------------------------------------
# Re-export the upload cap constants so tests and other modules can import
# them from a single place.
# ---------------------------------------------------------------------------


__all__ = [
    "ABSOLUTE_MAX_UPLOAD_MB",
    "DEFAULT_MAX_UPLOAD_MB",
    "_CONFIG_BACKEND_INCOMPATIBLE_MESSAGE",
    "_ConfigBackendIncompatible",
    "_get_config_store",
    "_load_config_from_store",
    "_mask_api_key",
    "_persist_config",
    "get_ocr_settings",
    "get_translation_settings",
    # Phase C / Task 9 back-compat re-exports — the live handlers live in
    # routers/models.py now; old import paths still work for plugin-context
    # providers and out-of-tree consumers.
    "list_models",
    "list_ocr_models",
    "list_translation_models",
    "router",
]
