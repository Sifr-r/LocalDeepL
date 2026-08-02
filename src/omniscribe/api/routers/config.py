# ruff: noqa: E402
import logging
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


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Ignoring invalid integer environment value for %s", name)
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


class RuntimeConfigDict(TypedDict):
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
    document_processors: list[str]


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
    "document_processors": [],
}


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
    """Async shim so the in-memory patch path can mock the SSRF check."""
    return await is_ssrf_target(value)


# ---------------------------------------------------------------------------
# Settings resolvers — core code should never poke ``_config`` directly.
# ---------------------------------------------------------------------------


def get_translation_settings() -> TranslationSettings:
    """Return core-owned settings for the optional async translation workflow.

    Namespaced ``translation_*`` keys win over the legacy ``api_*`` keys
    when both are set; the namespaced values persist the operator's
    intentional split without being silently clobbered by a legacy
    POST.
    """
    config = cast(dict[str, Any], _config)
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
    """
    from omniscribe.api.services.ai import AIRequestSettings

    config = cast(dict[str, Any], _config)
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
    """Return the legacy config payload with API key masked + upload cap surfaced."""
    payload = cast(dict[str, Any], _config).copy()
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
    """Update legacy configuration.

    Only mutates the legacy ``api_*`` keys and the OCR knobs; the
    per-namespace ``ocr_*`` / ``translation_*`` keys are intentionally
    untouched so a legacy POST does not silently clobber a deliberate
    split.
    """
    values = body.model_dump(exclude_unset=True)
    config = cast(dict[str, Any], _config)
    for key, val in values.items():
        if key == "api_key" and isinstance(val, str) and _is_masked_placeholder(val):
            continue
        if key == "api_base" and await is_ssrf_target(val):
            return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
        config[key] = val.value if hasattr(val, "value") else val
    return JSONResponse(content=_build_legacy_view())


# ---------------------------------------------------------------------------
# Per-namespace /api/config/{ocr,translation}
# ---------------------------------------------------------------------------


async def _apply_ocr_update(body: OcrConfigUpdate) -> dict[str, Any]:
    """Persist the OCR namespace update, ignoring masked-placeholders.

    Returns the resulting namespace mapping. Raises ``_SSRFRejected``
    when ``ocr_api_base`` fails SSRF validation so the route handler
    can convert it to a 403 response.
    """
    values = body.model_dump(exclude_unset=True)
    config = cast(dict[str, Any], _config)
    for key, val in values.items():
        if key == "ocr_api_key" and _is_masked_placeholder(val):
            continue
        if key == "ocr_api_base" and isinstance(val, str) and await _is_ssrf(val):
            raise _SSRFRejected
        config[key] = val
    return {k: config.get(k) for k in body.stored_keys}


def _apply_translation_update(body: TranslationConfigUpdate) -> dict[str, Any]:
    """Persist the translation namespace update, ignoring masked placeholders."""
    values = body.model_dump(exclude_unset=True)
    config = cast(dict[str, Any], _config)
    for key, val in values.items():
        if key == "translation_api_key" and _is_masked_placeholder(val):
            continue
        config[key] = val
    return {k: config.get(k) for k in body.stored_keys}


@router.get("/api/config/ocr")
async def get_ocr_namespace_config():
    """Return the OCR-namespace view with the API key masked."""
    config = cast(dict[str, Any], _config)
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
    """Persist the OCR-namespace update and return the masked view."""
    try:
        await _apply_ocr_update(body)
    except _SSRFRejected:
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    config = cast(dict[str, Any], _config)
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
    config = cast(dict[str, Any], _config)
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
    """Persist the translation-namespace update and return the masked view."""
    _apply_translation_update(body)
    config = cast(dict[str, Any], _config)
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
    """Persist the per-namespace OCR auth token. ``None`` clears it."""
    config = cast(dict[str, Any], _config)
    config["ocr_auth_token"] = body.auth_token
    return JSONResponse(content={"ocr_auth_token": body.auth_token})


@router.post("/api/config/translation/auth")
async def update_translation_auth_token(body: AuthTokenUpdate):
    """Persist the per-namespace translation auth token. ``None`` clears it."""
    config = cast(dict[str, Any], _config)
    config["translation_auth_token"] = body.auth_token
    return JSONResponse(content={"translation_auth_token": body.auth_token})


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------


@router.get("/api/models")
async def list_models():
    """
    Query the OpenAI-compatible endpoint for available models.

    Uses the current ``api_base`` from the config store.
    """
    if await is_ssrf_target(_config["api_base"]):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=_config["api_base"],
            api_key=_config["api_key"],
        )
        response = await client.models.list()
        model_ids = [m.id for m in response.data] if response.data else []
        return JSONResponse(content={"models": model_ids})
    except Exception:
        logger.exception("Model discovery failed")
        return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})


@router.get("/api/models/ocr")
async def list_ocr_models():
    """Model discovery for the OCR namespace (uses ``ocr_api_base``)."""
    config = cast(dict[str, Any], _config)
    api_base = config.get("ocr_api_base") or config["api_base"]
    api_key = config.get("ocr_api_key") or config["api_key"]
    if await is_ssrf_target(api_base):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        response = await client.models.list()
        model_ids = [m.id for m in response.data] if response.data else []
        return JSONResponse(content={"models": model_ids})
    except Exception:
        logger.exception("OCR model discovery failed")
        return JSONResponse(content={"models": [], "error": SERVER_ERROR_MESSAGE})


@router.get("/api/models/translation")
async def list_translation_models():
    """Model discovery for the translation namespace (uses ``translation_api_base``)."""
    config = cast(dict[str, Any], _config)
    api_base = config.get("translation_api_base") or config["api_base"]
    api_key = config.get("translation_api_key") or config["api_key"]
    if await is_ssrf_target(api_base):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        response = await client.models.list()
        model_ids = [m.id for m in response.data] if response.data else []
        return JSONResponse(content={"models": model_ids})
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
