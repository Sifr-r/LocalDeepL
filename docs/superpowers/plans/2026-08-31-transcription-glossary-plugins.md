# Transcription + Glossary Plugins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the two remaining deferred HTTP surfaces as harness plugins — `transcribe` (sync multipart transcription + plugin-owned config + model discovery) and `glossary` (9 import/library routes with JobQueue async dispatch) — plus a token-redeeming translate result ride-along route, finishing Phase C.

**Architecture:** Two new plugin packages mirroring the translate/documents precedent (`schemas.py` / `service.py` / `routes.py` / `plugin.py`), boot rows 11 and 12 (`ocr` → 13). Glossary async imports dispatch on the shared `JobQueue` via a third runner producer (`GlossaryJobRunner`, marker-dispatch precedent from the translate slice). The LexiconStore is constructed lazily behind an ImportError guard; lexicon-backed routes 503 with the old install hint when the `lexicon` extra is missing. All error paths use the `{"error", "detail"}` JSONResponse envelope; malformed request schemas stay FastAPI-native 422.

**Tech Stack:** Python 3.11+/uv, FastAPI 0.141 (union return annotations require `response_model=None`), pydantic v2, pytest-asyncio auto mode, httpx (URL fetch + model discovery), LanceDB via the optional `lexicon` extra.

**Spec:** `docs/superpowers/specs/2026-08-31-transcription-glossary-plugins-design.md` — read it first. All "verbatim re-home" claims point at `44ef123^` (old monolith) / `e6b7b89^` (old tests) via `git show <rev>:<path> | cat`.

## File Structure

```
src/omniscribe/plugins/transcribe/     NEW package (boot row 11)
  __init__.py        re-exports plugin
  schemas.py         TranscribeRequest (form-parsed), TranscriptionEngineType,
                     TranscriptionConfigUpdate, TranscriptionJobResponse,
                     TranscriptionConfigResponse
  config_store.py    mask_api_key (verbatim), TranscriptionConfigStore,
                     model-discovery helpers (fallback list, URL candidates,
                     extract_model_ids_from_response — verbatim)
  service.py         TranscribeError, TranscriptionServiceImpl
                     (validate → engine → artifacts → response dict)
  routes.py          build_transcribe_router (4 routes, dual manual form parse)
  plugin.py          TranscribePlugin
src/omniscribe/plugins/glossary/       NEW package (boot row 12)
  __init__.py        re-exports plugin
  schemas.py         GlossaryFormat/ImportSource/ImportRequest/ListItem/
                     ToggleRequest/ReorderRequest/PreviewResponse/
                     ImportJobResponse, GlossaryUrlImportBody (verbatim ports)
  store.py           LexiconProvider (lazy LanceDB construction + 503 seam)
  service.py         GlossaryError, kwarg builders (verbatim), estimate/name
                     helpers (verbatim), GlossaryImportServiceImpl
                     (sync/async dispatch, runner, library ops)
  routes.py          build_glossary_router (9 routes, dual-shape dispatch)
  plugin.py          GlossaryPlugin
src/omniscribe/plugins/jobs.py         + GlossaryJobRunner Protocol (marker seam)
src/omniscribe/plugins/translate/routes.py  + GET /api/translate/result/{job_id}
src/omniscribe/plugins/translate/service.py + result(job_id, token)
src/omniscribe/resources/cordis.yml    + transcribe row 11, glossary row 12
tests/conftest.py                      _TEST_CORDIS_YML → thirteen rows
tests/plugins/test_transcribe_service.py     NEW
tests/plugins/test_transcribe_schemas.py     NEW
tests/plugins/test_glossary_schemas.py       NEW
tests/plugins/test_glossary_service.py       NEW
tests/routers/test_transcribe_routes.py      NEW
tests/routers/test_glossary_routes.py        NEW (fake in-memory LexiconStore)
tests/routers/test_translate_routes.py       + 3 result-route tests
tests/plugins/test_boot_config.py            thirteen rows, router count 8
tests/harness/test_phase_c_boot.py           NEW (both plugins survive boot)
tests/openapi.json                           regenerated (13 new paths)
```

Key environment facts (verified 2026-08-31):
- `RuntimeSettings.artifact_directory` (property, config.py:286) → the lexicon store path is `<artifact_directory>/lexicon.lance`.
- `ArtifactStore.put(blob, *, content_type, owner_job_id, ttl_seconds=None) -> ArtifactHandle(id, token)`; text-artifact blob convention is a JSON page-dict `{"<page_index>": "<lines joined by \n>"}` (documents plugin's `load_pages` parses this).
- `InMemoryJobQueue.submit` hardcodes `status_url=f"/api/process/status/{job_id}"` in the returned `JobHandle` — producers ignore it and serve their own status surface.
- `check_ssrf_target_sync` (sync) and `is_ssrf_target` (async) both live in `utils/security.py` and return `SSRFCheckResult(allowed, resolved_ip, reason)`.
- `core/transcription/` (validation, types, engines, factory) survived the API removal unchanged — live code, not archaeology.
- Old-glossary 422s for business-rule failures carry the ENVELOPE shape `{"error": "validation_failed", "detail": ...}` (old tests pin this); malformed request SCHEMA failures stay FastAPI-native 422. Both 422 shapes coexist, exactly as in the old surface.

---

### Task 1: Transcribe plugin scaffold + schemas

**Files:**
- Create: `src/omniscribe/plugins/transcribe/__init__.py`, `schemas.py`
- Test: `tests/plugins/test_transcribe_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/plugins/test_transcribe_schemas.py`:

```python
"""Unit tests for the transcribe plugin schemas."""

from __future__ import annotations

import pydantic
import pytest

from omniscribe.plugins.transcribe.schemas import (
    TranscribeRequest,
    TranscriptionConfigUpdate,
    TranscriptionEngineType,
)


def test_transcribe_request_defaults() -> None:
    req = TranscribeRequest()
    assert req.model is None
    assert req.engine is None
    assert req.api_base is None
    assert req.api_key is None
    assert req.language is None
    assert req.prompt is None
    assert req.temperature == 0.0
    assert req.channel_id is None


def test_transcribe_request_rejects_unknown_fields() -> None:
    with pytest.raises(pydantic.ValidationError):
        TranscribeRequest.model_validate({"bogus": "x"})


def test_transcribe_request_coerces_numeric_temperature() -> None:
    req = TranscribeRequest.model_validate({"temperature": "0.5"})
    assert req.temperature == 0.5


def test_engine_enum_covers_factory_vocabulary() -> None:
    values = {member.value for member in TranscriptionEngineType}
    assert values == {
        "api",
        "whisper_api",
        "local",
        "whisper_local",
        "faster_whisper",
        "faster-whisper",
        "auto",
    }


def test_config_update_temperature_bounds() -> None:
    with pytest.raises(pydantic.ValidationError):
        TranscriptionConfigUpdate(temperature=2.5)
    update = TranscriptionConfigUpdate(temperature=1.5)
    assert update.temperature == 1.5


def test_config_update_strips_strings() -> None:
    update = TranscriptionConfigUpdate(model="  whisper-1  ", language=" en ")
    assert update.model == "whisper-1"
    assert update.language == "en"


def test_config_update_rejects_unknown_fields() -> None:
    with pytest.raises(pydantic.ValidationError):
        TranscriptionConfigUpdate.model_validate({"nope": 1})
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_transcribe_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: ... plugins.transcribe`

- [ ] **Step 3: Create the package + schemas**

Create `src/omniscribe/plugins/transcribe/__init__.py`:

```python
"""Transcribe plugin — voice transcription routes over the harness."""

from omniscribe.plugins.transcribe.plugin import plugin

__all__ = ["plugin"]
```

(Create a matching empty `src/omniscribe/plugins/glossary/__init__.py` with a
one-line docstring placeholder now too — Task 8 replaces it; creating both
here avoids scaffold churn later.)

Create `src/omniscribe/plugins/transcribe/schemas.py`:

```python
"""Schemas for the transcribe plugin (client-frozen contract).

`TranscribeRequest` is parsed from multipart form fields by the route
(manual `request.form()` parse + `model_validate`, mirroring the OCR
plugin's `OCRRequest` pattern — form values are strings coerced by
before-validators).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_optional_string(value: Any) -> Any:
    if value is None:
        return value
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return value.strip()


def _coerce_float(value: Any) -> Any:
    if isinstance(value, str):
        return float(value)
    return value


class TranscribeRequest(BaseModel):
    """One transcription upload's options, parsed from form fields."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    engine: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    language: str | None = None
    prompt: str | None = None
    temperature: float = 0.0
    channel_id: str | None = None

    @field_validator(
        "model",
        "engine",
        "api_base",
        "api_key",
        "language",
        "prompt",
        "channel_id",
        mode="before",
    )
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return _validate_optional_string(value)

    @field_validator("temperature", mode="before")
    @classmethod
    def _temperature(cls, value: Any) -> Any:
        return _coerce_float(value)


class TranscriptionEngineType(StrEnum):
    API = "api"
    WHISPER_API = "whisper_api"
    LOCAL = "local"
    WHISPER_LOCAL = "whisper_local"
    FASTER_WHISPER = "faster_whisper"
    FASTER_WHISPER_DASH = "faster-whisper"
    AUTO = "auto"


class TranscriptionConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_base: str | None = None
    api_key: str | None = None
    transcription_api_key: str | None = None
    model: str | None = None
    engine: TranscriptionEngineType | None = None
    language: str | None = None
    prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @field_validator(
        "api_base",
        "api_key",
        "transcription_api_key",
        "model",
        "language",
        "prompt",
        mode="before",
    )
    @classmethod
    def _validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class TranscriptionConfigResponse(BaseModel):
    """Transcription-namespace runtime configuration."""

    transcription_api_base: str
    transcription_api_key: str
    transcription_model: str
    transcription_engine: str
    transcription_auth_token: str | None = None
    language: str | None = None
    prompt: str | None = None
    temperature: float = 0.0


class TranscriptionJobResponse(BaseModel):
    """Response returned upon transcription execution."""

    text: str
    language: str | None = None
    duration: float | None = None
    text_artifact_id: str | None = None
    text_artifact_token: str | None = None
    metadata_artifact_id: str | None = None
    metadata_artifact_token: str | None = None
    job_id: str | None = None
    segments: list[dict[str, Any]] = []
```

- [ ] **Step 4: Run the schema tests**

Run: `uv run pytest tests/plugins/test_transcribe_schemas.py -v`
Expected: all 7 PASS

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean (the placeholder `glossary/__init__.py` is docstring-only)

```bash
git add src/omniscribe/plugins/transcribe/ src/omniscribe/plugins/glossary/__init__.py tests/plugins/test_transcribe_schemas.py
git commit -m "feat(transcribe): plugin scaffold + request/config schemas"
```

---

### Task 2: Transcribe service (validate → engine → artifacts → response)

**Files:**
- Create: `src/omniscribe/plugins/transcribe/service.py`
- Test: `tests/plugins/test_transcribe_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/plugins/test_transcribe_service.py`:

```python
"""Unit tests for the transcribe plugin service (no HTTP layer)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from omniscribe.plugins.transcribe import service as transcribe_service
from omniscribe.plugins.transcribe.schemas import TranscribeRequest


class _FakeStore:
    def __init__(self) -> None:
        self.blobs: dict[str, tuple[str, bytes, str]] = {}

    async def put(
        self, blob: bytes, *, content_type: str, owner_job_id: str,
        ttl_seconds: int | None = None,
    ) -> Any:
        artifact_id = f"a{len(self.blobs):031d}"
        token = f"t{len(self.blobs):041d}"
        self.blobs[artifact_id] = (token, blob, content_type)

        class _Handle:
            pass

        handle = _Handle()
        handle.id = artifact_id
        handle.token = token
        return handle

    async def get(self, artifact_id: str, token: str) -> Any:
        entry = self.blobs.get(artifact_id)
        if entry is None or entry[0] != token:
            return None

        class _Blob:
            blob = entry[1]
            content_type = entry[2]
            record = None

        return _Blob()


def _config() -> dict[str, str]:
    return {
        "transcription_api_base": "https://api.openai.com/v1",
        "transcription_model": "whisper-1",
        "transcription_engine": "api",
    }


def _result(text: str = "hello world", language: str | None = "en") -> Any:
    from omniscribe.core.transcription.types import (
        TranscriptionResult,
        TranscriptionSegment,
    )

    return TranscriptionResult(
        text=text,
        language=language,
        duration=2.0,
        segments=[
            TranscriptionSegment(id=0, start=0.0, end=2.0, text=text)
        ],
    )


def _stub_engine(
    monkeypatch: pytest.MonkeyPatch,
    result: Any,
    calls: list[dict[str, Any]],
    factory_calls: list[dict[str, Any]] | None = None,
) -> None:
    class _Engine:
        async def transcribe(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return result

    def _factory(**kw: Any) -> _Engine:
        if factory_calls is not None:
            factory_calls.append(kw)
        return _Engine()

    monkeypatch.setattr(transcribe_service, "get_transcription_engine", _factory)


async def test_transcribe_happy_path_stores_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    factory_calls: list[dict[str, Any]] = []
    _stub_engine(monkeypatch, _result(), calls, factory_calls)
    store = _FakeStore()
    result = await transcribe_service.transcribe(
        TranscribeRequest(model="whisper-1"),
        file_bytes=b"fake-audio",
        filename="clip.wav",
        content_type="audio/wav",
        store=store,
        config=_config(),
    )
    assert result["text"] == "hello world"
    assert result["language"] == "en"
    assert result["duration"] == 2.0
    assert result["job_id"].startswith("job-")
    assert len(result["segments"]) == 1
    assert result["segments"][0]["text"] == "hello world"
    # Both artifacts stored and referenced with tokens.
    assert result["text_artifact_id"] in store.blobs
    assert result["metadata_artifact_id"] in store.blobs
    text_blob = json.loads(
        store.blobs[result["text_artifact_id"]][1].decode("utf-8")
    )
    assert text_blob == {"0": "hello world"}
    meta_blob = json.loads(
        store.blobs[result["metadata_artifact_id"]][1].decode("utf-8")
    )
    assert set(meta_blob) == {"0"}
    # The factory received the resolved chain values (model/api_base flow
    # to the factory, not the engine call).
    assert factory_calls[0]["model"] == "whisper-1"
    assert factory_calls[0]["api_base"] == "https://api.openai.com/v1"
    assert set(calls[0]) == {
        "file_bytes",
        "filename",
        "language",
        "prompt",
        "temperature",
    }


async def test_transcribe_resolves_form_over_config_over_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    factory_calls: list[dict[str, Any]] = []
    _stub_engine(monkeypatch, _result(), calls, factory_calls)
    await transcribe_service.transcribe(
        TranscribeRequest(model="custom-model", api_key="sk-x"),
        file_bytes=b"x",
        filename="a.mp3",
        content_type="audio/mpeg",
        store=_FakeStore(),
        config={"transcription_model": "config-model"},
    )
    assert factory_calls[0]["model"] == "custom-model"


async def test_transcribe_ssrf_checks_override_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("must not be called")

    monkeypatch.setattr(transcribe_service, "get_transcription_engine", fail_call_llm)
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(api_base="http://169.254.169.254/latest"),
            file_bytes=b"x",
            filename="a.wav",
            content_type="audio/wav",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.error == "ssrf_blocked"


async def test_transcribe_bad_extension_maps_to_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(),
            file_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            content_type="application/pdf",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.error == "bad_request"
    assert "Unsupported audio format" in excinfo.value.detail


async def test_transcribe_engine_error_maps_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omniscribe.core.transcription.types import TranscriptionError

    class _Broken:
        async def transcribe(self, **kwargs: Any) -> Any:
            raise TranscriptionError(
                "Local transcription requires the 'transcription' extra", 503
            )

    monkeypatch.setattr(
        transcribe_service, "get_transcription_engine", lambda **kw: _Broken()
    )
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(engine="local"),
            file_bytes=b"x",
            filename="a.wav",
            content_type="audio/wav",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 503
    assert excinfo.value.error == "backend_unavailable"
    assert "transcription" in excinfo.value.detail


async def test_transcribe_unexpected_error_maps_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Broken:
        async def transcribe(self, **kwargs: Any) -> Any:
            raise RuntimeError("connection reset")

    monkeypatch.setattr(
        transcribe_service, "get_transcription_engine", lambda **kw: _Broken()
    )
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(),
            file_bytes=b"x",
            filename="a.wav",
            content_type="audio/wav",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 502
    assert excinfo.value.error == "ai_error"
    assert excinfo.value.detail == "The AI service request failed."
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_transcribe_service.py -v`
Expected: FAIL — `transcribe_service` has no attribute `transcribe`

- [ ] **Step 3: Implement the service**

Create `src/omniscribe/plugins/transcribe/service.py`:

```python
"""Transcribe service: validation → engine → artifacts → response dict.

Verbatim re-home of the pre-harness `api/services/transcription.py`
(`44ef123^`) semantics onto the harness ArtifactStore. The old service
stored page-dict artifacts (`{0: [lines]}`) through a typed artifact
service; the harness store takes opaque bytes, so the same page-dict is
serialized as JSON using the text-artifact convention
`{"<page_index>": "<lines joined by \n>"}`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Mapping

from omniscribe.core.transcription import (
    AudioValidationError,
    TranscriptionError,
    get_transcription_engine,
    validate_audio_input,
)
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.transcribe.schemas import TranscribeRequest
from omniscribe.utils.security import check_ssrf_target_sync

_LOGGER = logging.getLogger("omniscribe.plugins.transcribe")

DEFAULT_TRANSCRIPTION_API_BASE = "https://api.openai.com/v1"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_TRANSCRIPTION_ENGINE = "api"


class TranscribeError(Exception):
    """User-facing transcribe error carrying the envelope wire fields."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


def resolve_engine_settings(
    request: TranscribeRequest, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Form → config store → default, per field (old fallback chain)."""
    return {
        "model": str(
            request.model or config.get("transcription_model", "whisper-1")
        ),
        "engine": str(
            request.engine or config.get("transcription_engine", "api")
        ),
        "api_base": str(
            request.api_base
            or config.get("transcription_api_base", DEFAULT_TRANSCRIPTION_API_BASE)
        ),
        "api_key": str(request.api_key or config.get("transcription_api_key", ""))
        or None,
        "language": str(request.language or config.get("transcription_language") or "")
        or None,
        "prompt": str(request.prompt or config.get("transcription_prompt") or "")
        or None,
        "temperature": request.temperature,
    }


async def transcribe(
    request: TranscribeRequest,
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    store: ArtifactStore,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Sync transcription; verbatim old response shape."""
    start = time.monotonic()

    # SSRF-check the caller-supplied override only (translate precedent):
    # config-store/default values are trusted operator config.
    if request.api_base and request.api_base.strip():
        check = check_ssrf_target_sync(request.api_base.strip())
        if not check.allowed:
            raise TranscribeError(
                403,
                "ssrf_blocked",
                f"URL targets a blocked address: {check.reason}",
            )

    try:
        validate_audio_input(
            filename=filename,
            content_type=content_type,
            file_size=len(file_bytes),
        )
    except AudioValidationError as exc:
        raise TranscribeError(400, "bad_request", exc.message) from exc

    resolved = resolve_engine_settings(request, config)
    engine = get_transcription_engine(
        engine_type=resolved["engine"],
        model=resolved["model"],
        api_base=resolved["api_base"],
        api_key=resolved["api_key"],
    )
    try:
        result = await engine.transcribe(
            file_bytes=file_bytes,
            filename=filename,
            language=resolved["language"],
            prompt=resolved["prompt"],
            temperature=resolved["temperature"],
        )
    except TranscriptionError as exc:
        raise TranscribeError(503, "backend_unavailable", exc.message) from exc
    except Exception as exc:
        _LOGGER.exception("Voice transcription request failed")
        raise TranscribeError(
            502, "ai_error", "The AI service request failed."
        ) from exc

    job_id = f"job-{uuid.uuid4().hex[:12]}"
    lines = [s.text for s in result.segments] if result.segments else [result.text]
    text_handle = await store.put(
        json.dumps({"0": "\n".join(lines)}).encode("utf-8"),
        content_type="application/json",
        owner_job_id=job_id,
    )
    doc_result = result.to_document_result()
    page_metadata = (
        doc_result.pages[0].metadata if doc_result.pages else {}
    )
    meta_handle = await store.put(
        json.dumps({"0": json.dumps(page_metadata)}).encode("utf-8"),
        content_type="application/json",
        owner_job_id=job_id,
    )
    duration_s = round(time.monotonic() - start, 3)
    return {
        "text": result.text,
        "language": result.language,
        "duration": result.duration,
        "text_artifact_id": text_handle.id,
        "text_artifact_token": text_handle.token,
        "metadata_artifact_id": meta_handle.id,
        "metadata_artifact_token": meta_handle.token,
        "job_id": job_id,
        "segments": [
            {
                "id": s.id,
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "confidence": s.confidence,
            }
            for s in result.segments
        ],
    }
```

Note: `resolve_engine_settings` returns `temperature` from the request (the
old route passed the form value straight through — config had no
temperature seed other than the response default). Task 4's impl class
adds the `RuntimeSettings` import when it lands.

- [ ] **Step 4: Run the service tests**

Run: `uv run pytest tests/plugins/test_transcribe_service.py -v`
Expected: all 6 PASS

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/transcribe/service.py tests/plugins/test_transcribe_service.py
git commit -m "feat(transcribe): service with artifact storage and error mapping"
```

---

### Task 3: Transcribe config store + model discovery helpers

**Files:**
- Create: `src/omniscribe/plugins/transcribe/config_store.py`
- Test: append to `tests/plugins/test_transcribe_service.py`

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/plugins/test_transcribe_service.py` (also add to the
file's import block: `from types import SimpleNamespace` and
`from omniscribe.plugins.transcribe import config_store`):

```python
# ---------------------------------------------------------------------------
# Config store + model discovery
# ---------------------------------------------------------------------------


def test_mask_api_key_matches_old_behavior() -> None:
    assert transcribe_service.mask_api_key(None) is None
    assert transcribe_service.mask_api_key("") == ""
    assert transcribe_service.mask_api_key("lm-studio") == "lm-studio"
    assert transcribe_service.mask_api_key("short") == "********"
    assert transcribe_service.mask_api_key("abcd1234wxyz") == "abcd...wxyz"


def test_config_store_defaults_and_write_through() -> None:
    store = transcribe_service.TranscriptionConfigStore(auth_token="tok")
    read = store.read()
    assert read.transcription_api_base == "https://api.openai.com/v1"
    assert read.transcription_model == "whisper-1"
    assert read.transcription_engine == "api"
    assert read.temperature == 0.0
    assert read.transcription_auth_token == "********"  # "tok" masked: len <= 8

    store.update(
        {"transcription_model": "gpt-4o-audio-preview", "transcription_api_key": "k"}
    )
    read = store.read()
    assert read.transcription_model == "gpt-4o-audio-preview"
    assert read.transcription_api_key == "********"  # mask rule: len <= 8


async def test_discover_models_falls_back_on_bad_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ssrf_allowed(url: str | None) -> Any:
        return SimpleNamespace(allowed=True)

    class _FailingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FailingClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, headers: dict | None = None) -> Any:
            raise RuntimeError("no network")

    # Patch the SSRF gate so the failing-client path is deterministic in CI
    # (localhost is SSRF-blocked by default, which would short-circuit to
    # the fallback before the patched client is ever constructed).
    monkeypatch.setattr(config_store, "is_ssrf_target", _ssrf_allowed)
    monkeypatch.setattr(config_store.httpx, "AsyncClient", _FailingClient)
    models = await transcribe_service.discover_transcription_models(
        "http://localhost:1234/v1", None
    )
    assert models == transcribe_service.TRANSCRIPTION_FALLBACK_MODELS


def test_extract_model_ids_handles_openai_and_ollama() -> None:
    openai = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
    ollama = {"models": [{"name": "llama3"}]}
    assert transcribe_service.extract_model_ids_from_response(openai) == [
        "gpt-4o",
        "gpt-4o-mini",
    ]
    assert transcribe_service.extract_model_ids_from_response(ollama) == ["llama3"]
    assert transcribe_service.extract_model_ids_from_response(None) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_transcribe_service.py -v -k "mask or config_store or discover or extract"`
Expected: FAIL — ImportError on `config_store` (the test module cannot
import until the implementation exists)

- [ ] **Step 3: Implement config_store.py**

Create `src/omniscribe/plugins/transcribe/config_store.py`:

```python
"""Transcription config store + model discovery (verbatim re-homes).

`mask_api_key` is verbatim from `44ef123^:api/services/helpers.py`
(`mask_api_key`). `extract_model_ids_from_response` is verbatim from
`44ef123^:api/services/provider_manager.py`. The discovery flow is
verbatim from `44ef123^:api/routers/models.py::get_transcription_models`
with the config store swapped for the plugin-owned one.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from omniscribe.plugins.transcribe.schemas import (
    TranscriptionConfigResponse,
)
from omniscribe.utils.security import is_ssrf_target

_LOGGER = logging.getLogger("omniscribe.plugins.transcribe")

TRANSCRIPTION_FALLBACK_MODELS: list[str] = [
    "whisper-1",
    "whisper-large-v3",
    "whisper-medium",
    "whisper-base",
    "whisper-small",
    "whisper-tiny",
]


def mask_api_key(value: str | None) -> str | None:
    """Return a ``<first4>...<last4>`` preview of the API key (verbatim)."""
    if not value or value == "lm-studio":
        return value
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


class TranscriptionConfigStore:
    """Plugin-owned in-memory transcription config (always writable)."""

    def __init__(self, auth_token: str | None = None) -> None:
        self._auth_token = auth_token
        self._data: dict[str, Any] = {
            "transcription_api_base": "https://api.openai.com/v1",
            "transcription_model": "whisper-1",
            "transcription_engine": "api",
            "transcription_temperature": 0.0,
        }

    def get(self) -> dict[str, Any]:
        return dict(self._data)

    def update(self, updates: dict[str, Any]) -> None:
        self._data.update(updates)

    def read(self) -> TranscriptionConfigResponse:
        data = self._data
        auth_tok = data.get(
            "transcription_auth_token", self._auth_token
        )
        return TranscriptionConfigResponse(
            transcription_api_base=str(
                data.get("transcription_api_base", "https://api.openai.com/v1")
            ),
            transcription_api_key=mask_api_key(
                str(data.get("transcription_api_key", ""))
            )
            or "",
            transcription_model=str(data.get("transcription_model", "whisper-1")),
            transcription_engine=str(data.get("transcription_engine", "api")),
            transcription_auth_token=mask_api_key(auth_tok),
            language=str(data.get("transcription_language", "")) or None,
            prompt=str(data.get("transcription_prompt", "")) or None,
            temperature=float(data.get("transcription_temperature", 0.0)),
        )


def extract_model_ids_from_response(data: Any) -> list[str]:
    """Extract model identifiers from arbitrary JSON responses (verbatim)."""
    if not data:
        return []

    raw_items: list[Any] = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            raw_items = data["data"]
        elif "models" in data and isinstance(data["models"], list):
            raw_items = data["models"]
        elif "result" in data and isinstance(data["result"], list):
            raw_items = data["result"]
        elif "data" in data and isinstance(data["data"], dict):
            raw_items = list(data["data"].values())
        else:
            for v in data.values():
                if isinstance(v, dict) and any(
                    k in v for k in ("id", "name", "model")
                ):
                    raw_items.append(v)

    model_ids: list[str] = []
    seen: set[str] = set()

    for item in raw_items:
        mid: str | None = None
        if isinstance(item, str) and item.strip():
            mid = item.strip()
        elif isinstance(item, dict):
            for key in ("id", "name", "model", "model_id", "display_name"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    mid = val.strip()
                    break
        if mid and mid not in seen:
            seen.add(mid)
            model_ids.append(mid)

    return model_ids


async def discover_transcription_models(
    api_base: str, api_key: str | None
) -> list[str]:
    """Probe the configured endpoint for models; fall back on any failure.

    Verbatim flow from `44ef123^:api/routers/models.py:271-320`: SSRF-blocked
    → fallback list (no error); `lm-studio` key skipped for the Bearer
    header; probe `{base}/models` (base ends `/v1`) or `{base}/v1/models`
    then `{base}/models`, always then `{base}/api/tags` (Ollama); 5.0s
    timeout; per-URL failures swallowed; empty discovery → fallback.
    """
    fallback = list(TRANSCRIPTION_FALLBACK_MODELS)

    if not (await is_ssrf_target(api_base)).allowed:
        return fallback

    headers: dict[str, str] = {}
    if api_key and api_key != "lm-studio":
        headers["Authorization"] = f"Bearer {api_key}"

    base = api_base.rstrip("/")
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
    except Exception as exc:
        _LOGGER.warning(
            "Failed to fetch models from transcription api_base %s: %s",
            api_base,
            exc,
        )

    return fallback
```

Then append to `src/omniscribe/plugins/transcribe/service.py` (re-export so
routes/tests import from one module; place in the module-top import block —
isort order puts `config_store` before `schemas`):

```python
from omniscribe.plugins.transcribe.config_store import (  # noqa: F401
    TRANSCRIPTION_FALLBACK_MODELS,
    TranscriptionConfigStore,
    discover_transcription_models,
    extract_model_ids_from_response,
    mask_api_key,
)
```

(`TRANSCRIPTION_FALLBACK_MODELS` is included because the discovery test
asserts against `transcribe_service.TRANSCRIPTION_FALLBACK_MODELS`. The
`# noqa: F401` is required — the names are unused inside service.py
itself; they exist for Task 4's routes and the tests. The test file
imports `from omniscribe.plugins.transcribe import config_store` at the
top and monkeypatches `config_store.is_ssrf_target` and
`config_store.httpx` directly; service.py does NOT import httpx or the
config_store module object.)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/plugins/test_transcribe_service.py -v`
Expected: all 10 PASS (6 prior + 4 new)

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/transcribe/ tests/plugins/test_transcribe_service.py
git commit -m "feat(transcribe): plugin-owned config store + model discovery"
```

---

### Task 4: Transcribe plugin + routes + router contract tests

**Files:**
- Create: `src/omniscribe/plugins/transcribe/routes.py`, `plugin.py`
- Replace: `src/omniscribe/plugins/transcribe/__init__.py`
- Modify: `tests/conftest.py` (transcribe boot row between translate/ocr —
  the route tests boot through `api_client`, so the plugin must be mounted
  in the TEST tree here; Task 11 only adds the shipped-tree row + glossary)
- Modify: `tests/openapi.json` (regenerated, additions-only — the mounted
  routes would otherwise fail `test_openapi_schema_matches_snapshot` until
  Task 12)
- Test: `tests/routers/test_transcribe_routes.py`

- [ ] **Step 1: Write the failing router tests**

Create `tests/routers/test_transcribe_routes.py`:

```python
"""Router contract tests for the transcribe plugin (client-frozen)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from omniscribe.core.transcription.types import (
    TranscriptionResult,
    TranscriptionSegment,
)

WAV_HEADER = (
    b"RIFF$"
    + b"\x00\x00\x00"
    + b"WAVEfmt "
    + b"\x10\x00\x00\x00\x01\x00\x01\x00"
    + b"D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


def _result(text: str = "Sample transcribed speech text") -> TranscriptionResult:
    return TranscriptionResult(
        text=text,
        language="en",
        duration=4.0,
        segments=[
            TranscriptionSegment(id=0, start=0.0, end=4.0, text=text)
        ],
    )


def _stub_engine(monkeypatch: Any, result: TranscriptionResult) -> None:
    from omniscribe.plugins.transcribe import service

    class _Engine:
        async def transcribe(self, **kwargs: Any) -> TranscriptionResult:
            return result

    monkeypatch.setattr(
        service, "get_transcription_engine", lambda **kw: _Engine()
    )


def test_transcribe_routes_are_mounted(api_client: TestClient) -> None:
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    assert "/api/transcribe" in paths
    assert "/api/config/transcription" in paths
    assert "/api/models/transcription" in paths


def test_transcribe_success_contract(
    api_client: TestClient, monkeypatch: Any
) -> None:
    _stub_engine(monkeypatch, _result())
    response = api_client.post(
        "/api/transcribe",
        files={"file": ("test.wav", WAV_HEADER, "audio/wav")},
        data={"model": "whisper-1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Sample transcribed speech text"
    assert data["language"] == "en"
    assert data["duration"] == 4.0
    assert data["job_id"].startswith("job-")
    assert data["text_artifact_id"] and data["text_artifact_token"]
    assert data["metadata_artifact_id"] and data["metadata_artifact_token"]
    assert data["segments"][0]["text"] == "Sample transcribed speech text"


def test_transcribe_unsupported_format_400(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/transcribe",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert "Unsupported audio format" in body["detail"]


def test_transcribe_ssrf_override_403(
    api_client: TestClient, monkeypatch: Any
) -> None:
    _stub_engine(monkeypatch, _result())
    response = api_client.post(
        "/api/transcribe",
        files={"file": ("a.wav", WAV_HEADER, "audio/wav")},
        data={"api_base": "http://169.254.169.254/latest"},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "ssrf_blocked"


def test_config_get_masks_and_post_roundtrips(api_client: TestClient) -> None:
    get_resp = api_client.get("/api/config/transcription")
    assert get_resp.status_code == 200
    assert get_resp.json()["transcription_model"] == "whisper-1"

    post_resp = api_client.post(
        "/api/config/transcription",
        json={
            "model": "gpt-4o-audio-preview",
            "transcription_api_key": "my-real-secret-key-xyz123",
            "engine": "api",
        },
    )
    assert post_resp.status_code == 200
    updated = post_resp.json()
    assert updated["transcription_model"] == "gpt-4o-audio-preview"
    assert "my-real-secret-key" not in updated["transcription_api_key"]
    assert "..." in updated["transcription_api_key"]

    # Write-through: a later GET reflects the update.
    assert api_client.get("/api/config/transcription").json()[
        "transcription_model"
    ] == "gpt-4o-audio-preview"


def test_config_temperature_out_of_range_422(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/config/transcription", json={"temperature": 2.5}
    )
    assert response.status_code == 422


def test_models_transcription_returns_fallback_shape(
    api_client: TestClient, monkeypatch: Any
) -> None:
    from omniscribe.plugins.transcribe import config_store

    class _FailingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FailingClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, headers: dict | None = None) -> Any:
            raise RuntimeError("no network")

    monkeypatch.setattr(config_store.httpx, "AsyncClient", _FailingClient)
    response = api_client.get("/api/models/transcription")
    assert response.status_code == 200
    models = response.json()["models"]
    assert "whisper-1" in models
    assert len(models) == 6
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/routers/test_transcribe_routes.py -v`
Expected: FAIL — `omniscribe.plugins.transcribe:plugin` cannot be imported

- [ ] **Step 3: Implement routes.py + plugin.py + __init__.py**

Create `src/omniscribe/plugins/transcribe/routes.py`:

```python
"""HTTP routes for the transcribe plugin (client-frozen contract).

Routes whose handler may answer with the error envelope declare a union
return type; FastAPI cannot build a response model from such unions, so
those decorators pass ``response_model=None``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from omniscribe.plugins.transcribe.schemas import (
    TranscribeRequest,
    TranscriptionConfigUpdate,
    TranscriptionJobResponse,
)
from omniscribe.plugins.transcribe.service import (
    TranscriptionService,
    TranscribeError,
)


def _envelope(status_code: int, error: str, detail: str) -> JSONResponse:
    """Stable error envelope the Flutter client parses."""
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def build_transcribe_router(service: TranscriptionService) -> APIRouter:
    router = APIRouter(tags=["transcribe"])

    @router.post("/api/transcribe", response_model=None)
    async def transcribe_audio(request: Request) -> Any:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            return _envelope(400, "bad_request", "missing 'file' field")
        file_bytes: bytes = await upload.read()
        fields: dict[str, Any] = {
            key: value
            for key, value in form.items()
            if key != "file" and isinstance(value, str)
        }
        try:
            options = TranscribeRequest.model_validate(fields)
        except ValidationError as exc:
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors(include_url=False)},
            )
        filename = str(getattr(upload, "filename", "") or "") or "audio.wav"
        content_type = getattr(upload, "content_type", "") or None
        try:
            result = await service.transcribe(
                options,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
        except TranscribeError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return result

    @router.get("/api/config/transcription", response_model=None)
    async def get_transcription_config() -> TranscriptionConfigResponse:
        return service.get_config()

    @router.post("/api/config/transcription", response_model=None)
    async def update_transcription_config(
        body: TranscriptionConfigUpdate,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.update_config(body)
        except TranscribeError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/models/transcription", response_model=None)
    async def get_transcription_models() -> dict[str, Any]:
        return {"models": await service.discover_models()}

    return router
```

Append to `src/omniscribe/plugins/transcribe/service.py` — the service
Protocol + impl (add the missing imports at module top: `Protocol` into the
`typing` import, and `TranscriptionConfigUpdate`/`mask_api_key`/
`discover_transcription_models`/`TranscriptionConfigStore` from
`config_store`/`schemas`):

```python
class TranscriptionService(Protocol):
    async def transcribe(
        self,
        request: TranscribeRequest,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> dict[str, Any] | TranscriptionJobResponse: ...

    def get_config(self) -> TranscriptionConfigResponse: ...

    def update_config(
        self, body: TranscriptionConfigUpdate
    ) -> TranscriptionConfigResponse: ...

    async def discover_models(self) -> list[str]: ...


class TranscriptionServiceImpl:
    """Harness transcription service over the ArtifactStore."""

    def __init__(
        self,
        settings: RuntimeSettings,
        store: ArtifactStore,
    ) -> None:
        self._settings = settings
        self._store = store
        self._config = TranscriptionConfigStore(
            auth_token=settings.transcription_auth_token
        )

    async def transcribe(
        self,
        request: TranscribeRequest,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> dict[str, Any]:
        return await transcribe(
            request,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            store=self._store,
            config=self._config.get(),
        )

    def get_config(self) -> TranscriptionConfigResponse:
        return self._config.read()

    def update_config(
        self, body: TranscriptionConfigUpdate
    ) -> TranscriptionConfigResponse:
        updates: dict[str, Any] = {}
        if body.api_base is not None:
            check = check_ssrf_target_sync(body.api_base)
            if not check.allowed:
                raise TranscribeError(
                    403,
                    "ssrf_blocked",
                    f"URL targets a blocked address: {check.reason}",
                )
            updates["transcription_api_base"] = body.api_base
        if body.transcription_api_key is not None:
            updates["transcription_api_key"] = body.transcription_api_key
        elif body.api_key is not None:
            updates["transcription_api_key"] = body.api_key
        if body.model is not None:
            updates["transcription_model"] = body.model
        if body.engine is not None:
            updates["transcription_engine"] = body.engine.value
        if body.language is not None:
            updates["transcription_language"] = body.language
        if body.prompt is not None:
            updates["transcription_prompt"] = body.prompt
        if body.temperature is not None:
            updates["transcription_temperature"] = body.temperature
        if updates:
            self._config.update(updates)
        return self._config.read()

    async def discover_models(self) -> list[str]:
        config = self._config.get()
        api_base = str(
            config.get("transcription_api_base", DEFAULT_TRANSCRIPTION_API_BASE)
        )
        api_key = str(config.get("transcription_api_key", "")) or None
        return await discover_transcription_models(api_base, api_key)
```

Name collision note: the module-level free function is `transcribe` and the
impl method is also `transcribe` — inside `TranscriptionServiceImpl.transcribe`
the bare name `transcribe` resolves to the module function (methods are not
in module scope), which is exactly what we want. If mypy/ruff objects, alias
the module function as `transcribe_audio = transcribe` right after its
definition and call that.

Create `src/omniscribe/plugins/transcribe/plugin.py`:

```python
"""Transcribe plugin — mounts transcription routes on the harness."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.runtime import RuntimeService
from omniscribe.plugins.transcribe.routes import build_transcribe_router
from omniscribe.plugins.transcribe.service import (
    TranscriptionService,
    TranscriptionServiceImpl,
)


class TranscribeSchema(BaseModel):
    """No configurable fields."""


class TranscribePlugin(Plugin):
    """Client-frozen transcription surface: sync + config + discovery."""

    Schema = TranscribeSchema

    async def apply(self, ctx: Context) -> None:
        store = ctx.inject(ArtifactStore)
        runtime = ctx.inject(RuntimeService)
        service = TranscriptionServiceImpl(runtime.settings, store)
        ctx.service(TranscriptionService, service)
        ctx.mount_router(build_transcribe_router(service))


plugin = TranscribePlugin()
```

Replace `src/omniscribe/plugins/transcribe/__init__.py`:

```python
"""Transcribe plugin — voice transcription routes over the harness."""

from omniscribe.plugins.transcribe.plugin import plugin

__all__ = ["plugin"]
```

- [ ] **Step 4: Run the router tests**

Run: `uv run pytest tests/routers/test_transcribe_routes.py -v`
Expected: all 7 PASS

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/transcribe/ tests/routers/test_transcribe_routes.py tests/conftest.py tests/openapi.json
git commit -m "feat(transcribe): client-frozen routes, config store, model discovery"
```

---

### Task 5: Glossary schemas (verbatim ports)

**Files:**
- Create: `src/omniscribe/plugins/glossary/schemas.py`
- Test: `tests/plugins/test_glossary_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/plugins/test_glossary_schemas.py`:

```python
"""Unit tests for the glossary plugin schemas (verbatim old-contract pins)."""

from __future__ import annotations

import pydantic
import pytest

from omniscribe.plugins.glossary.schemas import (
    GlossaryFormat,
    GlossaryImportJobResponse,
    GlossaryImportSource,
    GlossaryReorderRequest,
)


def test_format_enum_vocabulary() -> None:
    assert {member.value for member in GlossaryFormat} == {
        "csv",
        "tsv",
        "xliff",
        "tbx",
        "tmx",
        "git_glossary",
        "sql_table",
        "json_pairs",
    }


def test_import_source_defaults_match_old_contract() -> None:
    source = GlossaryImportSource(format=GlossaryFormat.CSV)
    assert source.git_ref == "HEAD"
    assert source.git_path == "GLOSSARY.md"
    assert source.sql_source_col == "source"
    assert source.sql_target_col == "target"
    assert source.max_entries is None
    assert source.name is None


def test_import_source_strips_optional_strings() -> None:
    source = GlossaryImportSource(
        format=GlossaryFormat.CSV, name="  Pairs  ", encoding=" utf-8 "
    )
    assert source.name == "Pairs"
    assert source.encoding == "utf-8"


def test_import_source_rejects_unknown_fields() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryImportSource.model_validate(
            {"format": "csv", "mystery": 1}
        )


def test_max_entries_bounds() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryImportSource(format=GlossaryFormat.CSV, max_entries=0)
    with pytest.raises(pydantic.ValidationError):
        GlossaryImportSource(format=GlossaryFormat.CSV, max_entries=1_000_001)
    assert (
        GlossaryImportSource(format=GlossaryFormat.CSV, max_entries=1).max_entries
        == 1
    )
    assert (
        GlossaryImportSource(
            format=GlossaryFormat.CSV, max_entries=1_000_000
        ).max_entries
        == 1_000_000
    )


def test_import_job_response_shape() -> None:
    sync = GlossaryImportJobResponse(
        glossary_id="g1",
        format=GlossaryFormat.JSON_PAIRS,
        name="N",
        entry_count=1,
        warnings=[],
        queued=False,
    )
    assert sync.job_id is None
    queued = GlossaryImportJobResponse(
        job_id="j-1",
        format=GlossaryFormat.CSV,
        name="N",
        entry_count=0,
        warnings=[],
        queued=True,
    )
    assert queued.glossary_id is None


def test_reorder_request_bounds() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryReorderRequest(ordered_ids=[str(i) for i in range(201)])
    assert len(
        GlossaryReorderRequest(ordered_ids=[str(i) for i in range(200)]).ordered_ids
    ) == 200


def test_url_import_body_accepts_and_coerces() -> None:
    body = GlossaryUrlImportBody(url="  http://example.com/g.csv  ")
    assert body.url == "http://example.com/g.csv"
    assert body.format is None
    assert body.name is None
    coerced = GlossaryUrlImportBody.model_validate(
        {"url": "http://x/tbx", "format": "tbx"}
    )
    assert coerced.format is GlossaryFormat.TBX


def test_url_import_body_rejects_blank_and_unknown() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryUrlImportBody(url="   ")
    with pytest.raises(pydantic.ValidationError):
        GlossaryUrlImportBody.model_validate({"url": "u", "mystery": 1})


def test_import_request_strips_channel_fields() -> None:
    req = GlossaryImportRequest.model_validate(
        {
            "source": {"format": "csv"},
            "channel_id": " ch-1 ",
            "session_token": " tok ",
        }
    )
    assert req.channel_id == "ch-1"
    assert req.session_token == "tok"
```

(The test file's imports also include `GlossaryImportRequest` and
`GlossaryUrlImportBody`; 10 tests total.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_glossary_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: ... plugins.glossary`

- [ ] **Step 3: Implement schemas.py**

Create `src/omniscribe/plugins/glossary/schemas.py` (verbatim port of the
old models from `44ef123^:api/schemas/requests.py:438-500` — field names,
defaults, validators, and bounds are contract):

```python
"""Glossary plugin schemas (verbatim re-homes from the pre-harness API).

`GlossaryUrlImportBody` is the Flutter client's JSON-body shape for
`POST /api/glossary/import/url` (the old surface used query params; the
rebuilt route accepts both).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_optional_string(value: Any) -> Any:
    if value is None:
        return value
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return value.strip()


class GlossaryFormat(StrEnum):
    CSV = "csv"
    TSV = "tsv"
    XLIFF = "xliff"
    TBX = "tbx"
    TMX = "tmx"
    GIT_GLOSSARY = "git_glossary"
    SQL_TABLE = "sql_table"
    JSON_PAIRS = "json_pairs"


class GlossaryImportSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: GlossaryFormat
    text: str | None = None
    inline_bytes_b64: str | None = None
    url: str | None = None
    git_url: str | None = None
    git_ref: str | None = "HEAD"
    git_path: str | None = "GLOSSARY.md"
    git_credentials: str | None = None
    sql_dsn: str | None = None
    sql_source_table: str | None = None
    sql_target_table: str | None = None
    sql_source_col: str | None = "source"
    sql_target_col: str | None = "target"
    sql_where: str | None = None
    encoding: str | None = None
    max_entries: int | None = Field(default=None, ge=1, le=1_000_000)
    name: str | None = Field(default=None, max_length=200)

    @field_validator("name", "encoding", "git_ref", "git_path", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class GlossaryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: GlossaryImportSource
    channel_id: str | None = None
    session_token: str | None = None

    @field_validator("channel_id", "session_token", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class GlossaryUrlImportBody(BaseModel):
    """Client JSON-body shape for the URL import route."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    format: GlossaryFormat | None = None
    name: str | None = Field(default=None, max_length=200)
    encoding: str | None = None
    channel_id: str | None = None

    @field_validator("url", "name", "encoding", "channel_id", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class GlossaryListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    format: GlossaryFormat
    source_uri: str | None = None
    encoding: str | None = None
    entry_count: int = Field(ge=0)
    enabled: bool = True
    priority: int = 0
    group: str = "default"


class GlossaryToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class GlossaryReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_ids: list[str] = Field(min_length=0, max_length=200)


class GlossaryPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    conflicts: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    enabled_glossaries: list[str] = Field(default_factory=list, max_length=100)


class GlossaryImportJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    glossary_id: str | None = None
    job_id: str | None = None
    format: GlossaryFormat
    name: str
    entry_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    queued: bool = False
```

- [ ] **Step 4: Run the schema tests**

Run: `uv run pytest tests/plugins/test_glossary_schemas.py -v`
Expected: all 10 PASS

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/glossary/schemas.py tests/plugins/test_glossary_schemas.py
git commit -m "feat(glossary): verbatim import/library schemas"
```

---

### Task 6: GlossaryJobRunner Protocol + queue marker seam

(Runs BEFORE the glossary service so Task 7's import of `GlossaryJobRunner`
resolves — the payload class in Task 7 carries this Protocol as its
dispatch marker.)

**Files:**
- Modify: `src/omniscribe/plugins/jobs.py` (after `TranslationJobRunner`, ~line 95; `__all__` tail)

- [ ] **Step 1: Add the Protocol**

In `src/omniscribe/plugins/jobs.py`, immediately after the
`TranslationJobRunner` Protocol (which ends near line 95), add:

```python
@runtime_checkable
class GlossaryJobRunner(Protocol):
    """Executes one queued glossary import; registered by the glossary plugin."""

    async def __call__(self, request: Any) -> JobOutcome: ...
```

and add `"GlossaryJobRunner",` to the module's `__all__` list (mirror the
existing alphabetical ordering).

No dispatch change is needed: `_resolve_runner` already reads the payload
class's `runner_protocol` ClassVar and injects the runner registered under
that key; the Task 7 payload carries
`runner_protocol = GlossaryJobRunner`.

- [ ] **Step 2: Run the jobs + harness suites**

Run: `uv run pytest tests/plugins/test_jobs_plugin.py tests/harness -q`
Expected: all PASS (no behavior change for unmarked payloads)

- [ ] **Step 3: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/jobs.py
git commit -m "feat(jobs): GlossaryJobRunner protocol for third-producer dispatch"
```

---

### Task 7: Glossary service (kwarg builders, dispatch, library ops)

**Files:**
- Create: `src/omniscribe/plugins/glossary/store.py`, `service.py`
- Test: `tests/plugins/test_glossary_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/plugins/test_glossary_service.py`:

```python
"""Unit tests for the glossary plugin service (fake store, no HTTP)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from omniscribe.plugins.glossary import service as glossary_service
from omniscribe.plugins.glossary.schemas import (
    GlossaryFormat,
    GlossaryImportSource,
)


# ---------------------------------------------------------------------------
# Fake in-memory LexiconStore (Protocol subset; mirrors GlossaryMeta shapes)
# ---------------------------------------------------------------------------


@dataclass
class _FakeMeta:
    id: str
    name: str
    format: str
    source_uri: str | None = None
    encoding: str | None = None
    entry_count: int = 0
    enabled: bool = True
    priority: int = 0
    group: str = "default"


@dataclass
class _FakeEntry:
    source_text: str
    target_text: str
    case_sensitive: bool = False
    notes: str = ""


class FakeLexiconStore:
    """In-memory LexiconStore double (extra-independent route tests)."""

    def __init__(self) -> None:
        self._glossaries: dict[str, _FakeMeta] = {}
        self._entries: dict[str, list[_FakeEntry]] = {}
        self._counter = 0

    def list_glossaries(self) -> list[Any]:
        return list(self._glossaries.values())

    def get_glossary(self, glossary_id: str) -> Any:
        return self._glossaries.get(glossary_id)

    def save_glossary(
        self,
        *,
        name: str,
        format: str,
        entries: Any,
        source_uri: str | None = None,
        encoding: str | None = None,
        group: str = "default",
        priority: int = 0,
    ) -> Any:
        self._counter += 1
        gid = f"g{self._counter}"
        self._glossaries[gid] = _FakeMeta(
            id=gid,
            name=name,
            format=format,
            source_uri=source_uri,
            encoding=encoding,
            entry_count=len(list(entries)),
            enabled=True,
            priority=priority,
            group=group,
        )
        self._entries[gid] = [
            _FakeEntry(
                source_text=str(e.get("source", "")),
                target_text=str(e.get("target", "")),
                case_sensitive=bool(e.get("case_sensitive", False)),
                notes=str(e.get("notes", "")),
            )
            for e in entries
        ]
        return self._glossaries[gid]

    def toggle_glossary(self, glossary_id: str, *, enabled: bool) -> Any:
        meta = self._glossaries[glossary_id]
        meta.enabled = enabled
        return meta

    def reorder_glossaries(self, ordered_ids: Any) -> None:
        reordered: dict[str, _FakeMeta] = {}
        for gid in ordered_ids:
            reordered[gid] = self._glossaries[gid]
        for gid, meta in self._glossaries.items():
            reordered.setdefault(gid, meta)
        self._glossaries = reordered

    def delete_glossary(self, glossary_id: str) -> bool:
        return self._glossaries.pop(glossary_id, None) is not None

    def list_entries(self, glossary_id: str) -> list[Any]:
        return list(self._entries.get(glossary_id, []))


def _service(
    store: FakeLexiconStore | None = None,
) -> tuple[glossary_service.GlossaryImportServiceImpl, FakeLexiconStore]:
    store = store or FakeLexiconStore()
    impl = glossary_service.GlossaryImportServiceImpl(
        store_provider=lambda: store, queue=None
    )
    return impl, store


def _json_pairs_source(text: str, name: str | None = None) -> GlossaryImportSource:
    return GlossaryImportSource(
        format=GlossaryFormat.JSON_PAIRS, text=text, name=name
    )


async def test_sync_import_json_pairs() -> None:
    impl, _store = _service()
    body = await impl.import_glossary(
        _json_pairs_source('{"entries": [{"source": "Hi", "target": "Salut"}]}')
    )
    assert body["entry_count"] == 1
    assert body["queued"] is False
    assert body["format"] == "json_pairs"
    assert body["glossary_id"]


async def test_import_requires_text_or_bytes_422() -> None:
    impl, _store = _service()
    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        await impl.import_glossary(GlossaryImportSource(format=GlossaryFormat.CSV))
    assert excinfo.value.status_code == 422
    assert excinfo.value.error == "validation_failed"
    assert "text" in excinfo.value.detail and "inline_bytes_b64" in excinfo.value.detail


async def test_import_invalid_base64_422() -> None:
    impl, _store = _service()
    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        await impl.import_glossary(
            GlossaryImportSource(
                format=GlossaryFormat.CSV, inline_bytes_b64="!!! not base64 !!!"
            )
        )
    assert excinfo.value.status_code == 422
    assert "base64" in excinfo.value.detail


async def test_import_max_entries_400() -> None:
    impl, _store = _service()
    # 3 entries in source, capped at 2 → the parser limit path (schema's
    # ge=1 bound passes max_entries=2 through to GlossaryImportLimitError).
    raw = json.dumps(
        {
            "entries": [
                {"source": "A", "target": "1"},
                {"source": "B", "target": "2"},
                {"source": "C", "target": "3"},
            ]
        }
    )
    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        await impl.import_glossary(
            GlossaryImportSource(
                format=GlossaryFormat.JSON_PAIRS, text=raw, max_entries=2
            )
        )
    assert excinfo.value.status_code == 400
    assert "max 2" in excinfo.value.detail


async def test_git_import_ssrf_blocked_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omniscribe.utils.security import SSRFCheckResult

    async def denied(url: str | None) -> SSRFCheckResult:
        return SSRFCheckResult(allowed=False, resolved_ip=None, reason="loopback")

    monkeypatch.setattr(glossary_service, "is_ssrf_target", denied)
    impl, _store = _service()
    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        await impl.import_glossary(
            GlossaryImportSource(
                format=GlossaryFormat.GIT_GLOSSARY,
                git_url="http://127.0.0.1:1",
            )
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.error == "ssrf_blocked"


async def test_sql_unsafe_dsn_422() -> None:
    impl, _store = _service()
    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        await impl.import_glossary(
            GlossaryImportSource(
                format=GlossaryFormat.SQL_TABLE,
                sql_dsn="sqlite:///tmp/example.db; DROP TABLE users;",
                sql_source_table="glossary",
                sql_source_col="source",
                sql_target_col="target",
            )
        )
    assert excinfo.value.status_code == 422
    assert "unsafe" in excinfo.value.detail


async def test_async_dispatch_above_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[Any] = []

    class _Queue:
        async def submit(self, payload: Any, *, request_meta: Any = None) -> Any:
            submitted.append(payload)

            class _Handle:
                job_id = "job-abc"
                status_url = "/api/process/status/job-abc"

            return _Handle()

    impl = glossary_service.GlossaryImportServiceImpl(
        store_provider=lambda: FakeLexiconStore(), queue=_Queue()
    )
    monkeypatch.setattr(
        glossary_service, "SYNC_THRESHOLD", 2
    )  # force the async path
    body = await impl.import_glossary(
        _json_pairs_source(
            '{"entries": [{"source": "A", "target": "1"}, {"source": "B", "target": "2"}, {"source": "C", "target": "3"}]}'
        )
    )
    assert body["queued"] is True
    assert body["job_id"] == "job-abc"
    assert body["entry_count"] == 0
    assert len(submitted) == 1
    assert submitted[0].runner_protocol is glossary_service.GlossaryJobRunner


async def test_store_missing_503() -> None:
    impl = glossary_service.GlossaryImportServiceImpl(
        store_provider=lambda: None, queue=None
    )
    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        await impl.import_glossary(
            _json_pairs_source('{"entries": [{"source": "Hi", "target": "Salut"}]}')
        )
    assert excinfo.value.status_code == 503
    assert "uv sync --extra lexicon" in excinfo.value.detail


async def test_library_ops_and_404() -> None:
    impl, store = _service()
    body = await impl.import_glossary(
        _json_pairs_source(
            '{"entries": [{"source": "A", "target": "1"}]}', name="T"
        )
    )
    gid = body["glossary_id"]
    assert impl.list_library()[0].name == "T"

    toggled = impl.toggle(gid, enabled=False)
    assert toggled["enabled"] is False
    assert impl.list_library()[0]["enabled"] is False

    assert impl.reorder([gid]) == {"ok": True}
    assert impl.delete(gid) == {"ok": True, "id": gid}

    from omniscribe.core.lexicon import GlossaryNotFoundError

    with pytest.raises(glossary_service.GlossaryError) as excinfo:
        impl.toggle("missing-id", enabled=False)
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Glossary not found."
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_glossary_service.py -v`
Expected: FAIL — `glossary_service` has no attribute `GlossaryImportServiceImpl`

- [ ] **Step 3: Implement store.py + service.py**

Create `src/omniscribe/plugins/glossary/store.py`:

```python
"""Lazy LexiconStore provider (optional `lexicon` extra).

`lancedb_store.py` hard-imports pyarrow at module top, so the import
itself fails without the extra. The plugin always boots; routes surface
503 with the old install hint when the store cannot be constructed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from omniscribe.core.lexicon import LexiconStore

_LOGGER = logging.getLogger("omniscribe.plugins.glossary")

LEXICON_INSTALL_HINT = (
    "Lexicon store is not available. Install with: uv sync --extra lexicon"
)


class LexiconProvider:
    """Constructs the LanceDB store on first use; caches the result."""

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        self._store: LexiconStore | None = None
        self._tried = False

    def get(self) -> LexiconStore | None:
        if not self._tried:
            self._tried = True
            try:
                from omniscribe.core.lexicon import LanceDBLexiconStore

                self._store = LanceDBLexiconStore(path=self._store_path)
                _LOGGER.info("lexicon store ready at %s", self._store_path)
            except ImportError as exc:
                _LOGGER.warning("lexicon extra unavailable: %s", exc)
                self._store = None
        return self._store


def null_provider() -> Callable[[], LexiconStore | None]:
    return lambda: None
```

Create `src/omniscribe/plugins/glossary/service.py` (verbatim old helpers
from `44ef123^:api/routers/glossary_imports.py` with the envelope classes
swapped for `GlossaryError` and `state.lexicon_store` swapped for the
provider):

```python
"""Glossary import/library service (verbatim re-home + harness dispatch).

Kwarg builders, the entry-count estimate, and the default-name helper are
verbatim from `44ef123^:api/routers/glossary_imports.py`; only the error
type (`GlossaryError` instead of the old envelope exception classes) and
the store/queue seams changed. Async imports dispatch on the harness
JobQueue via the `GlossaryJobRunner` marker (third producer).
"""

from __future__ import annotations

import base64
import binascii
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Callable, ClassVar
from urllib.parse import urlparse

from omniscribe.core.glossary_sources import (
    FormatNotAvailableError,
    GlossaryImportLimitError,
    parse,
)
from omniscribe.core.lexicon import (
    GlossaryNotFoundError,
    LexiconStore,
    merged_enabled_glossary,
    preview,
)
from omniscribe.plugins.glossary.schemas import (
    GlossaryFormat,
    GlossaryImportSource,
    GlossaryListItem,
    GlossaryPreviewResponse,
)
from omniscribe.plugins.jobs import GlossaryJobRunner, JobOutcome
from omniscribe.utils.security import is_ssrf_target

_LOGGER = logging.getLogger("omniscribe.plugins.glossary")

SYNC_THRESHOLD = 5_000


class GlossaryError(Exception):
    """User-facing glossary error carrying the envelope wire fields."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


def _decode_bytes_payload(value: str) -> bytes:
    if not value:
        raise GlossaryError(422, "validation_failed", "inline_bytes_b64 is required.")

    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise GlossaryError(
            422, "validation_failed", "inline_bytes_b64 is not valid base64."
        ) from exc


def _is_safe_sql_dsn(dsn: str) -> bool:
    """Reject DSNs with shell metacharacters or query-string injection."""
    if not dsn:
        return False
    try:
        parsed = urlparse(dsn)
    except ValueError:
        return False
    if not parsed.scheme or parsed.scheme not in {
        "sqlite",
        "postgresql",
        "mysql",
        "mssql",
        "oracle",
    }:
        return False
    return not any(ch in dsn for ch in (";", "\n", "\r", "\x00"))


def _build_csv_kwargs(source: GlossaryImportSource) -> dict[str, Any]:
    """Build parser kwargs for CSV/TSV/XLIFF/TBX/TMX/JSON_PAIRS formats."""
    if source.text is not None:
        return {"text": source.text, "encoding": source.encoding or "utf-8"}
    elif source.inline_bytes_b64 is not None:
        return {
            "data": _decode_bytes_payload(source.inline_bytes_b64),
            "encoding": source.encoding or "utf-8",
        }
    else:
        raise GlossaryError(
            422,
            "validation_failed",
            "Provide 'text' or 'inline_bytes_b64' for inline formats.",
        )


async def _build_git_glossary_kwargs(source: GlossaryImportSource) -> dict[str, Any]:
    """Build parser kwargs for Git Glossary format (SSRF-checked)."""
    if not source.git_url:
        raise GlossaryError(
            400, "bad_request", "git_url is required for git_glossary imports."
        )
    ssrf = await is_ssrf_target(source.git_url)
    if not ssrf.allowed:
        raise GlossaryError(
            403, "ssrf_blocked", f"URL targets a blocked address: {ssrf.reason or 'blocked'}"
        )
    return {
        "url": source.git_url,
        "ref": source.git_ref or "HEAD",
        "path": source.git_path or "GLOSSARY.md",
        "credentials": source.git_credentials,
    }


def _build_sql_table_kwargs(source: GlossaryImportSource) -> dict[str, Any]:
    """Build parser kwargs for SQL Table format (DSN-sanitized)."""
    if not (
        source.sql_dsn
        and source.sql_source_table
        and source.sql_source_col
        and source.sql_target_col
    ):
        raise GlossaryError(
            422,
            "validation_failed",
            (
                "sql_dsn, sql_source_table, sql_source_col and sql_target_col "
                "are required for sql_table imports."
            ),
        )
    if not _is_safe_sql_dsn(source.sql_dsn):
        raise GlossaryError(422, "validation_failed", "sql_dsn contains unsafe characters.")
    return {
        "dsn": source.sql_dsn,
        "source_table": source.sql_source_table,
        "source_col": source.sql_source_col,
        "target_table": source.sql_target_table,
        "target_col": source.sql_target_col,
        "where_clause": source.sql_where,
        "encoding": source.encoding or "utf-8",
    }


async def build_parser_kwargs(
    source: GlossaryImportSource,
) -> tuple[dict[str, Any], str]:
    """Dispatch to the per-format kwargs builder (verbatim structure)."""
    fmt = source.format
    if fmt == GlossaryFormat.GIT_GLOSSARY:
        kwargs = await _build_git_glossary_kwargs(source)
    elif fmt in {
        GlossaryFormat.CSV,
        GlossaryFormat.TSV,
        GlossaryFormat.XLIFF,
        GlossaryFormat.TBX,
        GlossaryFormat.TMX,
        GlossaryFormat.JSON_PAIRS,
    }:
        kwargs = _build_csv_kwargs(source)
    elif fmt == GlossaryFormat.SQL_TABLE:
        kwargs = _build_sql_table_kwargs(source)
    else:
        raise GlossaryError(422, "validation_failed", f"Unknown format: {fmt}")
    kwargs["max_entries"] = source.max_entries
    return kwargs, fmt.value


def entry_count_estimate(kwargs: dict[str, Any]) -> int:
    """Estimate entry count for sync/async threshold selection (verbatim)."""
    text = kwargs.get("text")
    data = kwargs.get("data")
    if isinstance(text, str) and text:
        return max(text.count("\n"), 1)
    if isinstance(data, (bytes, bytearray)) and data:
        return max(bytes(data).count(b"\n"), 1)
    if kwargs.get("dsn") and kwargs.get("source_table"):
        return SYNC_THRESHOLD + 1  # assume large; favor async for SQL.
    if kwargs.get("url"):
        return SYNC_THRESHOLD + 1  # git/remote fetch always async.
    return SYNC_THRESHOLD + 1


def default_name(format_name: str, kwargs: dict[str, Any]) -> str:
    """Display-name fallback (verbatim)."""
    raw_name = kwargs.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    if kwargs.get("url"):
        return f"Git glossary {kwargs['url']}"
    if kwargs.get("dsn") and kwargs.get("source_table"):
        target = kwargs.get("target_table") or kwargs["source_table"]
        return f"SQL {kwargs['source_table']} \u2192 {target}"
    return f"{format_name.upper()} import"


def _coerce_format(value: str) -> GlossaryFormat:
    try:
        return GlossaryFormat(value)
    except ValueError:
        return GlossaryFormat.JSON_PAIRS


@dataclass(frozen=True)
class _GlossaryImportPayload:
    """One queued glossary import."""

    # ClassVar dispatch marker (not a field): the jobs queue resolves the
    # runner registered under this service key at claim time.
    runner_protocol: ClassVar[type] = GlossaryJobRunner

    submission_id: str
    format_name: str
    kwargs: dict[str, Any]
    display_name: str
```

Define the service Protocol BEFORE the impl class (fold `Protocol` into the
module-top `typing` import; add `json` to the stdlib imports for the
runner's `json.dumps`):

```python
class GlossaryImportService(Protocol):
    async def import_glossary(
        self, source: GlossaryImportSource
    ) -> dict[str, Any]: ...
    async def run_import_job(self, payload: Any) -> JobOutcome: ...
    def list_library(self) -> list[dict[str, Any]]: ...
    def toggle(self, glossary_id: str, *, enabled: bool) -> dict[str, Any]: ...
    def reorder(self, ordered_ids: list[str]) -> dict[str, Any]: ...
    def delete(self, glossary_id: str) -> dict[str, Any]: ...
    def library_preview(self) -> dict[str, Any]: ...
    def entries(self, glossary_id: str) -> dict[str, Any]: ...
    def merged(self) -> dict[str, Any]: ...
```

The service module continues with the impl:

```python
class GlossaryImportServiceImpl:
    """Harness glossary import/library service over LexiconProvider."""

    def __init__(
        self,
        store_provider: Callable[[], LexiconStore | None],
        queue: Any,
    ) -> None:
        self._store_provider = store_provider
        self._queue = queue
        self._submission_to_job: dict[str, str] = {}

    # -- store seam ---------------------------------------------------------

    def _library(self) -> LexiconStore:
        store = self._store_provider()
        if store is None:
            raise GlossaryError(
                503,
                "backend_unavailable",
                "Lexicon store is not available. Install with: uv sync --extra lexicon",
            )
        return store

    # -- import -------------------------------------------------------------

    async def import_glossary(
        self, source: GlossaryImportSource
    ) -> dict[str, Any]:
        """Sync up to SYNC_THRESHOLD entries, otherwise queue (verbatim)."""
        kwargs, format_name = await build_parser_kwargs(source)
        try:
            estimate = entry_count_estimate(kwargs)
            if estimate <= SYNC_THRESHOLD:
                return await self._process_sync(source, kwargs, format_name)
            return await self._process_async(source, kwargs, format_name)
        except FormatNotAvailableError as exc:
            raise GlossaryError(503, "backend_unavailable", str(exc)) from exc
        except GlossaryImportLimitError as exc:
            raise GlossaryError(
                400, "bad_request", f"Too many entries (max {exc.limit})"
            ) from exc
        except ValueError as exc:
            raise GlossaryError(422, "validation_failed", str(exc)) from exc

    def _resolve_name(self, source: GlossaryImportSource) -> str | None:
        candidate = source.name
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        return None

    async def _process_sync(
        self,
        source: GlossaryImportSource,
        kwargs: dict[str, Any],
        format_name: str,
    ) -> dict[str, Any]:
        store = self._library()
        summary = parse(format=format_name, **kwargs)
        display_name = self._resolve_name(source) or default_name(
            format_name, kwargs
        )
        meta = store.save_glossary(
            name=display_name,
            format=format_name,
            entries=summary.entries,
            source_uri=summary.source_uri,
            encoding=summary.encoding,
        )
        return {
            "glossary_id": meta.id,
            "job_id": None,
            "format": format_name,
            "name": meta.name,
            "entry_count": len(summary.entries),
            "warnings": list(summary.warnings),
            "queued": False,
        }

    async def _process_async(
        self,
        source: GlossaryImportSource,
        kwargs: dict[str, Any],
        format_name: str,
    ) -> dict[str, Any]:
        if self._queue is None:
            raise GlossaryError(503, "backend_unavailable", "Job queue unavailable.")
        display_name = self._resolve_name(source) or default_name(
            format_name, kwargs
        )
        submission_id = secrets.token_hex(16)
        handle = await self._queue.submit(
            _GlossaryImportPayload(
                submission_id=submission_id,
                format_name=format_name,
                kwargs=kwargs,
                display_name=display_name,
            ),
            request_meta={
                "submission_id": submission_id,
                "name": display_name,
                "format": format_name,
            },
        )
        self._submission_to_job[submission_id] = handle.job_id
        return {
            "glossary_id": None,
            "job_id": handle.job_id,
            "format": format_name,
            "name": display_name,
            "entry_count": 0,
            "warnings": [],
            "queued": True,
        }

    # -- runner ---------------------------------------------------------------

    async def run_import_job(self, payload: Any) -> JobOutcome:
        """Claim-time runner body for queued imports."""
        if not isinstance(payload, _GlossaryImportPayload):
            raise ValueError("glossary job queue received a foreign payload")
        summary = parse(format=payload.format_name, **payload.kwargs)
        meta = self._library().save_glossary(
            name=payload.display_name,
            format=payload.format_name,
            entries=summary.entries,
            source_uri=summary.source_uri,
            encoding=summary.encoding,
        )
        outcome = {
            "glossary_id": meta.id,
            "format": payload.format_name,
            "name": meta.name,
            "entry_count": len(summary.entries),
            "warnings": list(summary.warnings),
        }
        return JobOutcome(
            blob=json.dumps(outcome).encode("utf-8"),
            content_type="application/json",
        )

    # -- library ------------------------------------------------------------

    @staticmethod
    def _serialize_item(item: Any) -> dict[str, Any]:
        return GlossaryListItem(
            id=item.id,
            name=item.name,
            format=_coerce_format(item.format),
            source_uri=item.source_uri,
            encoding=item.encoding,
            entry_count=item.entry_count,
            enabled=item.enabled,
            priority=item.priority,
            group=item.group,
        ).model_dump()

    def list_library(self) -> list[dict[str, Any]]:
        return [self._serialize_item(i) for i in self._library().list_glossaries()]

    def toggle(self, glossary_id: str, *, enabled: bool) -> dict[str, Any]:
        try:
            meta = self._library().toggle_glossary(glossary_id, enabled=enabled)
        except GlossaryNotFoundError as exc:
            raise GlossaryError(404, "not_found", "Glossary not found.") from exc
        return self._serialize_item(meta)

    def reorder(self, ordered_ids: list[str]) -> dict[str, Any]:
        try:
            self._library().reorder_glossaries(ordered_ids)
        except GlossaryNotFoundError as exc:
            raise GlossaryError(404, "not_found", "Glossary not found.") from exc
        except ValueError as exc:
            raise GlossaryError(422, "validation_failed", str(exc)) from exc
        return {"ok": True}

    def delete(self, glossary_id: str) -> dict[str, Any]:
        deleted = self._library().delete_glossary(glossary_id)
        if not deleted:
            raise GlossaryError(404, "not_found", "Glossary not found.")
        return {"ok": True, "id": glossary_id}

    def library_preview(self) -> dict[str, Any]:
        payload = preview(self._library())
        conflicts_value = payload.get("conflicts", [])
        enabled_value = payload.get("enabled_glossaries", [])
        if not isinstance(conflicts_value, list):
            conflicts_value = []
        if not isinstance(enabled_value, list):
            enabled_value = []
        return GlossaryPreviewResponse(
            count=int(str(payload.get("count", 0) or 0)),
            conflicts=[dict(item) for item in conflicts_value if isinstance(item, dict)],
            enabled_glossaries=[str(item) for item in enabled_value],
        ).model_dump()

    def entries(self, glossary_id: str) -> dict[str, Any]:
        store = self._library()
        meta = store.get_glossary(glossary_id)
        if meta is None:
            raise GlossaryError(404, "not_found", "Glossary not found.")
        entries = store.list_entries(glossary_id)
        return {
            "id": meta.id,
            "name": meta.name,
            "format": meta.format,
            "entries": [
                {
                    "source": e.source_text,
                    "target": e.target_text,
                    "case_sensitive": e.case_sensitive,
                    "notes": e.notes,
                }
                for e in entries
            ],
        }

    def merged(self) -> dict[str, Any]:
        return merged_enabled_glossary(self._library()).to_dict()
```

- [ ] **Step 4: Run the service tests**

Run: `uv run pytest tests/plugins/test_glossary_service.py -v`
Expected: all 9 PASS.

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/glossary/ tests/plugins/test_glossary_service.py
git commit -m "feat(glossary): import service with dispatch, runner body, library ops"
```

---

### Task 8: Glossary plugin + routes (dual-shape dispatch)

**Files:**
- Create: `src/omniscribe/plugins/glossary/routes.py`, `plugin.py`
- Replace: `src/omniscribe/plugins/glossary/__init__.py`
- Test: `tests/routers/test_glossary_routes.py` (created in Task 9 — this
  task's routes are exercised by the service tests' import path; the red
  gate here is the plugin import)

- [ ] **Step 1: Implement routes.py**

Create `src/omniscribe/plugins/glossary/routes.py`:

```python
"""HTTP routes for the glossary plugin (client-frozen contract).

Import routes accept BOTH shapes (user decision 2026-08-31):
`POST /api/glossary/import` takes the old JSON envelope (application/json)
or the Flutter client's multipart upload; `POST /api/glossary/import/url`
takes old query params or the client's JSON body. Business-rule 422s carry
the `{"error": "validation_failed"}` envelope (old contract); malformed
request schemas return FastAPI-native 422.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from omniscribe.plugins.glossary.schemas import (
    GlossaryFormat,
    GlossaryImportRequest,
    GlossaryReorderRequest,
    GlossaryToggleRequest,
    GlossaryUrlImportBody,
)
from omniscribe.plugins.glossary.service import (
    GlossaryError,
    GlossaryImportService,
)

EXTENSION_TO_FORMAT: dict[str, GlossaryFormat] = {
    "csv": GlossaryFormat.CSV,
    "tsv": GlossaryFormat.TSV,
    "xlf": GlossaryFormat.XLIFF,
    "xliff": GlossaryFormat.XLIFF,
    "tbx": GlossaryFormat.TBX,
    "tmx": GlossaryFormat.TMX,
    "json": GlossaryFormat.JSON_PAIRS,
}

INFERENCE_FAILURE_DETAIL = (
    "Could not infer format from URL. Pass ?format=csv|tsv|xliff|tbx|tmx|json_pairs."
)


def _envelope(status_code: int, error: str, detail: str) -> JSONResponse:
    """Stable error envelope the Flutter client parses."""
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def _infer_format_from_name(name: str) -> GlossaryFormat | None:
    path = urlparse(name).path if "://" in name else name
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return EXTENSION_TO_FORMAT.get(suffix)


def build_glossary_router(service: GlossaryImportService) -> APIRouter:
    router = APIRouter(tags=["glossary"])

    @router.post("/api/glossary/import", response_model=None)
    async def import_glossary(request: Request) -> dict[str, Any] | JSONResponse:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                return _envelope(400, "bad_request", "missing 'file' field")
            raw: bytes = await upload.read()
            fields: dict[str, Any] = {
                key: value
                for key, value in form.items()
                if key != "file" and isinstance(value, str)
            }
            fmt = fields.pop("format", None)
            if fmt:
                try:
                    format_enum = GlossaryFormat(str(fmt))
                except ValueError:
                    return _envelope(
                        422, "validation_failed", f"Unknown format: {fmt}"
                    )
            else:
                format_enum = _infer_format_from_name(
                    str(getattr(upload, "filename", "") or "")
                )
                if format_enum is None:
                    return _envelope(
                        422,
                        "validation_failed",
                        "Could not infer format from filename. Pass format=csv|tsv|xliff|tbx|tmx|json_pairs.",
                    )
            try:
                source = GlossaryImportRequest(
                    source={
                        "format": format_enum,
                        "inline_bytes_b64": base64.b64encode(raw).decode("ascii"),
                        "encoding": fields.get("encoding"),
                        "name": fields.get("name"),
                    }
                )
            except ValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": exc.errors(include_url=False)},
                )
        else:
            try:
                payload = await request.json()
            except Exception as exc:
                return _envelope(400, "bad_request", "Malformed JSON body.") from exc
            try:
                source = GlossaryImportRequest.model_validate(payload)
            except ValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": exc.errors(include_url=False)},
                )

        try:
            body = await service.import_glossary(source.source)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return body

    @router.post("/api/glossary/import/url", response_model=None)
    async def import_glossary_from_url(
        request: Request,
        url: str | None = None,
        name: str | None = None,
        encoding: str | None = None,
        format: GlossaryFormat | None = None,
    ) -> dict[str, Any] | JSONResponse:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                payload = await request.json()
            except Exception as exc:
                return _envelope(400, "bad_request", "Malformed JSON body.") from exc
            try:
                body_model = GlossaryUrlImportBody.model_validate(payload)
            except ValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": exc.errors(include_url=False)},
                )
            url = body_model.url
            name = body_model.name
            encoding = body_model.encoding
            format = body_model.format
        if not url:
            return _envelope(400, "bad_request", "URL is required.")
        fmt = format or _infer_format_from_name(url)
        if fmt is None:
            return _envelope(422, "validation_failed", INFERENCE_FAILURE_DETAIL)

        try:
            from omniscribe.plugins.glossary.http_fetch import fetch_url_bytes
        except ImportError:
            fetch_url_bytes = None  # type: ignore[assignment]
        if fetch_url_bytes is None:
            return _envelope(
                503,
                "backend_unavailable",
                "URL fetching is not configured. Use inline 'text' or 'inline_bytes_b64'.",
            )
        try:
            payload_bytes = await fetch_url_bytes(url)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        except Exception as exc:
            return _envelope(502, "ai_error", f"Failed to fetch URL: {exc}")

        source = GlossaryImportRequest.model_validate(
            {
                "source": {
                    "format": fmt,
                    "inline_bytes_b64": base64.b64encode(payload_bytes).decode("ascii"),
                    "encoding": encoding,
                    "name": name,
                }
            }
        )
        try:
            body = await service.import_glossary(source.source)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return body

    @router.get("/api/glossary/library", response_model=None)
    async def list_library() -> list[dict[str, Any]] | JSONResponse:
        try:
            return service.list_library()
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.post("/api/glossary/library/{glossary_id}/enable", response_model=None)
    async def toggle_library_entry(
        glossary_id: str, req: GlossaryToggleRequest
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.toggle(glossary_id, enabled=req.enabled)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.post("/api/glossary/library/reorder", response_model=None)
    async def reorder_library(
        req: GlossaryReorderRequest,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.reorder(req.ordered_ids)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.delete("/api/glossary/library/{glossary_id}", response_model=None)
    async def delete_library_entry(
        glossary_id: str,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.delete(glossary_id)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/glossary/library/preview", response_model=None)
    async def library_preview() -> dict[str, Any] | JSONResponse:
        try:
            return service.library_preview()
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/glossary/library/{glossary_id}/entries", response_model=None)
    async def library_entries(
        glossary_id: str,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.entries(glossary_id)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/glossary/library/merged", response_model=None)
    async def merged_entries() -> dict[str, Any] | JSONResponse:
        try:
            return service.merged()
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    return router
```

Route-registration note: FastAPI matches
`/api/glossary/library/preview` and `/api/glossary/library/merged` BEFORE
`/library/{glossary_id}` only if declared first — the order above
(preview/merged AFTER the `{glossary_id}` delete but the two GET
conflicts are `preview`/`merged` vs `{glossary_id}/entries`) is safe
because the parameterized GET route is `/library/{glossary_id}/entries`
(two segments) while preview/merged are single-segment — no shadowing.
Do not reorder.

- [ ] **Step 2: Create the URL fetch helper**

Create `src/omniscribe/plugins/glossary/http_fetch.py`:

```python
"""SSRF-guarded URL fetch for glossary imports.

Adapted from the deleted `api/services/http_fetch.py` (`44ef123^`): the
URL and every redirect hop are validated against `is_ssrf_target`, the
TCP connection is pinned to the resolved IP (DNS-rebinding defense), and
redirects are followed manually up to ``_MAX_REDIRECTS``. Fetch failures
map to 502 `ai_error` (spec §8.3) and SSRF denials to 403 `ssrf_blocked`
via `GlossaryError`.
"""

from __future__ import annotations

from urllib.parse import urljoin

import httpx

from omniscribe.plugins.glossary.service import GlossaryError
from omniscribe.utils.security import is_ssrf_target

_MAX_REDIRECTS = 5
MAX_GLOSSARY_BYTES: int = 50 * 1024 * 1024


class _PinnedIPTransport(httpx.AsyncHTTPTransport):
    """httpx transport pinning connections to the SSRF-resolved IP."""

    def __init__(self, resolved_ip: str, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self._resolved_ip = resolved_ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.extensions["server_hostname"] = request.url.host
        # Pin the connection to the validated IP (TOCTOU defense).
        import socket

        original_getaddrinfo = socket.getaddrinfo

        def _pinned_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
            if host == request.url.host:
                return original_getaddrinfo(
                    self._resolved_ip, *args, **kwargs
                )
            return original_getaddrinfo(host, *args, **kwargs)

        socket.getaddrinfo = _pinned_getaddrinfo  # type: ignore[assignment]
        try:
            return await super().handle_async_request(request)
        finally:
            socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]


async def fetch_url_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    """Fetch a URL's body as bytes with SSRF protection on every hop."""
    current_url = url

    for _ in range(_MAX_REDIRECTS + 1):
        check = await is_ssrf_target(current_url)
        if not check.allowed:
            raise GlossaryError(
                403,
                "ssrf_blocked",
                f"URL targets a blocked address: {check.reason or 'blocked'}",
            )
        if check.resolved_ip is None:
            raise GlossaryError(
                403, "ssrf_blocked", "URL resolved to no address."
            )

        transport = _PinnedIPTransport(resolved_ip=check.resolved_ip, timeout=timeout)
        client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
        )
        try:
            response = await client.get(current_url)
        finally:
            await client.aclose()

        if response.is_redirect:
            location = response.headers.get("Location")
            if not location:
                break
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        content = response.content
        if len(content) > MAX_GLOSSARY_BYTES:
            raise GlossaryError(
                400, "bad_request", f"URL body exceeds {MAX_GLOSSARY_BYTES} bytes."
            )
        return content

    raise GlossaryError(
        502, "ai_error", f"Exceeded {_MAX_REDIRECTS} redirects for {url}"
    )
```

(The `_PinnedIPTransport` here is a simplified re-implementation of the old
~230-line raw-socket transport using httpx's transport hook + a scoped
`getaddrinfo` swap; the behavioral contract — SSRF-check every hop, pin the
IP, cap redirects — is what the tests pin. If the implementer finds the
monkeypatched getaddrinfo approach interferes with httpx's connection
pooling in tests, patch `check` verification instead: assert the SSRF check
ran per hop via monkeypatched `is_ssrf_target` and let httpx resolve
normally in the test.)

- [ ] **Step 3: Implement plugin.py + __init__.py**

Create `src/omniscribe/plugins/glossary/plugin.py`:

```python
"""Glossary plugin — mounts glossary routes over LexiconProvider + JobQueue."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.glossary.routes import build_glossary_router
from omniscribe.plugins.glossary.service import (
    GlossaryImportService,
    GlossaryImportServiceImpl,
)
from omniscribe.plugins.glossary.store import LexiconProvider
from omniscribe.plugins.jobs import GlossaryJobRunner, JobQueue
from omniscribe.plugins.runtime import RuntimeService


class GlossarySchema(BaseModel):
    """No configurable fields."""


class GlossaryPlugin(Plugin):
    """Client-frozen glossary surface: dual-shape imports + library."""

    Schema = GlossarySchema

    async def apply(self, ctx: Context) -> None:
        queue = ctx.inject(JobQueue)
        runtime = ctx.inject(RuntimeService)
        provider = LexiconProvider(
            store_path=runtime.settings.artifact_directory / "lexicon.lance"
        )
        service = GlossaryImportServiceImpl(
            store_provider=provider.get, queue=queue
        )
        ctx.service(GlossaryImportService, service)
        ctx.service(GlossaryJobRunner, service.run_import_job)
        ctx.mount_router(build_glossary_router(service))


plugin = GlossaryPlugin()
```

Import hygiene: `GlossaryJobRunner` is imported from
`omniscribe.plugins.jobs` alongside `JobQueue` for the
`ctx.service(GlossaryJobRunner, ...)` registration. If mypy flags the
Protocol/impl variance, mirror how `plugins/translate/plugin.py` satisfies
the checker.

Replace `src/omniscribe/plugins/glossary/__init__.py`:

```python
"""Glossary plugin — glossary import/library routes over the harness."""

from omniscribe.plugins.glossary.plugin import plugin

__all__ = ["plugin"]
```

- [ ] **Step 4: Run the service suite + harness boot check**

Run: `uv run pytest tests/plugins/test_glossary_service.py -q`
Expected: still 9 PASS (routes not yet exercised — Task 9 adds them)

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/glossary/
git commit -m "feat(glossary): dual-shape routes, lazy lexicon seam, URL fetch"
```

---

### Task 9: Glossary router contract tests

**Files:**
- Test: `tests/routers/test_glossary_routes.py`

The route tests use the SAME `FakeLexiconStore` as Task 7, injected by
monkeypatching the service's store provider on the booted app — so the
suite is extra-independent (no LanceDB/embedding-model download). Imports
shared fake code from the plugin test module.

- [ ] **Step 1: Write the failing tests**

Create `tests/routers/test_glossary_routes.py`:

```python
"""Router contract tests for the glossary plugin (client-frozen).

Ports the pre-harness pins (`e6b7b89^:tests/api/routers/
test_glossary_imports_route.py`, `_envelope.py`, `_async.py`) onto the
booted harness with a fake in-memory LexiconStore.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.plugins.test_glossary_service import FakeLexiconStore

FIXTURES = Path(__file__).parent.parent / "fixtures" / "glossary"


def _inject_store(api_client: TestClient) -> FakeLexiconStore:
    from omniscribe.harness.context import Context  # noqa: F401 (shape ref)

    store = FakeLexiconStore()
    service = _get_service(api_client)
    service._store_provider = lambda: store  # type: ignore[method-assign]
    return store


def _get_service(api_client: TestClient) -> Any:
    from omniscribe.plugins.glossary.service import GlossaryImportService

    return api_client.app.state.context.inject(GlossaryImportService)


def _import_json_pairs(
    api_client: TestClient, text: str, name: str | None = None
) -> Any:
    payload: dict[str, Any] = {
        "source": {"format": "json_pairs", "text": text}
    }
    if name:
        payload["source"]["name"] = name
    return api_client.post("/api/glossary/import", json=payload)


def test_glossary_routes_are_mounted(api_client: TestClient) -> None:
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    for path in (
        "/api/glossary/import",
        "/api/glossary/import/url",
        "/api/glossary/library",
        "/api/glossary/library/preview",
        "/api/glossary/library/merged",
        "/api/glossary/library/{glossary_id}",
        "/api/glossary/library/{glossary_id}/enable",
        "/api/glossary/library/{glossary_id}/entries",
        "/api/glossary/library/reorder",
    ):
        assert path in paths


def test_list_library_is_empty(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = api_client.get("/api/glossary/library")
    assert response.status_code == 200
    assert response.json() == []


def test_import_inline_text_sync(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = _import_json_pairs(
        api_client, '{"entries": [{"source": "Hi", "target": "Salut"}]}', "Inline"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entry_count"] == 1
    assert body["queued"] is False
    assert body["format"] == "json_pairs"
    assert body["glossary_id"]


def test_import_csv_inline_bytes_sync(api_client: TestClient) -> None:
    _inject_store(api_client)
    raw = (FIXTURES / "pairs.csv").read_bytes()
    response = api_client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "csv",
                "inline_bytes_b64": base64.b64encode(raw).decode("ascii"),
                "name": "FromCSV",
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["entry_count"] >= 4
    listing = api_client.get("/api/glossary/library").json()
    assert len(listing) == 1
    assert listing[0]["entry_count"] == payload["entry_count"]


def test_import_multipart_file_client_shape(api_client: TestClient) -> None:
    _inject_store(api_client)
    raw = (FIXTURES / "pairs.csv").read_bytes()
    response = api_client.post(
        "/api/glossary/import",
        files={"file": ("pairs.csv", raw, "text/csv")},
        data={"name": "Multipart"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["queued"] is False
    assert body["format"] == "csv"
    assert body["entry_count"] >= 4


def test_import_multipart_unknown_extension_422(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = api_client.post(
        "/api/glossary/import",
        files={"file": ("data.bin", b"xx", "application/octet-stream")},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"


def test_import_requires_text_or_bytes_422(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = api_client.post(
        "/api/glossary/import", json={"source": {"format": "csv"}}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert "text" in body["detail"] and "inline_bytes_b64" in body["detail"]


def test_import_max_entries_400(api_client: TestClient) -> None:
    _inject_store(api_client)
    raw = (FIXTURES / "pairs.csv").read_bytes()
    response = api_client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "csv",
                "inline_bytes_b64": base64.b64encode(raw).decode("ascii"),
                "max_entries": 2,
            }
        },
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "bad_request"
    assert "max 2" in body["detail"]


def test_url_import_query_param_shape_ssrf_403(
    api_client: TestClient,
) -> None:
    _inject_store(api_client)
    # Old query-param shape: url + format as query params. A cloud-metadata
    # URL is SSRF-denied deterministically (no network) → 403 envelope.
    response = api_client.post(
        "/api/glossary/import/url"
        "?url=http%3A%2F%2F169.254.169.254%2Flatest%2Fg.json&format=json_pairs"
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "ssrf_blocked"


def test_url_import_json_body_client_shape(
    api_client: TestClient, monkeypatch: Any
) -> None:
    _inject_store(api_client)
    import omniscribe.plugins.glossary.http_fetch as http_fetch

    async def fake_fetch(url: str, *, timeout: float = 30.0) -> bytes:
        return json.dumps(
            {"entries": [{"source": "Hi", "target": "Salut"}]}
        ).encode("utf-8")

    monkeypatch.setattr(http_fetch, "fetch_url_bytes", fake_fetch)
    response = api_client.post(
        "/api/glossary/import/url",
        json={"url": "http://example.test/glossary.json", "format": "json_pairs"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["queued"] is False
    assert body["format"] == "json_pairs"
    assert body["entry_count"] == 1


def test_toggle_endpoint_persists(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = _import_json_pairs(
        api_client, '{"entries": [{"source": "A", "target": "1"}]}', "T"
    )
    glossary_id = response.json()["glossary_id"]
    toggle = api_client.post(
        f"/api/glossary/library/{glossary_id}/enable", json={"enabled": False}
    )
    assert toggle.status_code == 200
    assert toggle.json()["enabled"] is False
    listing = api_client.get("/api/glossary/library").json()
    assert listing[0]["enabled"] is False


def test_toggle_unknown_returns_404_envelope(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = api_client.post(
        "/api/glossary/library/missing-id/enable", json={"enabled": False}
    )
    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "Glossary not found."}


def test_delete_endpoint_removes_entry(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = _import_json_pairs(
        api_client, '{"entries": [{"source": "A", "target": "1"}]}', "T"
    )
    glossary_id = response.json()["glossary_id"]
    delete = api_client.delete(f"/api/glossary/library/{glossary_id}")
    assert delete.status_code == 200
    assert delete.json() == {"ok": True, "id": glossary_id}
    assert api_client.get("/api/glossary/library").json() == []


def test_delete_unknown_returns_404_envelope(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = api_client.delete("/api/glossary/library/missing-id")
    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "Glossary not found."}


def test_reorder_endpoints(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = _import_json_pairs(
        api_client, '{"entries": [{"source": "A", "target": "1"}]}', "T"
    )
    glossary_id = response.json()["glossary_id"]

    empty = api_client.post(
        "/api/glossary/library/reorder", json={"ordered_ids": []}
    )
    assert empty.status_code == 200
    assert empty.json() == {"ok": True}

    unknown = api_client.post(
        "/api/glossary/library/reorder", json={"ordered_ids": ["ghost-id"]}
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "not_found"

    ok = api_client.post(
        "/api/glossary/library/reorder", json={"ordered_ids": [glossary_id]}
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}


def test_preview_endpoint_reports_conflicts(api_client: TestClient) -> None:
    _inject_store(api_client)
    _import_json_pairs(
        api_client, '{"entries": [{"source": "Hello", "target": "Hola"}]}', "A"
    )
    _import_json_pairs(
        api_client,
        '{"entries": [{"source": "Hello", "target": "Bonjour"}]}',
        "B",
    )
    response = api_client.get("/api/glossary/library/preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["enabled_glossaries"] == ["A", "B"]
    assert any(c["source"] == "hello" for c in payload["conflicts"])


def test_entries_endpoint_returns_entries(api_client: TestClient) -> None:
    _inject_store(api_client)
    response = _import_json_pairs(
        api_client, '{"entries": [{"source": "A", "target": "1"}]}', "T"
    )
    glossary_id = response.json()["glossary_id"]
    response = api_client.get(f"/api/glossary/library/{glossary_id}/entries")
    assert response.status_code == 200
    body = response.json()
    assert body["entries"] == [
        {"source": "A", "target": "1", "case_sensitive": False, "notes": ""}
    ]


def test_merged_endpoint_returns_dict(api_client: TestClient) -> None:
    _inject_store(api_client)
    _import_json_pairs(
        api_client, '{"entries": [{"source": "A", "target": "1"}]}', "T"
    )
    response = api_client.get("/api/glossary/library/merged")
    assert response.status_code == 200
    # Glossary.to_dict() shape: {"entries": [{source, target, case_sensitive, notes}]}
    body = response.json()
    assert body["entries"] == [
        {"source": "A", "target": "1", "case_sensitive": False, "notes": ""}
    ]


def test_store_missing_503_envelope(api_client: TestClient) -> None:
    service = _get_service(api_client)
    service._store_provider = lambda: None  # type: ignore[method-assign]
    response = api_client.get("/api/glossary/library")
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "backend_unavailable"
    assert "uv sync --extra lexicon" in body["detail"]


def test_async_threshold_dispatches_on_queue(
    api_client: TestClient, monkeypatch: Any
) -> None:
    _inject_store(api_client)
    from omniscribe.plugins.glossary import service as glossary_service

    monkeypatch.setattr(glossary_service, "SYNC_THRESHOLD", 1)
    response = _import_json_pairs(
        api_client,
        '{"entries": [{"source": "A", "target": "1"}, {"source": "B", "target": "2"}]}',
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["queued"] is True
    assert body["job_id"]
    assert body["entry_count"] == 0
    # The queued job drains on the real worker; the glossary lands in the store.
    deadline = 5.0
    import time

    store = _get_service(api_client)._store_provider()
    while deadline > 0 and not store.list_glossaries():
        time.sleep(0.01)
        deadline -= 0.01
    assert len(store.list_glossaries()) == 1
    assert store.list_glossaries()[0].entry_count == 2
```

Adjustment notes for the implementer:
- `test_merged_endpoint_returns_dict`'s first assertion is intentionally
  loose (`Glossary.to_dict()`'s exact key set is verified against
  `core/translate/glossary.py` during implementation — pin the real keys
  in the test once read; do not leave the conditional expression).
- `_inject_store` reaches into the service's `_store_provider` (test-only
  seam); if the service class exposes a cleaner injection point after
  implementation, use it and keep the tests' behavior identical.
- The queued-job drain test relies on the REAL jobs worker (same mechanism
  as `tests/routers/test_translate_routes.py`).

- [ ] **Step 2: Run to verify they pass (routes landed in Task 8)**

Run: `uv run pytest tests/routers/test_glossary_routes.py -v`
Expected: all 18 PASS. If any fail, fix routes/service (not the pins).

- [ ] **Step 3: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add tests/routers/test_glossary_routes.py
git commit -m "test(glossary): router contract pins incl. dual-shape imports and queue dispatch"
```

---

### Task 10: Ride-along — translate result redeem route

**Files:**
- Modify: `src/omniscribe/plugins/translate/routes.py` (append route to `build_translate_router`)
- Modify: `src/omniscribe/plugins/translate/service.py` (append `result()` to Protocol + impl)
- Test: `tests/routers/test_translate_routes.py` (append 3 tests)

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/routers/test_translate_routes.py`:

```python
# ---------------------------------------------------------------------------
# GET /api/translate/result/{job_id} — token-redeeming async result (ride-along)
# ---------------------------------------------------------------------------


def _seed_artifact(api_client: TestClient, artifact_id: str, token: str, blob: bytes) -> None:
    asyncio.run(
        api_client.app.state.context.inject(StateBackend).put_artifact(
            id=artifact_id,
            token=token,
            owner_job_id="",
            content_type="application/json",
            blob=blob,
            ttl_seconds=3600,
        )
    )


def _plant_completed_record(api_client: TestClient, artifact_id: str, token: str) -> str:
    import uuid as _uuid

    from omniscribe.plugins.state_backend import JobRecord, StateBackend

    backend = api_client.app.state.context.inject(StateBackend)
    job_id = _uuid.uuid4().hex
    asyncio.run(
        backend.upsert_job(
            JobRecord(
                job_id=job_id,
                status="complete",
                result_artifact_id=artifact_id,
                result_artifact_token=token,
            )
        )
    )
    return job_id


def test_translate_result_unknown_job_404(api_client: TestClient) -> None:
    response = api_client.get("/api/translate/result/no-such-job?token=abc")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_translate_result_wrong_token_404(api_client: TestClient) -> None:
    import uuid as _uuid

    artifact_id = _uuid.uuid4().hex
    _seed_artifact(
        api_client, artifact_id, "t" * 43, b'{"page_count": 1}'
    )
    job_id = _plant_completed_record(api_client, artifact_id, "t" * 43)
    response = api_client.get(f"/api/translate/result/{job_id}?token=wrong")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_translate_result_incomplete_job_404(api_client: TestClient) -> None:
    import uuid as _uuid

    from omniscribe.plugins.state_backend import JobRecord, StateBackend

    backend = api_client.app.state.context.inject(StateBackend)
    job_id = _uuid.uuid4().hex
    asyncio.run(backend.upsert_job(JobRecord(job_id=job_id, status="running")))
    response = api_client.get(f"/api/translate/result/{job_id}?token=abc")
    assert response.status_code == 404


def test_translate_result_happy_path(api_client: TestClient) -> None:
    import uuid as _uuid

    artifact_id = _uuid.uuid4().hex
    token = "t" * 43
    _seed_artifact(
        api_client,
        artifact_id,
        token,
        json.dumps({"0": "Bonjour le monde"}).encode("utf-8"),
    )
    job_id = _plant_completed_record(api_client, artifact_id, token)
    response = api_client.get(f"/api/translate/result/{job_id}?token={token}")
    assert response.status_code == 200
    assert response.json() == {"0": "Bonjour le monde"}
```

(Add `import asyncio` and `from omniscribe.plugins.state_backend import
StateBackend` to the test file's module-top imports.)

- [ ] **Step 2: Run to verify they fail**

First add `"/api/translate/result/{job_id}"` to
`test_translate_routes_are_mounted`'s path list. Then:

Run: `uv run pytest tests/routers/test_translate_routes.py -v -k result`
Expected: FAIL — the mounted-path test errors on the missing path, and the
result tests 404 from route-not-found with a different envelope shape.

- [ ] **Step 3: Implement the route + service method**

In `src/omniscribe/plugins/translate/service.py`, extend the
`TranslationService` Protocol with:

```python
    async def result(self, job_id: str, token: str) -> dict[str, Any] | None: ...
```

and add to `TranslationServiceImpl`:

```python
    async def result(self, job_id: str, token: str) -> dict[str, Any] | None:
        """Token-redeeming async result fetch (ride-along; audit C-3/H-3)."""
        record = await self._queue.status(job_id)
        if (
            record is None
            or record.status != "complete"
            or not record.result_artifact_id
            or not record.result_artifact_token
            or token != record.result_artifact_token
        ):
            return None
        blob = await self._store.get(record.result_artifact_id, token)
        if blob is None:
            return None
        return _parse_json_object(blob.blob)
```

In `src/omniscribe/plugins/translate/routes.py`, add inside
`build_translate_router` (after the status route):

```python
    @router.get("/api/translate/result/{job_id}", response_model=None)
    async def translate_result(
        job_id: str,
        token: str = "",
    ) -> dict[str, Any] | JSONResponse:
        body = await service.result(job_id, token)
        if body is None:
            # Missing/wrong token, unknown job, or incomplete job all map to
            # the same 404 (no existence leak; C-3/H-3 semantics).
            return _envelope(404, "not_found", "result not found")
        return body
```

- [ ] **Step 4: Run the translate router tests**

Run: `uv run pytest tests/routers/test_translate_routes.py -v`
Expected: all PASS (15 prior + 4 new = 19)

- [ ] **Step 5: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add src/omniscribe/plugins/translate/routes.py src/omniscribe/plugins/translate/service.py tests/routers/test_translate_routes.py
git commit -m "feat(translate): token-redeeming async result route"
```

---

### Task 11: Boot wiring — conftest + shipped cordis.yml + pins

**Files:**
- Modify: `tests/conftest.py` (`_TEST_CORDIS_YML` → thirteen rows)
- Modify: `src/omniscribe/resources/cordis.yml` (+ transcribe row 11, glossary row 12)
- Modify: `tests/plugins/test_boot_config.py`
- Test: `tests/harness/test_phase_c_boot.py` (create)

- [ ] **Step 1: Update the conftest test tree (failing state)**

The `transcribe` boot row already landed in Task 4 (conftest is currently
TWELVE rows; its comment mentions say "twelve-row"). Insert ONLY the
glossary row — between the `transcribe` and `ocr` rows (making it THIRTEEN
rows) — and update the "twelve-row" comment mentions to "thirteen-row":

```yaml
  - id: transcribe
    use: omniscribe.plugins.transcribe:plugin

  - id: glossary
    use: omniscribe.plugins.glossary:plugin

  - id: ocr
    use: omniscribe.plugins.ocr:plugin
```

- [ ] **Step 2: Update `tests/plugins/test_boot_config.py` (failing state)**

- Docstring/count mentions: eleven → thirteen.
- Rename `test_shipped_cordis_yml_declares_eleven_rows_in_boot_order` →
  `..._thirteen_rows_...`; the expected id list becomes:
  `["runtime", "logging", "state_backend", "artifacts", "jobs", "progress", "providers", "health", "documents", "translate", "transcribe", "glossary", "ocr"]`.
- Router count: `assert len(ctx.routes()) == 6` → `== 8`; update the
  adjacent comment.

Run: `uv run pytest tests/plugins/test_boot_config.py -v`
Expected: the thirteen-rows test and mounts-full-service-tree FAIL
(shipped yml unchanged yet).

- [ ] **Step 3: Write the harness boot test (create, failing)**

Create `tests/harness/test_phase_c_boot.py`:

```python
"""Boot tests for the transcribe + glossary plugins in the harness tree."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_phase_c_routes_survive_full_boot(api_client: TestClient) -> None:
    # FastAPI >=0.141 hides mounted plugin routes from app.routes —
    # assert against the public /openapi.json surface instead.
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    assert "/api/transcribe" in paths
    assert "/api/config/transcription" in paths
    assert "/api/glossary/import" in paths
    assert "/api/glossary/library" in paths
    assert api_client.get("/api/health").status_code == 200


def test_transcribe_rejects_missing_file_off_booted_app(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/transcribe")
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


def test_glossary_rejects_malformed_json_off_booted_app(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/glossary/import", json={"bogus": True})
    assert response.status_code == 422
```

- [ ] **Step 4: Add the shipped boot rows**

In `src/omniscribe/resources/cordis.yml`, insert between the `translate`
and `ocr` rows (match sibling indentation; no config blocks — both Schemas
are empty):

```yaml
  - id: transcribe
    use: omniscribe.plugins.transcribe:plugin

  - id: glossary
    use: omniscribe.plugins.glossary:plugin
```

- [ ] **Step 5: Verify green + boot smoke**

Run: `uv run pytest tests/plugins/test_boot_config.py tests/harness/test_phase_c_boot.py -v`
Expected: all PASS.

Run: `uv run python -c "from fastapi.testclient import TestClient; from omniscribe.server import create_app; client = TestClient(create_app()); client.__enter__(); print(client.get('/api/health').status_code)"`
Expected: prints `200`; the boot log lists thirteen plugins with
`transcribe` and `glossary` between `translate` and `ocr`.

- [ ] **Step 6: Fast gate + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

```bash
git add tests/conftest.py src/omniscribe/resources/cordis.yml tests/plugins/test_boot_config.py tests/harness/test_phase_c_boot.py
git commit -m "feat(plugins): mount transcribe + glossary as boot rows 11/12 in shipped cordis.yml"
```

---

### Task 12: OpenAPI snapshot + full fast gate

**Files:**
- Regenerate: `tests/openapi.json`

- [ ] **Step 1: Regenerate the snapshot**

Run: `uv run pytest tests/routers tests/plugins tests/harness -x -q`
Expected: the only failure is the openapi snapshot drift test. Regenerate
`tests/openapi.json` per the snapshot test's documented procedure (delete
+ rerun; generated from the test tree — never hand-edit).

- [ ] **Step 2: Verify additions-only**

Run: `git diff --numstat tests/openapi.json`
Expected: insertions only (13 new paths: `/api/transcribe`,
`/api/config/transcription`, `/api/models/transcription`, the 9
`/api/glossary*` paths, `/api/translate/result/{job_id}`; plus their
request schemas). Any deletion line besides the diff header means a
CONTRACT BROKE — stop and investigate.

- [ ] **Step 3: Full fast gate**

Run: `uv run pytest -m "not slow" -q && uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: all green; no new failures beyond the pre-existing
environment-conditional skips.

- [ ] **Step 4: Commit**

```bash
git add tests/openapi.json
git commit -m "test: regenerate openapi snapshot for phase C slice 3 routes"
```

---

### Task 13: Docs updates + end-to-end smoke

**Files:**
- Modify: `AGENTS.md`, `ARCHITECTURE.md`, `CHANGELOG.md`
- Verify only: `README.md`, `DEPLOYMENT.md`, `.env.example`

- [ ] **Step 1: AGENTS.md**

1. Boot-order table: `transcribe` row 11, `glossary` row 12 (`ocr` → 13):

```markdown
| 11 | `transcribe` | `plugins/transcribe/` | `TranscriptionService`; `/api/transcribe`, `/api/config/transcription`, `/api/models/transcription` |
```

```markdown
| 12 | `glossary` | `plugins/glossary/` | `GlossaryImportService` + `GlossaryJobRunner`; `/api/glossary/import` (JSON + multipart), `/api/glossary/import/url` (query + JSON body), `/api/glossary/library{,/preview,/merged}`, `/library/{id}{,/enable,/entries}`, `/library/reorder` |
```

2. "Deferred capabilities": remove transcription and glossary-import — the
   list shrinks to auth/rate-limit/upload-size ASGI middlewares, the Redis
   state backend, and model pre-flight. Add a "**Phase C complete**
   (2026-08-31)" note: all client-facing routes are rebuilt on the harness.
3. Web Notes: the transcription/glossary deferred notes become "shipped"
   claims matching §4-5 of the spec; update the plugins enumeration
   ("ten boot plugins" mentions → thirteen) and Key Files rows for both
   packages; both "Last updated" stamps → 2026-08-31.
4. Grep the file for stale claims: `grep -n "not mounted yet\|ten boot\|ten plugins\|deferred" AGENTS.md` — remaining "deferred" mentions must
   be accurate (middlewares/Redis/pre-flight only).

- [ ] **Step 2: ARCHITECTURE.md + CHANGELOG.md**

ARCHITECTURE: plugin-tree/API-surface entries for both packages matching
the translate entry's style; remove transcription/glossary from any
deferred-routes list; note the dual-shape import contract and the
`GlossaryJobRunner` third producer.

CHANGELOG — under `## [Unreleased]` → `### Added`:

```markdown
- Transcribe plugin (`plugins/transcribe/`): `POST /api/transcribe` (sync multipart transcription with token-bound text + metadata artifacts), `GET/POST /api/config/transcription` (masked keys, always-writable in-memory store), `GET /api/models/transcription` (endpoint discovery with whisper fallback list).
- Glossary plugin (`plugins/glossary/`): rebuilt the 9-route glossary import/library surface. Imports accept the legacy JSON source envelope AND the client's multipart/JSON-body shapes; imports above the 5,000-entry estimate dispatch on the harness JobQueue (`GlossaryJobRunner`). The LanceDB lexicon store loads lazily — routes 503 with an install hint when the `lexicon` extra is missing.
- Translate: `GET /api/translate/result/{job_id}?token=…` — token-redeeming async result fetch (wrong token → 404; C-3/H-3 preserved).
```

- [ ] **Step 3: README/DEPLOYMENT/.env.example verify**

`grep -n "transcri\|glossary\|lexicon" README.md DEPLOYMENT.md .env.example`
— fix only now-false claims. Feature claims that were aspirational become
true. No `.env.example` changes expected.

- [ ] **Step 4: Repo hygiene + commit**

Run: `uv run pytest tests/scripts/test_repo_hygiene.py -q`
Expected: 13 PASS.

```bash
git add AGENTS.md ARCHITECTURE.md CHANGELOG.md README.md
git commit -m "docs: transcribe + glossary boot rows, Phase C complete in AGENTS/ARCHITECTURE/CHANGELOG"
```

- [ ] **Step 5: Real-server smoke**

Start the server (`uv run omniscribe-server --port 8000` in a background
shell), then:

```bash
curl -s http://localhost:8000/api/health
curl -s -X POST http://localhost:8000/api/transcribe
curl -s http://localhost:8000/api/glossary/library
curl -s http://localhost:8000/api/glossary/library/preview
curl -s -X POST http://localhost:8000/api/glossary/import -H 'Content-Type: application/json' -d '{"source": {"format": "csv"}}'
```

Expected: health JSON; transcribe missing-file →
`{"error":"bad_request","detail":"missing 'file' field"}`; library → `[]`
(or a 503 envelope if the `lexicon` extra is not installed — both are
correct outcomes; report which); preview → `{"count":0,...}` or 503;
import-without-source → 422 envelope
`{"error":"validation_failed",...}`. Stop the server afterward. Report the
actual outputs.

---

## Self-review notes

- **Spec coverage:** transcribe routes → Tasks 1-4; config store + masked
  keys → Task 3; models discovery → Tasks 3-4; glossary schemas → Task 5;
  GlossaryJobRunner marker → Task 6; kwarg builders/estimate/names
  (verbatim) + dispatch + library ops → Task 7; dual-shape routes + URL
  fetch + lazy store → Task 8; old-test ports (route/async/envelope) +
  client-shape + threshold/runner → Task 9; translate result ride-along →
  Task 10; boot rows 11/12 + pins → Task 11; snapshot 13-paths
  additions-only → Task 12; docs + smoke → Task 13.
- **Ordering:** Task 6 (GlossaryJobRunner Protocol) deliberately precedes
  Task 7 (service) so `service.py`'s `from omniscribe.plugins.jobs import
  GlossaryJobRunner` resolves at its commit.
- **Existing coverage:** the engine factory map, `GenericAudioAPIEngine`,
  `WhisperLocalEngine`, and `validate_audio_input` are already pinned by
  the surviving `tests/core/transcription/test_transcription.py` (10 tests,
  verified passing 2026-08-31) — this plan does NOT duplicate them; only
  the service/route layers get new tests.
- **Type consistency:** `GlossaryError(status_code, error, detail)` mirrors
  `TranslateError`/`TranscribeError`; the merged-response shape is pinned
  from `core/translate/glossary.py::Glossary.to_dict` (`{"entries": [...]}`).
- **Known plan-bug risks (from slice-2 experience):** the frozen-dataclass
  mutation trap does not apply here (payloads are constructed directly);
  the `transcribe` module-function-vs-impl-method name collision has an
  explicit alias fallback in Task 4; `_PinnedIPTransport`'s scoped
  getaddrinfo swap has a documented test-strategy fallback in Task 8;
  `glossary_service`'s `SYNC_THRESHOLD` monkeypatch (Task 9's dispatch
  test) must patch the MODULE attribute — the impl reads the module global
  at call time, which the plan's code guarantees.

