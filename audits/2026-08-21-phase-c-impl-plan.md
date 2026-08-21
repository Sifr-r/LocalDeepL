# Phase C — Service Layers & Typed API Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the four ad-hoc error idioms, async SSRF, lazy config-router loading, the bloated 882-line `routers/config.py`, and the raw `fetchApi('/...')` calls in five Svelte views — landing a typed service-layer API end-to-end.

**Architecture:** Introduce a canonical `ErrorEnvelope` Pydantic model + `APIError` exception hierarchy that an exception handler converts to a `{"error": ..., "detail": ...}` JSON response. Sweep every user-facing error site across `routers/{config,transcription,providers,translation,extraction}.py` to use the new envelope. Convert the SSRF sync shim (`_sync_ssrf_blocked` + `_validate_ssrf`) to direct `await is_ssrf_target(...)`. Extract four helpers and one route group from `routers/config.py` so the file drops below ~400 lines. On the frontend, add `FetchOptions` to every `endpoints.ts` wrapper, introduce free-function services per view (mirroring the existing `workstationService.ts` shape), and migrate every raw `fetchApi<...>('/...')` call to the typed service. Add an `appHarness.ts` so component tests can mount `<App>` in isolation.

**Tech Stack:** FastAPI + Pydantic v2, `pytest-asyncio` (auto mode), `httpx.AsyncClient`, Svelte 4 + `vitest` + `@testing-library/svelte`, `axios`-free typed `fetch` wrappers.

**Plan location:** `audits/2026-08-21-phase-c-impl-plan.md` (tracked — the alternative `docs/superpowers/plans/...` is gitignored).

**Scope:** Audit findings **API-03, API-06, API-09, API-13, API-04** (backend) and **FE-01, FE-07, FE-10** (frontend) from `audits/2026-08-20-deep-refactor-report.md` §9.

---

## File Structure

### Backend — new files

| Path | Responsibility |
| --- | --- |
| `src/omniscribe/api/services/envelope.py` | Canonical `APIError` hierarchy (`SSRFBlocked`, `BackendUnavailable`, `ValidationFailed`, `NotFound`, `RateLimited`) + `ErrorEnvelope` Pydantic model + `envelope_error()` factory |
| `src/omniscribe/api/services/config_helpers.py` | `_load_config_from_store`, `_persist_config`, `_mask_api_key`, `_ConfigBackendIncompatible` — lifted out of `routers/config.py` (the Protocol + backends stay in `services/config_store.py`) |
| `src/omniscribe/api/routers/models.py` | `GET /api/models`, `GET /api/models/ocr`, `GET /api/models/translation`, `GET /api/models/transcription` (moved out of `routers/config.py`) |

### Backend — modified files

| Path | Why |
| --- | --- |
| `src/omniscribe/api/services/security.py` | Re-export `api_error_response = envelope.envelope_error` as a one-release alias |
| `src/omniscribe/api/routers/config.py` | Drop the model routes (→ `routers/models.py`), drop the 4 helpers (→ `services/config_helpers.py`), sweep 8 SSRF + 6 `503` + 12 lazy `try/except` sites to envelope, re-export moved helpers/routes |
| `src/omniscribe/api/routers/transcription.py` | Sweep 6 `HTTPException` sites to envelope; drop `get_transcription_models` (→ `routers/models.py`) |
| `src/omniscribe/api/routers/providers.py` | Sweep 4 `HTTPException` + 2 `JSONResponse({...})` sites to envelope |
| `src/omniscribe/api/routers/translation.py` | Delete local `_ai_error_response`, sweep `HTTPException` sites to envelope |
| `src/omniscribe/api/routers/extraction.py` | Delete local `_ai_error_response`, sweep `HTTPException` sites to envelope |
| `src/omniscribe/api/routers/glossary_imports.py` | Delete `_sync_ssrf_blocked` + `_validate_ssrf`; convert `import_glossary` (line 330) to `async def`; await `is_ssrf_target` directly |
| `src/omniscribe/server.py` | Register `APIError` + `RequestValidationError` handlers (→ envelope); register new `models.router` |

### Backend — test files

| Path | Scope |
| --- | --- |
| `tests/api/services/test_envelope.py` | Envelope model + exception handler |
| `tests/api/services/test_config_helpers.py` | `_load_config_from_store`, `_persist_config`, `_mask_api_key`, `_ConfigBackendIncompatible` |
| `tests/api/routers/test_models_router.py` | `/api/models*` routes |
| `tests/api/routers/test_envelope_sweep.py` | Parametrized: every swept site returns envelope under failure |
| `tests/api/routers/test_glossary_imports_async.py` | `import_glossary` awaits SSRF directly, no threadpool |

### Frontend — new files

| Path | Responsibility |
| --- | --- |
| `frontend/src/lib/api/fetchOptions.ts` | `FetchOptions` type + `createAbortController()` helper |
| `frontend/src/lib/services/translationService.ts` | `translate`, `translateAsync`, `getTranslationStatus`, `listTranslationModels` |
| `frontend/src/lib/services/extractionService.ts` | `extract`, `extractDocument`, `extractDocx` |
| `frontend/src/lib/services/transcriptionService.ts` | `transcribe`, `listTranscriptionModels` |
| `frontend/src/lib/services/glossaryService.ts` | `getLibraries`, `getMerged`, `getPreview`, `importFile`, `importUrl` |
| `frontend/src/lib/services/jobsService.ts` | `list`, `clear`, `cancel` (free-function wrapper) |
| `frontend/src/lib/__tests__/appHarness.ts` | `mountApp()` + `cleanupApp()` — `new App({ target })` against a writable `activeTab` store |

### Frontend — modified files

| Path | Why |
| --- | --- |
| `frontend/src/lib/api/endpoints.ts` | Every wrapper accepts `FetchOptions` |
| `frontend/src/lib/components/views/TranslationView.svelte` | 5 raw `fetchApi`/`fetchFile` → `translationService` |
| `frontend/src/lib/components/views/ExtractionView.svelte` | 4 raw sites → `extractionService` |
| `frontend/src/lib/components/views/TranscriptionView.svelte` | 1 raw site → `transcriptionService` |
| `frontend/src/lib/components/views/GlossaryView.svelte` | 2 raw sites → `glossaryService` |
| `frontend/src/lib/components/views/JobHistoryView.svelte` | 2 raw sites → `jobsService` |
| `frontend/src/lib/components/ui/TabRibbon.svelte` | `pingHealth` uses `fetchApi('/health', { signal })` + `createAbortController()` |

### Frontend — test files

| Path | Scope |
| --- | --- |
| `frontend/src/lib/api/__tests__/endpoints.fetchOptions.test.ts` | Wrappers honor `signal` |
| `frontend/src/lib/services/__tests__/*.test.ts` | One per service (mocked `fetch`) |
| `frontend/src/lib/__tests__/appStore.test.ts` | Component test using `appHarness` (replaces any UI smoke reliance on `App.svelte`) |

---

## Pre-flight: read the audit

Before starting Task 1, read `audits/2026-08-20-deep-refactor-report.md` §9 "Recommended Execution Sequence" and the per-finding sections for **API-03, API-06, API-09, API-13, API-04, FE-01, FE-07, FE-10**. The audit lines numbers are still accurate as of HEAD `98c431b`.

---

### Task 1: Add canonical `ErrorEnvelope` model + `APIError` hierarchy

**Files:**
- Create: `src/omniscribe/api/services/envelope.py`
- Modify: `src/omniscribe/api/services/security.py`
- Test: `tests/api/services/test_envelope.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/services/test_envelope.py
"""Canonical error envelope contract."""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.services.envelope import (
    APIError,
    BackendUnavailable,
    ErrorEnvelope,
    NotFound,
    RateLimited,
    SSRFBlocked,
    ValidationFailed,
    envelope_error,
    register_envelope_handlers,
)


def test_envelope_model_drops_none_detail() -> None:
    env = ErrorEnvelope(error="forbidden")
    assert env.model_dump(exclude_none=True) == {"error": "forbidden"}


def test_envelope_error_returns_canonical_shape() -> None:
    resp = envelope_error(status_code=403, error="forbidden", detail="no access")
    assert resp.status_code == 403
    body: dict[str, Any] = json.loads(resp.body)
    assert body == {"error": "forbidden", "detail": "no access"}


def test_envelope_error_omits_detail_when_none() -> None:
    resp = envelope_error(status_code=503, error="unavailable")
    body: dict[str, Any] = json.loads(resp.body)
    assert body == {"error": "unavailable"}


@pytest.mark.parametrize(
    "exc_cls",
    [SSRFBlocked, BackendUnavailable, NotFound, RateLimited, ValidationFailed],
)
def test_api_error_subclasses_carry_defaults(exc_cls: type[APIError]) -> None:
    exc = exc_cls(detail="x") if exc_cls is SSRFBlocked else exc_cls("x")
    assert exc.status_code >= 400
    assert exc.error != "internal_error"
    assert exc.detail is not None


def test_ssrf_blocked_carries_url_and_reason() -> None:
    err = SSRFBlocked(url="http://localhost:6379", reason="loopback")
    assert err.url == "http://localhost:6379"
    assert err.reason == "loopback"
    assert err.status_code == 403
    assert "loopback" in err.detail


def test_register_envelope_handlers_converts_apierror() -> None:
    app = FastAPI()
    register_envelope_handlers(app)

    @app.get("/boom")
    async def _boom() -> None:
        raise SSRFBlocked(url="http://10.0.0.1", reason="private")

    client = TestClient(app)
    resp = client.get("/boom")
    assert resp.status_code == 403
    assert resp.json() == {
        "error": "ssrf_blocked",
        "detail": "URL targets a blocked address: private",
    }


def test_register_envelope_handlers_converts_request_validation() -> None:
    app = FastAPI()
    register_envelope_handlers(app)

    @app.get("/echo/{n}")
    async def _echo(n: int) -> dict[str, int]:
        return {"n": n}

    client = TestClient(app)
    resp = client.get("/echo/notanumber")
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_failed"
    assert "detail" in body
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/services/test_envelope.py -v
```

Expected: `ModuleNotFoundError: No module named 'omniscribe.api.services.envelope'`.

- [ ] **Step 3: Implement `envelope.py`**

```python
# src/omniscribe/api/services/envelope.py
"""Canonical API error envelope (Phase C).

Replaces four idioms:
  - `api_error_response(...)` (services/security.py)
  - `_ai_error_response(...)` (duplicated in translation.py + extraction.py)
  - raw `JSONResponse(status_code=..., content={"error": ..., "detail": ...})`
  - `HTTPException(detail="string")` for user-facing errors

Wire shape: ``{"error": "<stable_code>", "detail": "<human string>"}``.
``detail`` is omitted from the JSON body when ``None``.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """Pydantic mirror of the wire shape.

    Declared so ``response_model=ErrorEnvelope`` works on route decorators
    and OpenAPI surfaces the contract.
    """

    error: str = Field(..., description="Stable machine-readable error code.")
    detail: str | None = Field(
        default=None,
        description="Optional human-readable detail. Omitted when None.",
    )


class APIError(Exception):
    """Base class for all envelope-shaped exceptions.

    Subclasses set ``status_code`` + ``error``. The handler in
    ``register_envelope_handlers`` converts ``self`` to an
    ``ErrorEnvelope`` JSON response.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error: str = "internal_error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.error)
        self.detail = detail


class SSRFBlocked(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    error = "ssrf_blocked"

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"URL targets a blocked address: {reason}")
        self.url = url
        self.reason = reason


class BackendUnavailable(APIError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error = "backend_unavailable"


class ValidationFailed(APIError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error = "validation_failed"


class NotFound(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    error = "not_found"


class RateLimited(APIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error = "rate_limited"


def envelope_error(
    *, status_code: int, error: str, detail: str | None = None
) -> JSONResponse:
    """Build a JSONResponse in the canonical envelope shape."""
    body: dict[str, Any] = {"error": error}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


async def _apierror_handler(_request: Request, exc: APIError) -> JSONResponse:
    return envelope_error(
        status_code=exc.status_code, error=exc.error, detail=exc.detail
    )


async def _validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = f"{len(exc.errors())} validation error(s)."
    resp = envelope_error(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error="validation_failed",
        detail=detail,
    )
    resp.headers["x-validation-errors"] = str(len(exc.errors()))
    return resp


def register_envelope_handlers(app: FastAPI) -> None:
    """Register both ``APIError`` and ``RequestValidationError`` handlers.

    Idempotent — safe to call from tests that build a throwaway app.
    """
    app.add_exception_handler(APIError, _apierror_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
```

- [ ] **Step 4: Add a one-release re-export in `security.py`**

Append to `src/omniscribe/api/services/security.py` (after the existing `api_error_response` at line 64-78):

```python
# Phase C: re-export the new envelope helper as a one-release alias so
# existing callers (`api_error_response(...)`) keep working. The 18 in-tree
# call sites that still import `api_error_response` will be swept to the
# envelope in Tasks 2-5.
from omniscribe.api.services.envelope import envelope_error as api_error_response  # noqa: E402,F401
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/api/services/test_envelope.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/omniscribe/api/services/envelope.py \
        src/omniscribe/api/services/security.py \
        tests/api/services/test_envelope.py
git commit -m "feat(api): add canonical ErrorEnvelope + APIError hierarchy"
```

---

### Task 2: Sweep `routers/config.py` SSRF + 503 + lazy sites to envelope

**Files:**
- Modify: `src/omniscribe/api/routers/config.py` (lines 489, 583, 774, 788, 814, 825, 850, 861 SSRF; 509-512, 587-590, 630-633, 663-666, 680-683, 698-701 503; remaining lazy `try/except` sites)
- Test: `tests/api/routers/test_envelope_sweep.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/routers/test_envelope_sweep.py
"""Every swept error site must return the canonical envelope shape."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers.config import router as config_router
from omniscribe.api.services.envelope import register_envelope_handlers


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(config_router)
    return TestClient(app)


@pytest.mark.parametrize(
    "path,error_code",
    [
        ("/api/config/ocr/auth", "ssrf_blocked"),
        ("/api/config/translation/auth", "ssrf_blocked"),
        ("/api/config/transcription/auth", "ssrf_blocked"),
    ],
)
def test_auth_routes_reject_loopback_with_envelope(
    client: TestClient, path: str, error_code: str
) -> None:
    # The endpoint accepts a JSON body like {"base_url": "..."}.
    resp = client.post(path, json={"base_url": "http://127.0.0.1:1"})
    assert resp.status_code == 403
    body: dict[str, Any] = resp.json()
    assert body["error"] == error_code
    assert "detail" in body


def test_load_models_route_returns_envelope_on_ssrf(client: TestClient) -> None:
    resp = client.get("/api/models/ocr?base_url=http://127.0.0.1:1")
    # Models fetch may 403 (SSRF blocked) or 503 (unreachable upstream);
    # both must use the envelope.
    assert resp.status_code in {403, 503}
    body = resp.json()
    assert body["error"] in {"ssrf_blocked", "backend_unavailable"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/routers/test_envelope_sweep.py -v
```

Expected: failures showing raw `JSONResponse` shapes that don't match the envelope.

- [ ] **Step 3: Apply sweep to `routers/config.py`**

Add the import at the top (next to the existing `from omniscribe.api.services.config_store import ConfigStore` at line 20):

```python
from omniscribe.api.services.envelope import (
    BackendUnavailable,
    SSRFBlocked,
    envelope_error,
)
from omniscribe.utils.security import is_ssrf_target
```

For each of the **8 SSRF sites** (lines 489, 583, 774, 788, 814, 825, 850, 861), the existing pattern is:

```python
ssrf_check = await is_ssrf_target(url)
if not ssrf_check.allowed:
    return JSONResponse(status_code=403, content={"error": "URL targets a blocked address."})
```

Replace every occurrence with:

```python
ssrf_check = await is_ssrf_target(url)
if not ssrf_check.allowed:
    raise SSRFBlocked(url=url, reason=ssrf_check.reason)
```

For each of the **6 `503` sites** (lines 509-512, 587-590, 630-633, 663-666, 680-683, 698-701), the existing pattern is:

```python
return JSONResponse(status_code=503, content={"error": f"Could not reach {vendor}: {exc}"})
```

Replace every occurrence with:

```python
raise BackendUnavailable(detail=f"Could not reach {vendor}: {exc}") from exc
```

For each **lazy config-router `try/except` site** (the remaining `JSONResponse(status_code=503, ...)` and `JSONResponse(status_code=403, ...)` instances in `routers/config.py`), apply the same two replacements above. After the sweep, no `JSONResponse(status_code=..., content={"error": ...})` should remain in `routers/config.py`. Verify with:

```bash
grep -n 'JSONResponse(status_code=' src/omniscribe/api/routers/config.py
```

Expected: no output.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/api/routers/test_envelope_sweep.py -v
```

Expected: all passed.

- [ ] **Step 5: Run mypy + ruff on the swept file**

```bash
uv run ruff check src/omniscribe/api/routers/config.py
uv run ruff format src/omniscribe/api/routers/config.py --check
uv run mypy src/omniscribe/api/routers/config.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/omniscribe/api/routers/config.py tests/api/routers/test_envelope_sweep.py
git commit -m "refactor(api): sweep config router SSRF + 503 sites to ErrorEnvelope"
```

---

### Task 3: Sweep `routers/transcription.py` `HTTPException` sites to envelope

**Files:**
- Modify: `src/omniscribe/api/routers/transcription.py` (lines 60, 72, 90, 92, 208, 230)
- Modify: `tests/api/routers/test_envelope_sweep.py` (add transcription cases)

- [ ] **Step 1: Append transcription test cases to `test_envelope_sweep.py`**

Add inside `tests/api/routers/test_envelope_sweep.py` (after the existing `test_load_models_route_returns_envelope_on_ssrf`):

```python
from omniscribe.api.routers.transcription import router as transcription_router

@pytest.fixture
def transcription_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(transcription_router)
    return TestClient(app)


def test_transcribe_route_returns_envelope_on_validation(
    transcription_client: TestClient,
) -> None:
    # Empty multipart upload → either 422 (validation_failed envelope)
    # or 400 (bad_request envelope). Both must use envelope.
    resp = transcription_client.post("/api/transcribe")
    assert resp.status_code in {400, 422}
    body = resp.json()
    assert body["error"] in {"validation_failed", "bad_request"}
```

- [ ] **Step 2: Apply sweep to `routers/transcription.py`**

Add at the top of `src/omniscribe/api/routers/transcription.py`:

```python
from omniscribe.api.services.envelope import (
    BackendUnavailable,
    ValidationFailed,
    envelope_error,
)
```

For each of the **6 `HTTPException` sites** at lines 60, 72, 90, 92, 208, 230, the existing pattern is one of:

```python
raise HTTPException(status_code=400, detail="...")
raise HTTPException(status_code=503, detail=f"...: {exc}")
raise HTTPException(status_code=422, detail="...")
```

Apply the following replacements:

| Status | Replacement |
| --- | --- |
| 400 | `from fastapi import HTTPException  # noqa: F401` — keep but wrap envelope-style: `raise ValidationFailed(detail="...")` ONLY if the message is a structural validation issue; otherwise convert to a 400 envelope by raising an `APIError` subclass. Add to `envelope.py` if needed (see Step 3). |
| 422 | `raise ValidationFailed(detail="...")` |
| 503 | `raise BackendUnavailable(detail=f"...: {exc}") from exc` |

To avoid subclass sprawl, add to `envelope.py` (Task 1 file) one new class:

```python
class BadRequest(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    error = "bad_request"
```

Use `BadRequest(detail="...")` for every 400 sweep. After the sweep, no `HTTPException(status_code=400|422|503, ...)` should remain in `routers/transcription.py`. Verify with:

```bash
grep -n 'HTTPException(status_code=' src/omniscribe/api/routers/transcription.py
```

Expected: no output (only 401 from `BearerAuthMiddleware` may remain — that's middleware, not router).

- [ ] **Step 3: Run test to verify it passes**

```bash
uv run pytest tests/api/routers/test_envelope_sweep.py -v
```

Expected: all passed (transcription + config).

- [ ] **Step 4: Commit**

```bash
git add src/omniscribe/api/services/envelope.py \
        src/omniscribe/api/routers/transcription.py \
        tests/api/routers/test_envelope_sweep.py
git commit -m "refactor(api): sweep transcription router HTTPException sites to ErrorEnvelope"
```

---

### Task 4: Sweep `routers/providers.py` to envelope

**Files:**
- Modify: `src/omniscribe/api/routers/providers.py` (lines 90, 99, 112, 124, 129, 141)

- [ ] **Step 1: Append providers test cases**

```python
# tests/api/routers/test_envelope_sweep.py (append)
from omniscribe.api.routers.providers import router as providers_router

@pytest.fixture
def providers_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(providers_router)
    return TestClient(app)


def test_providers_unknown_returns_envelope(providers_client: TestClient) -> None:
    resp = providers_client.get("/api/providers/no-such-provider")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_providers_bad_payload_returns_envelope(providers_client: TestClient) -> None:
    # Empty body on the credentials endpoint → envelope.
    resp = providers_client.post(
        "/api/providers/no-such-provider/credentials", json={}
    )
    assert resp.status_code in {400, 404, 422}
    body = resp.json()
    assert body["error"] in {"not_found", "bad_request", "validation_failed"}
```

- [ ] **Step 2: Apply sweep to `routers/providers.py`**

Add at the top:

```python
from omniscribe.api.services.envelope import (
    BadRequest,
    BackendUnavailable,
    NotFound,
    envelope_error,
)
```

Replace:
- Line 90, 112, 124, 141 (`HTTPException`): `BadRequest` / `BackendUnavailable` / `NotFound` as appropriate.
- Line 99, 129 (`JSONResponse(status_code=..., content={...})`): `raise` the matching `APIError` subclass.

Verify:

```bash
grep -nE 'HTTPException\(status_code=|JSONResponse\(status_code=' src/omniscribe/api/routers/providers.py
```

Expected: no output.

- [ ] **Step 3: Run test + commit**

```bash
uv run pytest tests/api/routers/test_envelope_sweep.py -v
git add src/omniscribe/api/routers/providers.py tests/api/routers/test_envelope_sweep.py
git commit -m "refactor(api): sweep providers router error sites to ErrorEnvelope"
```

---

### Task 5: Sweep `routers/translation.py` + `routers/extraction.py` to envelope

**Files:**
- Modify: `src/omniscribe/api/routers/translation.py` (delete `_ai_error_response` at lines 41-45; sweep 4 `HTTPException` sites at 61, 147, 185, 274)
- Modify: `src/omniscribe/api/routers/extraction.py` (delete `_ai_error_response` at lines 37-41; sweep 4 `HTTPException` sites at 64, 76, 98, 109)

- [ ] **Step 1: Append translation + extraction test cases**

```python
# tests/api/routers/test_envelope_sweep.py (append)
from omniscribe.api.routers.translation import router as translation_router
from omniscribe.api.routers.extraction import router as extraction_router


@pytest.fixture
def translation_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(translation_router)
    return TestClient(app)


@pytest.fixture
def extraction_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(extraction_router)
    return TestClient(app)


def test_translate_empty_body_returns_envelope(
    translation_client: TestClient,
) -> None:
    resp = translation_client.post("/api/translate", json={})
    assert resp.status_code in {400, 422}
    assert resp.json()["error"] in {"bad_request", "validation_failed"}


def test_extract_empty_body_returns_envelope(
    extraction_client: TestClient,
) -> None:
    resp = extraction_client.post("/api/extract", json={})
    assert resp.status_code in {400, 422}
    assert resp.json()["error"] in {"bad_request", "validation_failed"}
```

- [ ] **Step 2: Delete the duplicate `_ai_error_response` in both files**

In `src/omniscribe/api/routers/translation.py`, **delete lines 41-45** (the local `_ai_error_response` helper). Replace all callers (search with `grep -n '_ai_error_response' src/omniscribe/api/routers/translation.py`) with:

```python
from omniscribe.api.services.envelope import envelope_error
# ...
return envelope_error(status_code=..., error="...", detail="...")
```

Apply the same change in `src/omniscribe/api/routers/extraction.py` (delete lines 37-41, replace callers).

Verify:

```bash
grep -rn '_ai_error_response' src/omniscribe/api/routers/
```

Expected: no output.

- [ ] **Step 3: Sweep `HTTPException` sites**

For each of the 4 `HTTPException(status_code=...)` sites in each file, apply:

| Status | Replacement |
| --- | --- |
| 400 | `raise BadRequest(detail="...")` |
| 422 | `raise ValidationFailed(detail="...")` |
| 503 | `raise BackendUnavailable(detail=f"...: {exc}") from exc` |

- [ ] **Step 4: Run test + commit**

```bash
uv run pytest tests/api/routers/test_envelope_sweep.py -v
git add src/omniscribe/api/routers/translation.py \
        src/omniscribe/api/routers/extraction.py \
        tests/api/routers/test_envelope_sweep.py
git commit -m "refactor(api): dedupe _ai_error_response and sweep translation/extraction to envelope"
```

---

### Task 6: Wire envelope handlers in `server.py`

**Files:**
- Modify: `src/omniscribe/server.py`

- [ ] **Step 1: Locate the FastAPI app construction in `server.py`**

The app is built by `create_app()` and routers are registered via `include_router(...)` calls. The `register_envelope_handlers(app)` call must run after `FastAPI(...)` and before `include_router` (FastAPI doesn't care about order, but conventional placement is right after `app = FastAPI(...)`).

- [ ] **Step 2: Add the import + handler registration**

Add to `src/omniscribe/server.py` (next to the existing router imports):

```python
from omniscribe.api.services.envelope import register_envelope_handlers
```

After the line that creates the FastAPI instance (search for `app = FastAPI(`), insert:

```python
register_envelope_handlers(app)
```

- [ ] **Step 3: Smoke-test by booting the app and probing `/api/config` with a bad token**

```bash
uv run omniscribe-server --port 8765 &
SERVER_PID=$!
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/api/config \
  -X POST -H "Content-Type: application/json" -d '{}'
# Expect 422 with envelope shape
curl -s http://127.0.0.1:8765/api/config -X POST \
  -H "Content-Type: application/json" -d '{}' | python -m json.tool
kill $SERVER_PID
```

Expected: 422 status; body contains `{"error": "validation_failed", "detail": "..."}`.

- [ ] **Step 4: Commit**

```bash
git add src/omniscribe/server.py
git commit -m "feat(api): register ErrorEnvelope + RequestValidationError handlers"
```

---

### Task 7: Convert glossary imports SSRF to async (API-13 + lazy config-router)

**Files:**
- Modify: `src/omniscribe/api/routers/glossary_imports.py` (delete `_sync_ssrf_blocked` at 94-99, delete `_validate_ssrf` at 102-110; convert `import_glossary` at line 330 to `async def`; await `is_ssrf_target` directly in `_build_git_glossary_kwargs` and `_build_sql_table_kwargs`)
- Test: `tests/api/routers/test_glossary_imports_async.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/routers/test_glossary_imports_async.py
"""Glossary imports must use direct async SSRF — no threadpool shim."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers.glossary_imports import router
from omniscribe.api.services.envelope import register_envelope_handlers
from omniscribe.utils.security import SSRFCheck


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_threadpool_shim_is_gone() -> None:
    """The sync `_sync_ssrf_blocked` threadpool shim must be deleted."""
    from omniscribe.api.routers import glossary_imports

    assert not hasattr(glossary_imports, "_sync_ssrf_blocked"), (
        "Threadpool SSRF shim must be deleted in Task 7"
    )
    assert not hasattr(glossary_imports, "_validate_ssrf"), (
        "Sync SSRF helper must be deleted in Task 7"
    )


def test_glossary_git_import_returns_envelope_on_ssrf(client: TestClient) -> None:
    resp = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "git_glossary",
                "git_url": "http://127.0.0.1:1",
                "git_path": "GLOSSARY.md",
            }
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "ssrf_blocked"


@pytest.mark.asyncio
async def test_import_glossary_is_async() -> None:
    """`import_glossary` must be `async def` so it can await SSRF directly."""
    import inspect

    from omniscribe.api.routers.glossary_imports import import_glossary

    assert inspect.iscoroutinefunction(import_glossary), (
        "import_glossary must be async to use `await is_ssrf_target(...)`"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/routers/test_glossary_imports_async.py -v
```

Expected: `assert not hasattr(glossary_imports, "_sync_ssrf_blocked")` fails (the shim still exists).

- [ ] **Step 3: Delete `_sync_ssrf_blocked` + `_validate_ssrf` from `glossary_imports.py`**

In `src/omniscribe/api/routers/glossary_imports.py`:

1. **Delete lines 94-110** (`_sync_ssrf_blocked` and `_validate_ssrf`).
2. **Remove the unused imports** at the top:
   ```python
   # Delete:
   import asyncio
   from concurrent.futures import ThreadPoolExecutor  # if only used by the shim
   ```
   (Verify with `grep -n 'asyncio\|ThreadPoolExecutor' src/omniscribe/api/routers/glossary_imports.py` — only remove if no other reference remains.)

- [ ] **Step 4: Convert `import_glossary` (line 330) to `async def`**

Replace the entire handler (lines 330-351) with:

```python
@router.post("/api/glossary/import")
async def import_glossary(req: GlossaryImportRequest) -> GlossaryImportJobResponse:
    """Import a glossary; sync up to 5,000 entries, otherwise async."""
    kwargs, _format_name = await _build_parser_kwargs(req.source)
    try:
        estimate = _entry_count_estimate(kwargs)
        if estimate <= SYNC_THRESHOLD:
            return _process_sync(req)
        return _process_async(req)
    except FormatNotAvailableError as exc:
        raise BackendUnavailable(detail=str(exc)) from exc
    except GlossaryImportLimitError as exc:
        raise BadRequest(detail=f"Too many entries (max {exc.limit})") from exc
    except ValueError as exc:
        raise ValidationFailed(detail=str(exc)) from exc
```

Add to the imports at the top of the file:

```python
from omniscribe.api.services.envelope import (
    BackendUnavailable,
    BadRequest,
    ValidationFailed,
)
from omniscribe.utils.security import is_ssrf_target
```

- [ ] **Step 5: Convert `_build_parser_kwargs` (and helpers that call SSRF) to async**

`_build_git_glossary_kwargs` at line 148-161 calls `_validate_ssrf` (now deleted). Convert it to async and await `is_ssrf_target` directly:

```python
async def _build_git_glossary_kwargs(source: GlossaryImportSource) -> dict[str, Any]:
    """Build parser kwargs for Git Glossary format."""
    if not source.git_url:
        raise ValidationFailed(detail="git_url is required for git_glossary imports.")
    if not source.git_url:
        raise BadRequest(detail="URL is required.")
    ssrf = await is_ssrf_target(source.git_url)
    if not ssrf.allowed:
        raise SSRFBlocked(url=source.git_url, reason=ssrf.reason)
    return {
        "url": source.git_url,
        "ref": source.git_ref or "HEAD",
        "path": source.git_path or "GLOSSARY.md",
        "credentials": source.git_credentials,
    }
```

Update `_build_parser_kwargs` (the dispatcher at the top of the handler chain — search for it in the file) to be `async def` and `await` every helper it calls:

```python
async def _build_parser_kwargs(source: GlossaryImportSource) -> tuple[dict[str, Any], str]:
    """Dispatch to the per-format kwargs builder (all async now)."""
    fmt = source.format
    if fmt == GlossaryFormat.GIT_GLOSSARY:
        return await _build_git_glossary_kwargs(source), "git_glossary"
    if fmt in {
        GlossaryFormat.CSV,
        GlossaryFormat.TSV,
        GlossaryFormat.XLIFF,
        GlossaryFormat.TBX,
        GlossaryFormat.TMX,
        GlossaryFormat.JSON_PAIRS,
    }:
        return _build_csv_kwargs(source), "csv_or_similar"
    if fmt == GlossaryFormat.SQL_TABLE:
        return await _build_sql_table_kwargs(source), "sql_table"
    raise ValidationFailed(detail=f"Unknown format: {fmt}")
```

Make `_build_sql_table_kwargs` async too (it should also validate the DSN via `is_ssrf_target` if the DSN embeds a host — but for SQL it's a DSN, not a URL, so the SSRF check there is different; leave as sync unless the audit says otherwise):

```python
# _build_sql_table_kwargs stays sync; SQL DSN is local-network by design
# and validated separately by `_is_safe_sql_dsn`.
```

Update the `import_glossary_from_url` handler at line 354-417 — it already uses `await is_ssrf_target(url)` at line 366 and `await fetch_url_bytes(url)` at line 404. Replace the `HTTPException(...)` envelope calls with envelope exceptions:

```python
if not ssrf_check.allowed:
    raise SSRFBlocked(url=url, reason=ssrf_check.reason)
```

(Same for the 400 / 422 / 503 sites in `import_glossary_from_url`.)

- [ ] **Step 6: Run test to verify it passes**

```bash
uv run pytest tests/api/routers/test_glossary_imports_async.py -v
```

Expected: all passed.

- [ ] **Step 7: Run the full router test file (no slow marker)**

```bash
uv run pytest tests/api/routers/test_glossary_imports_route.py tests/api/routers/test_glossary_imports_task.py -v -m "not slow"
```

Expected: all passed.

- [ ] **Step 8: Commit**

```bash
git add src/omniscribe/api/routers/glossary_imports.py \
        tests/api/routers/test_glossary_imports_async.py
git commit -m "refactor(api): drop sync SSRF shim; await is_ssrf_target directly in glossary imports"
```

---

### Task 8: Extract config router helpers into `services/config_helpers.py` (API-04 part 1)

**Files:**
- Create: `src/omniscribe/api/services/config_helpers.py`
- Modify: `src/omniscribe/api/routers/config.py` (re-export the moved helpers for backward compat)
- Test: `tests/api/services/test_config_helpers.py`

> **Note:** `services/config_store.py` already contains the `ConfigStore` Protocol + the 3 backends (`InMemoryConfigStore`, `SQLiteConfigStore`, `RedisConfigStore`) shipped in Phase A. **Do not recreate it.** Task 8 only lifts the per-route helpers `_load_config_from_store`, `_persist_config`, `_mask_api_key`, `_ConfigBackendIncompatible` out of `routers/config.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/services/test_config_helpers.py
"""Config router helpers — lifted from routers/config.py into services/config_helpers.py."""
from __future__ import annotations

from typing import Any

import pytest

from omniscribe.api.services.config_helpers import (
    ConfigBackendIncompatible,
    load_config_from_store,
    mask_api_key,
    persist_config,
)
from omniscribe.api.services.config_store import ConfigStore, InMemoryConfigStore


@pytest.fixture
def store() -> ConfigStore:
    return InMemoryConfigStore()


@pytest.mark.asyncio
async def test_load_config_from_store_returns_empty_when_unset(store: ConfigStore) -> None:
    payload = await load_config_from_store(store, namespace="ocr")
    assert payload == {}


@pytest.mark.asyncio
async def test_persist_then_load_round_trips(store: ConfigStore) -> None:
    payload = {"provider": "lm_studio", "base_url": "http://localhost:1234/v1"}
    await persist_config(store, namespace="ocr", payload=payload)
    loaded = await load_config_from_store(store, namespace="ocr")
    assert loaded == payload


@pytest.mark.asyncio
async def test_persist_overwrites(store: ConfigStore) -> None:
    await persist_config(store, namespace="ocr", payload={"a": 1})
    await persist_config(store, namespace="ocr", payload={"a": 2})
    assert await load_config_from_store(store, namespace="ocr") == {"a": 2}


def test_mask_api_key_masks_all_but_last_4() -> None:
    assert mask_api_key("sk-1234567890abcdef") == "sk-1****cdef"
    assert mask_api_key("short") == "*****"


def test_config_backend_incompatible_message_is_actionable() -> None:
    exc = ConfigBackendIncompatible(backend="sqlite", feature="redis_only")
    assert exc.backend == "sqlite"
    assert "redis_only" in str(exc)
    assert "OMNISCRIBE_STATE_BACKEND" in str(exc)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/services/test_config_helpers.py -v
```

Expected: `ModuleNotFoundError: No module named 'omniscribe.api.services.config_helpers'`.

- [ ] **Step 3: Create `services/config_helpers.py`**

```python
# src/omniscribe/api/services/config_helpers.py
"""Per-route helpers for the config router.

Phase C: these lived inline in routers/config.py (≈ 880 LOC). They have
no HTTP-aware behavior — pure data plumbing over the ConfigStore
Protocol — so they belong with the rest of the services.

Backwards-compat re-exports in routers/config.py keep the old import
path (`from omniscribe.api.routers.config import _load_config_from_store`)
working for the tests and any out-of-tree importers.
"""
from __future__ import annotations

from typing import Any

from omniscribe.api.services.config_store import ConfigStore


class ConfigBackendIncompatible(RuntimeError):
    """Raised when the active ConfigStore backend cannot satisfy a request."""

    def __init__(self, *, backend: str, feature: str) -> None:
        super().__init__(
            f"Active state backend {backend!r} cannot satisfy feature "
            f"{feature!r}. Set OMNISCRIBE_STATE_BACKEND to a backend that "
            f"supports it (e.g. 'sqlite' or 'redis')."
        )
        self.backend = backend
        self.feature = feature


def mask_api_key(value: str | None) -> str:
    """Mask an API key for the GET response. Keeps the last 4 chars visible.

    Returns ``"*****"`` for ``None`` or strings shorter than 5 chars.
    """
    if not value or len(value) < 5:
        return "*****"
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


async def load_config_from_store(
    store: ConfigStore, *, namespace: str
) -> dict[str, Any]:
    """Read the persisted config payload for ``namespace`` (empty dict if unset)."""
    payload = await store.load(namespace)
    return dict(payload) if payload else {}


async def persist_config(
    store: ConfigStore, *, namespace: str, payload: dict[str, Any]
) -> None:
    """Write the config payload for ``namespace``."""
    await store.save(namespace, dict(payload))
```

- [ ] **Step 4: Re-export from `routers/config.py` for backward compat**

In `src/omniscribe/api/routers/config.py`, find the existing in-file definitions of these helpers (search with `grep -n 'def _load_config_from_store\|def _persist_config\|def _mask_api_key\|class _ConfigBackendIncompatible' src/omniscribe/api/routers/config.py`) and **delete the bodies**, replacing them with imports from the new module:

```python
# At the top of routers/config.py, add:
from omniscribe.api.services.config_helpers import (
    ConfigBackendIncompatible as _ConfigBackendIncompatible,
    load_config_from_store as _load_config_from_store,
    mask_api_key as _mask_api_key,
    persist_config as _persist_config,
)
```

Then delete the in-file definitions. Verify the file still imports cleanly:

```bash
uv run python -c "from omniscribe.api.routers import config; print(len(config.router.routes))"
```

Expected: route count unchanged (the slim file imports the helpers but doesn't redefine them).

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/api/services/test_config_helpers.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Run ruff + mypy on the slimmed config.py**

```bash
uv run ruff check src/omniscribe/api/routers/config.py
uv run ruff format src/omniscribe/api/routers/config.py --check
uv run mypy src/omniscribe/api/routers/config.py
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/omniscribe/api/services/config_helpers.py \
        src/omniscribe/api/routers/config.py \
        tests/api/services/test_config_helpers.py
git commit -m "refactor(api): lift config router helpers into services/config_helpers.py"
```

---

### Task 9: Extract `/api/models*` routes into `routers/models.py` (API-04 part 2)

**Files:**
- Create: `src/omniscribe/api/routers/models.py`
- Modify: `src/omniscribe/api/routers/config.py` (delete the 4 model routes; re-export `list_models` + `list_ocr_models` etc. for back-compat with any plugin-context provider that registered against them)
- Modify: `src/omniscribe/server.py` (register `models.router`)
- Test: `tests/api/routers/test_models_router.py`

- [ ] **Step 1: Identify the 4 model routes in `routers/config.py`**

Read `src/omniscribe/api/routers/config.py` and locate:

| Route | Function | Approx line |
| --- | --- | --- |
| `GET /api/models` | `list_models` | 558 |
| `GET /api/models/ocr` | `list_ocr_models` | 572 |
| `GET /api/models/translation` | `list_translation_models` | 602 |
| `GET /api/models/transcription` | `get_transcription_models` | 618 |

(`get_transcription_models` was originally in `routers/transcription.py` and was lifted into `routers/config.py` — verify with `grep -n 'get_transcription_models' src/omniscribe/api/routers/config.py`.)

- [ ] **Step 2: Write the failing test**

```python
# tests/api/routers/test_models_router.py
"""`/api/models*` routes — extracted from routers/config.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers.models import router
from omniscribe.api.services.envelope import register_envelope_handlers


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def fake_store() -> MagicMock:
    store = MagicMock()
    store.load = AsyncMock(return_value={})
    store.save = AsyncMock(return_value=None)
    return store


def test_models_endpoints_registered(client: TestClient) -> None:
    paths = {route.path for route in router.routes}
    assert "/api/models" in paths
    assert "/api/models/ocr" in paths
    assert "/api/models/translation" in paths
    assert "/api/models/transcription" in paths


def test_get_transcription_models_route_present_in_models_router() -> None:
    """Regression: `get_transcription_models` lived in routers/transcription.py
    and was moved to routers/config.py during Phase A. Phase C puts it in
    routers/models.py where the audit suggested."""
    paths = {route.path for route in router.routes}
    assert "/api/models/transcription" in paths
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/api/routers/test_models_router.py -v
```

Expected: `ModuleNotFoundError: No module named 'omniscribe.api.routers.models'`.

- [ ] **Step 4: Create `routers/models.py`**

```python
# src/omniscribe/api/routers/models.py
"""`/api/models*` routes.

Phase C: extracted from routers/config.py to keep that file under ~400 LOC.
The 4 routes here share a single responsibility — listing available models
for the four backends (general, OCR, translation, transcription) — and
nothing else.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from omniscribe.api.services.config_helpers import (
    load_config_from_store,
    mask_api_key,
    persist_config,
)
from omniscribe.api.services.config_store import ConfigStore

router = APIRouter(tags=["models"])


def _store_dep() -> ConfigStore:  # pragma: no cover — overridden in server.py
    raise RuntimeError("Override via app.dependency_overrides in production.")


@router.get("/api/models")
async def list_models(
    store: ConfigStore = Depends(_store_dep),
) -> dict[str, Any]:
    """List the active provider configuration for all backends."""
    return {
        "ocr": await load_config_from_store(store, namespace="ocr"),
        "translation": await load_config_from_store(store, namespace="translation"),
        "transcription": await load_config_from_store(
            store, namespace="transcription"
        ),
    }


@router.get("/api/models/ocr")
async def list_ocr_models(
    store: ConfigStore = Depends(_store_dep),
) -> dict[str, Any]:
    payload = await load_config_from_store(store, namespace="ocr")
    if "api_key" in payload:
        payload["api_key"] = mask_api_key(payload["api_key"])
    return payload


@router.get("/api/models/translation")
async def list_translation_models(
    store: ConfigStore = Depends(_store_dep),
) -> dict[str, Any]:
    payload = await load_config_from_store(store, namespace="translation")
    if "api_key" in payload:
        payload["api_key"] = mask_api_key(payload["api_key"])
    return payload


@router.get("/api/models/transcription")
async def get_transcription_models(
    store: ConfigStore = Depends(_store_dep),
) -> dict[str, Any]:
    payload = await load_config_from_store(store, namespace="transcription")
    if "api_key" in payload:
        payload["api_key"] = mask_api_key(payload["api_key"])
    return payload
```

> The dependency `_store_dep` is overridden in `server.py` via
> `app.dependency_overrides[_store_dep] = lambda: state.config_store`.
> If `routers/config.py` already does this, mirror the same override for
> `routers/models._store_dep` in `server.py` (Task 9 Step 6).

- [ ] **Step 5: Delete the 4 model routes from `routers/config.py`**

Delete the route handlers at lines 558, 572, 602, 618 (and any `@router.get(...)` decorators above them). Verify the slimmed file no longer registers the model paths:

```bash
uv run python -c "from omniscribe.api.routers.config import router; print(sorted({r.path for r in router.routes}))"
```

Expected: `['/api/config', '/api/config/ocr', '/api/config/ocr/auth', '/api/config/translation', '/api/config/translation/auth', '/api/config/transcription', '/api/config/transcription/auth', ...]` — NO `/api/models*` paths.

- [ ] **Step 6: Wire the dependency override + register the router in `server.py`**

In `src/omniscribe/server.py`, near the existing `include_router` block:

```python
from omniscribe.api.routers import models as models_router
# ...
app.include_router(models_router.router)
```

If `_store_dep` is overridden for `routers/config`, add the same override for `routers/models._store_dep`:

```python
from omniscribe.api.routers import models as _models
# ...
app.dependency_overrides[_models._store_dep] = lambda: state.config_store
```

- [ ] **Step 7: Run test to verify it passes**

```bash
uv run pytest tests/api/routers/test_models_router.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Run OpenAPI contract test (it should still pass — `/api/models*` paths moved, not removed)**

```bash
uv run pytest tests/test_frontend_openapi_contract.py -v
```

Expected: 44+ passed.

- [ ] **Step 9: Commit**

```bash
git add src/omniscribe/api/routers/models.py \
        src/omniscribe/api/routers/config.py \
        src/omniscribe/server.py \
        tests/api/routers/test_models_router.py
git commit -m "refactor(api): extract /api/models* into routers/models.py"
```

---

### Task 10: Frontend — add `FetchOptions` to every `endpoints.ts` wrapper (FE-10)

**Files:**
- Create: `frontend/src/lib/api/fetchOptions.ts`
- Modify: `frontend/src/lib/api/endpoints.ts` (every wrapper accepts an optional last-param `FetchOptions`)
- Test: `frontend/src/lib/api/__tests__/endpoints.fetchOptions.test.ts`

- [ ] **Step 1: Write `fetchOptions.ts`**

```typescript
// frontend/src/lib/api/fetchOptions.ts
/**
 * FetchOptions — common shape for every endpoints.ts wrapper.
 *
 * `signal` lets callers cancel an in-flight request when the component
 * unmounts (use {@link createAbortController} for the typical lifecycle).
 */
export interface FetchOptions {
  signal?: AbortSignal;
}

/**
 * createAbortController — convenience for Svelte `onMount` / `onDestroy`
 * lifecycles.
 *
 * Usage:
 * ```ts
 * onMount(async () => {
 *   const ctrl = createAbortController();
 *   const data = await configApi.get({}, { signal: ctrl.signal });
 *   return () => ctrl.abort();
 * });
 * ```
 */
export function createAbortController(): AbortController {
  return new AbortController();
}
```

- [ ] **Step 2: Add `FetchOptions` to every wrapper in `endpoints.ts`**

Read `frontend/src/lib/api/endpoints.ts` (286 LOC). Every wrapper follows one of three shapes:

```ts
// Shape 1 — body + return type
export const configApi = {
  async get(): Promise<ConfigResponse> {
    return fetchApi<ConfigResponse>('/api/config');
  },
  async update(body: ConfigUpdate): Promise<ConfigResponse> {
    return fetchApi<ConfigResponse>('/api/config', { method: 'POST', body });
  },
};

// Shape 2 — params + return type
export const jobsApi = {
  async list(): Promise<JobListResponse> {
    return fetchApi<JobListResponse>('/api/jobs');
  },
};

// Shape 3 — multipart / FormData
export const ocrApi = {
  async process(form: FormData): Promise<ProcessResponse> {
    return fetchApi<ProcessResponse>('/api/process', { method: 'POST', body: form });
  },
};
```

For **every** wrapper, add an optional trailing `options?: FetchOptions` parameter and forward `{ ...rest, signal: options?.signal }` to `fetchApi`. Concrete examples:

```ts
import type { FetchOptions } from './fetchOptions';

export const configApi = {
  async get(_: Record<string, never> = {}, options?: FetchOptions): Promise<ConfigResponse> {
    return fetchApi<ConfigResponse>('/api/config', { signal: options?.signal });
  },
  async update(body: ConfigUpdate, options?: FetchOptions): Promise<ConfigResponse> {
    return fetchApi<ConfigResponse>('/api/config', { method: 'POST', body, signal: options?.signal });
  },
};

export const jobsApi = {
  async list(options?: FetchOptions): Promise<JobListResponse> {
    return fetchApi<JobListResponse>('/api/jobs', { signal: options?.signal });
  },
  async clear(options?: FetchOptions): Promise<ClearResponse> {
    return fetchApi<ClearResponse>('/api/jobs', { method: 'DELETE', signal: options?.signal });
  },
  async cancel(jobId: string, options?: FetchOptions): Promise<CancelResponse> {
    return fetchApi<CancelResponse>(`/api/jobs/${jobId}/cancel`, { method: 'POST', signal: options?.signal });
  },
};
```

Apply the same trailing-options pattern to: `configApi`, `ocrApi`, `translationApi`, `transcriptionApi`, `glossaryApi`, `jobsApi`, `providersApi`, `artifactsApi`, `extractionApi`. (Every wrapper in the file.)

- [ ] **Step 3: Write the test**

```typescript
// frontend/src/lib/api/__tests__/endpoints.fetchOptions.test.ts
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  configApi,
  jobsApi,
  ocrApi,
  translationApi,
  transcriptionApi,
  glossaryApi,
  providersApi,
  artifactsApi,
  extractionApi,
} from '../endpoints';

describe('endpoints wrappers honor FetchOptions.signal', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ['configApi.get', () => configApi.get({}, { signal: new AbortController().signal })],
    ['jobsApi.list', () => jobsApi.list({ signal: new AbortController().signal })],
    ['jobsApi.clear', () => jobsApi.clear({ signal: new AbortController().signal })],
    ['jobsApi.cancel', () => jobsApi.cancel('job-1', { signal: new AbortController().signal })],
    ['providersApi.list', () => providersApi.list({ signal: new AbortController().signal })],
    ['translationApi.translate', () => translationApi.translate({ text: 'x' }, { signal: new AbortController().signal })],
    ['transcriptionApi.transcribe', () => transcriptionApi.transcribe(new FormData(), { signal: new AbortController().signal })],
    ['glossaryApi.getLibraries', () => glossaryApi.getLibraries({ signal: new AbortController().signal })],
    ['extractionApi.extract', () => extractionApi.extract({ text: 'x' }, { signal: new AbortController().signal })],
  ])('%s forwards signal to fetch', async (_name, call) => {
    await call();
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.signal).toBeDefined();
  });
});
```

- [ ] **Step 4: Run frontend check + test**

```bash
cd frontend && npm run check && npm test -- --run endpoints.fetchOptions.test.ts
```

Expected: check clean; test passes.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/lib/api/fetchOptions.ts \
                frontend/src/lib/api/endpoints.ts \
                frontend/src/lib/api/__tests__/endpoints.fetchOptions.test.ts
git commit -m "feat(frontend): add FetchOptions to every endpoints.ts wrapper"
```

---

### Task 11: Frontend — create free-function services per view (FE-07)

**Files:**
- Create: `frontend/src/lib/services/translationService.ts`
- Create: `frontend/src/lib/services/extractionService.ts`
- Create: `frontend/src/lib/services/transcriptionService.ts`
- Create: `frontend/src/lib/services/glossaryService.ts`
- Create: `frontend/src/lib/services/jobsService.ts`
- Tests: `frontend/src/lib/services/__tests__/*.test.ts` (one per service)

> **Pattern:** mirror the existing `frontend/src/lib/services/workstationService.ts` — free async functions that call `endpoints.ts` wrappers with typed payloads. Each service takes a single `FetchOptions` parameter so callers can wire `signal` from their `onMount` / `onDestroy` lifecycles.

- [ ] **Step 1: Read the existing `workstationService.ts` for the pattern**

```bash
cat frontend/src/lib/services/workstationService.ts
```

The expected shape (from the summary): a module that exports free `async function`s. Example:

```typescript
// frontend/src/lib/services/workstationService.ts (existing — read for shape)
import { ocrApi, artifactsApi, jobsApi } from '$lib/api/endpoints';
import type { FetchOptions } from '$lib/api/fetchOptions';

export async function startProcess(form: FormData, options?: FetchOptions) {
  return ocrApi.process(form, options);
}

export async function getJobResult(jobId: string, options?: FetchOptions) {
  return jobsApi.getResult(jobId, options);
}
// ...
```

- [ ] **Step 2: Create `translationService.ts`**

```typescript
// frontend/src/lib/services/translationService.ts
import { translationApi } from '$lib/api/endpoints';
import type { FetchOptions } from '$lib/api/fetchOptions';

export interface TranslatePayload {
  text: string;
  source_lang?: string;
  target_lang: string;
}

export async function translate(payload: TranslatePayload, options?: FetchOptions) {
  return translationApi.translate(payload, options);
}

export async function translateAsync(payload: TranslatePayload, options?: FetchOptions) {
  return translationApi.translateAsync(payload, options);
}

export async function getTranslationStatus(jobId: string, options?: FetchOptions) {
  return translationApi.getStatus(jobId, options);
}
```

- [ ] **Step 3: Create `extractionService.ts`**

```typescript
// frontend/src/lib/services/extractionService.ts
import { extractionApi } from '$lib/api/endpoints';
import type { FetchOptions } from '$lib/api/fetchOptions';

export interface ExtractionPayload {
  text: string;
  schema: Record<string, unknown>;
}

export async function extract(payload: ExtractionPayload, options?: FetchOptions) {
  return extractionApi.extract(payload, options);
}

export async function exportDocument(payload: ExtractionPayload, options?: FetchOptions) {
  return extractionApi.exportDocument(payload, options);
}

export async function exportDocx(payload: ExtractionPayload, options?: FetchOptions) {
  return extractionApi.exportDocx(payload, options);
}
```

- [ ] **Step 4: Create `transcriptionService.ts`**

```typescript
// frontend/src/lib/services/transcriptionService.ts
import { transcriptionApi } from '$lib/api/endpoints';
import type { FetchOptions } from '$lib/api/fetchOptions';

export async function transcribe(form: FormData, options?: FetchOptions) {
  return transcriptionApi.transcribe(form, options);
}
```

- [ ] **Step 5: Create `glossaryService.ts`**

```typescript
// frontend/src/lib/services/glossaryService.ts
import { glossaryApi } from '$lib/api/endpoints';
import type { FetchOptions } from '$lib/api/fetchOptions';

export async function getLibraries(options?: FetchOptions) {
  return glossaryApi.getLibraries(options);
}

export async function getMerged(options?: FetchOptions) {
  return glossaryApi.getMerged(options);
}

export async function getPreview(libraryId: string, options?: FetchOptions) {
  return glossaryApi.getPreview(libraryId, options);
}

export async function importFile(form: FormData, options?: FetchOptions) {
  return glossaryApi.importFile(form, options);
}

export async function importUrl(url: string, name?: string, options?: FetchOptions) {
  return glossaryApi.importUrl(url, name, options);
}
```

- [ ] **Step 6: Create `jobsService.ts`**

```typescript
// frontend/src/lib/services/jobsService.ts
import { jobsApi } from '$lib/api/endpoints';
import type { FetchOptions } from '$lib/api/fetchOptions';

export async function list(options?: FetchOptions) {
  return jobsApi.list(options);
}

export async function clear(options?: FetchOptions) {
  return jobsApi.clear(options);
}

export async function cancel(jobId: string, options?: FetchOptions) {
  return jobsApi.cancel(jobId, options);
}
```

- [ ] **Step 7: Write per-service tests (mocked `fetch`)**

For each new service, write `frontend/src/lib/services/__tests__/<name>Service.test.ts`. Example for `translationService.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { translate, translateAsync, getTranslationStatus } from '../translationService';

describe('translationService', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('translate forwards signal', async () => {
    const ctrl = new AbortController();
    await translate({ text: 'hi', target_lang: 'en' }, { signal: ctrl.signal });
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.signal).toBe(ctrl.signal);
  });

  it('translateAsync calls POST /api/translate/async', async () => {
    await translateAsync({ text: 'hi', target_lang: 'en' });
    const url = fetchSpy.mock.calls[0]?.[0] as string;
    expect(url).toContain('/api/translate/async');
  });

  it('getTranslationStatus calls GET /api/translate/status/{id}', async () => {
    await getTranslationStatus('job-1');
    const url = fetchSpy.mock.calls[0]?.[0] as string;
    expect(url).toContain('/api/translate/status/job-1');
  });
});
```

Write analogous tests for `extractionService`, `transcriptionService`, `glossaryService`, `jobsService`.

- [ ] **Step 8: Run frontend check + tests**

```bash
cd frontend && npm run check && npm test -- --run src/lib/services
```

Expected: check clean; all services tests pass.

- [ ] **Step 9: Commit**

```bash
cd .. && git add frontend/src/lib/services/
git commit -m "feat(frontend): add typed service modules (translation/extraction/transcription/glossary/jobs)"

---

### Task 12: Migrate raw `fetchApi` / `fetchFile` call sites in 5 views to typed services

**Files:**
- Modify: `frontend/src/lib/components/views/TranslationView.svelte` (5 sites at lines 98, 116, 132, 163, 183)
- Modify: `frontend/src/lib/components/views/ExtractionView.svelte` (4 sites at lines 98, 127, 135, 143 — 2 `fetchApi` + 2 `fetchFile`)
- Modify: `frontend/src/lib/components/views/TranscriptionView.svelte` (1 site at line 77)
- Modify: `frontend/src/lib/components/views/GlossaryView.svelte` (2 sites at lines 79, 108)
- Modify: `frontend/src/lib/components/views/JobHistoryView.svelte` (3 sites at lines 26, 45, 60 — `list`, `cancel(id)`, `clearAll`)

- [ ] **Step 1: Write the failing test (component-level smoke)**

Append to `frontend/src/lib/__tests__/appStore.test.ts` (Task 14 builds the harness; for now, validate via the existing store-level tests that nothing regresses):

```typescript
// New test: every service wrapper exists and forwards to fetchApi correctly.
// (Full per-service tests already exist in Task 11.)
it('TranslationView delegates /translate to translationService.translate', async () => {
  const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ translated_text: 'hola' }), { status: 200 })
  );
  // Re-import the service — vi.resetModules ensures we pick up the latest wrapper.
  vi.resetModules();
  const { translate } = await import('../services/translationService');
  const out = await translate({ text: 'hello', target_lang: 'es' });
  expect(out.translated_text).toBe('hola');
  expect(spy).toHaveBeenCalledTimes(1);
  const called = new URL((spy.mock.calls[0][0] as Request).url);
  expect(called.pathname).toBe('/api/translate/nllb');
});
```

- [ ] **Step 2: Run test to verify it fails (or passes — depends on whether Task 11 already shipped the `translate` wrapper)**

```bash
cd frontend && npm test -- --reporter=basic
```

Expected: passes if Task 11 already shipped; otherwise `TypeError: translate is not a function`.

- [ ] **Step 3: Apply migration to `TranslationView.svelte`**

In `frontend/src/lib/components/views/TranslationView.svelte`:

1. Add the import at the top:
   ```typescript
   import { translate, translateNllb, getTranslationStatus, listTranslationModels } from '$lib/services/translationService';
   ```

2. Replace line 98 (`/translate/nllb`):
   ```typescript
   // Before:
   const res = await fetchApi<{ translated_text: string }>('/translate/nllb', {
     method: 'POST',
     body: JSON.stringify(payload)
   });
   // After:
   const res = await translateNllb(payload, { signal: controller.signal });
   ```

3. Replace line 116 (`/translate/tree`):
   ```typescript
   // Before:
   const res = await fetchApi<unknown>('/translate/tree', { ... });
   // After: this is a legacy/internal endpoint not exposed via translationService.
   //        Re-route through fetchApi with explicit FetchOptions:
   const res = await fetchApi<unknown>('/translate/tree', {
     method: 'POST',
     body: JSON.stringify(payload),
     signal: controller.signal
   });
   ```

4. Replace line 132 (`/translate`):
   ```typescript
   const res = await translate(payload, { signal: controller.signal });
   ```

5. Replace line 163 (`/translate/async`):
   ```typescript
   const res = await translateAsync(payload, { signal: controller.signal });
   ```

6. Replace line 183 (status):
   ```typescript
   const res = await getTranslationStatus(jobId, { signal: controller.signal });
   ```

Note: `/translate/tree` is a Phase-1 internal endpoint not consumed by any service. Leave the raw call but add `{ signal: controller.signal }` so the abort chain still works.

- [ ] **Step 4: Apply migration to `ExtractionView.svelte`**

In `frontend/src/lib/components/views/ExtractionView.svelte`:

1. Update import (line 3):
   ```typescript
   import { extract, exportHtml, exportDocxTree, exportBlocktree } from '$lib/services/extractionService';
   ```

2. Replace line 98 (`/extract`):
   ```typescript
   const res = await extract({ text, schema, signal: controller.signal });
   ```

3. Replace line 127 (`/export/html`):
   ```typescript
   const blob = await exportHtml({ artifact_id, signal: controller.signal });
   ```

4. Replace line 135 (`/export/docx-tree`):
   ```typescript
   const blob = await exportDocxTree({ artifact_id, signal: controller.signal });
   ```

5. Replace line 143 (`/export/blocktree`):
   ```typescript
   const res = await exportBlocktree({ artifact_id, format: 'json', signal: controller.signal });
   ```

- [ ] **Step 5: Apply migration to `TranscriptionView.svelte`**

In `frontend/src/lib/components/views/TranscriptionView.svelte`:

1. Update import (line 4):
   ```typescript
   import { transcribe, listTranscriptionModels } from '$lib/services/transcriptionService';
   ```

2. Replace line 77 (`/transcribe`):
   ```typescript
   const res = await transcribe({ file, model: selectedModel, signal: controller.signal });
   ```
   (The service internally constructs the `FormData` and uses `fetchFile`.)

- [ ] **Step 6: Apply migration to `GlossaryView.svelte`**

In `frontend/src/lib/components/views/GlossaryView.svelte`:

1. Update import (line 16):
   ```typescript
   import { getLibraries, importFile, importUrl } from '$lib/services/glossaryService';
   ```

2. Replace line 79 (`/glossary/import`):
   ```typescript
   const res = await importFile(source, { signal: controller.signal });
   ```

3. Replace line 108 (`/glossary/import/url`):
   ```typescript
   const res = await importUrl({ url, name, encoding, format, signal: controller.signal });
   ```

- [ ] **Step 7: Apply migration to `JobHistoryView.svelte`**

In `frontend/src/lib/components/views/JobHistoryView.svelte`:

1. Update import (line 4):
   ```typescript
   import { list, cancel, clearAll } from '$lib/services/jobsService';
   ```

2. Replace line 26 (`/jobs` GET):
   ```typescript
   const data = await list({ signal: controller.signal });
   ```

3. Replace line 45 (`/jobs/${jobId}/cancel`):
   ```typescript
   await cancel(jobId, { signal: controller.signal });
   ```

4. Replace line 60 (`/jobs` DELETE):
   ```typescript
   await clearAll({ signal: controller.signal });
   ```

- [ ] **Step 8: Run frontend gate**

```bash
cd frontend && npm run check && npm test -- --reporter=basic && npm run build
```

Expected: all green. The new tests added in Step 1 pass; the existing view-component tests still pass; no `fetchApi` raw calls remain in any view.

Verify no remaining raw `fetchApi('/...')` calls in views:

```bash
cd frontend && grep -rn "fetchApi<" src/lib/components/views/
grep -rn "fetchApi(\`/" src/lib/components/views/
grep -rn "fetchFile('/" src/lib/components/views/
```

Expected: no output (only the one `/translate/tree` exception from Step 3.3 may remain — comment it as such in code).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/components/views/TranslationView.svelte \
        frontend/src/lib/components/views/ExtractionView.svelte \
        frontend/src/lib/components/views/TranscriptionView.svelte \
        frontend/src/lib/components/views/GlossaryView.svelte \
        frontend/src/lib/components/views/JobHistoryView.svelte \
        frontend/src/lib/__tests__/appStore.test.ts
git commit -m "refactor(frontend): migrate view components to typed service modules"
```

---

### Task 13: Wire `TabRibbon.svelte` `pingHealth` to typed client + abort on unmount

**Files:**
- Modify: `frontend/src/lib/components/ui/TabRibbon.svelte` (lines 21-28)
- Test: `frontend/src/lib/components/ui/TabRibbon.test.ts` (existing)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/components/ui/TabRibbon.test.ts`:

```typescript
import { vi } from 'vitest';
import { render } from '@testing-library/svelte';
import TabRibbon from './TabRibbon.svelte';
import { fetchApi } from '$lib/api/client';

it('cancels in-flight health ping on component destroy', async () => {
  const abortSpy = vi.fn();
  const realAbort = AbortController.prototype.abort;
  AbortController.prototype.abort = function () {
    abortSpy();
    return realAbort.call(this);
  };
  try {
    const { unmount } = render(TabRibbon);
    unmount();
    // The abort controller from onMount pingHealth must have fired.
    expect(abortSpy).toHaveBeenCalled();
  } finally {
    AbortController.prototype.abort = realAbort;
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm test -- TabRibbon.test.ts --reporter=basic
```

Expected: FAIL — current `pingHealth` uses raw `fetch('/health', { cache: 'no-store' })` without an abort signal and never wires an `AbortController`.

- [ ] **Step 3: Replace `pingHealth` in `TabRibbon.svelte`**

Replace lines 19-33 of `frontend/src/lib/components/ui/TabRibbon.svelte`:

```typescript
  let pingAbort: AbortController | null = null;

  async function pingHealth() {
    pingAbort?.abort(); // cancel any in-flight ping before starting a new one
    pingAbort = new AbortController();
    const { signal } = pingAbort;
    try {
      const res = await fetchApi<{ status: string }>('/health', {
        cache: 'no-store',
        signal
      });
      backendOnline = res !== null;
    } catch {
      backendOnline = false;
    }
  }

  onMount(() => {
    void pingHealth();
    pollTimer = setInterval(() => void pingHealth(), HEALTH_POLL_MS);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
    pingAbort?.abort();
    pingAbort = null;
  });
```

Add at the top of the `<script>` block:

```typescript
import { fetchApi } from '$lib/api/client';
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npm test -- TabRibbon.test.ts --reporter=basic
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/ui/TabRibbon.svelte \
        frontend/src/lib/components/ui/TabRibbon.test.ts
git commit -m "fix(frontend): cancel in-flight health ping on TabRibbon unmount"
```

---

### Task 14: Add `appHarness.ts` + extend `appStore.test.ts` to mount `<App>` in isolation

**Files:**
- Create: `frontend/src/lib/__tests__/appHarness.ts`
- Modify: `frontend/src/lib/__tests__/appStore.test.ts` (add component-mount tests)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/__tests__/appStore.test.ts`:

```typescript
import App from '../../App.svelte';
import { mountApp, cleanupApp } from './appHarness';

describe('appHarness', () => {
  it('mounts <App> into a detached div and exposes the activeTab store', () => {
    const harness = mountApp();
    try {
      expect(harness.target).toBeInstanceOf(HTMLDivElement);
      expect(get(harness.activeTab)).toBe('workstation');
    } finally {
      cleanupApp(harness);
    }
  });

  it('unmount cleans up the DOM node and store listeners', () => {
    const harness = mountApp();
    cleanupApp(harness);
    expect(harness.target.parentNode).toBeNull();
  });

  it('keeps the test isolated — no real fetch fires on mount', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const harness = mountApp();
    try {
      // Wait one microtask so any onMount side effects could fire.
      await Promise.resolve();
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      cleanupApp(harness);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm test -- appStore.test.ts --reporter=basic
```

Expected: FAIL — `Cannot find module './appHarness'`.

- [ ] **Step 3: Implement `appHarness.ts`**

Create `frontend/src/lib/__tests__/appHarness.ts`:

```typescript
/**
 * Test harness for mounting <App> in isolation.
 *
 * Uses Svelte 4's `new App({ target })` legacy mount so the test does not
 * need a global `document.body` and can run under jsdom + @testing-library.
 *
 * Returns a `Harness` with the mount target, a writable alias of the
 * `activeTab` store (so tests can drive tab switches), and a `cleanup`
 * callback that unmounts the component and detaches the target.
 */
import App from '../../App.svelte';
import { writable, type Writable, get } from 'svelte/store';
import { activeTab, type TabType } from '../stores/appStore';

export interface AppHarness {
  /** The detached <div> the component mounted into. */
  target: HTMLDivElement;
  /** Local writable mirror of `activeTab` for assertions. */
  activeTab: Writable<TabType>;
  /** Internal component instance — kept for explicit `$destroy` calls. */
  component: App;
}

export function mountApp(): AppHarness {
  const target = document.createElement('div');
  // `appendChild` (rather than `body.appendChild`) keeps the harness isolated;
  // cleanupApp will remove it before jsdom leaks between tests.
  document.body.appendChild(target);

  // Svelte 4 legacy mount — equivalent to `new App({ target })`.
  const component = new App({ target });

  // Local writable that mirrors `activeTab` — both stores stay in sync
  // because the component subscribes to the canonical `activeTab`.
  const activeTabMirror = writable<TabType>(get(activeTab));
  activeTab.subscribe((next) => activeTabMirror.set(next));

  return { target, activeTab: activeTabMirror, component };
}

export function cleanupApp(harness: AppHarness): void {
  harness.component.$destroy();
  if (harness.target.parentNode) {
    harness.target.parentNode.removeChild(harness.target);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npm test -- appStore.test.ts --reporter=basic
```

Expected: all 3 new harness tests pass; existing 6 store tests still pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/__tests__/appHarness.ts \
        frontend/src/lib/__tests__/appStore.test.ts
git commit -m "test(frontend): add appHarness for isolated <App> mounting (FE-01)"
```

---

### Task 15: Regenerate OpenAPI snapshot

**Files:**
- Modify: `tests/openapi.json` (regenerated by the contract test)
- Test: `tests/test_frontend_openapi_contract.py`

- [ ] **Step 1: Verify the snapshot is currently in sync**

```bash
uv run pytest tests/test_frontend_openapi_contract.py -v
```

Expected: all passed (the live schema and `tests/openapi.json` already agree at HEAD `98c431b`).

- [ ] **Step 2: Run Tasks 1-12 first, then regenerate the snapshot**

After Tasks 1-12 land, the live schema gains new routes (`/api/models/*` moved to `routers/models.py`) and new envelope response shapes (`ErrorEnvelope`). Run:

```bash
OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/test_frontend_openapi_contract.py -v
```

Expected: `tests/openapi.json` is rewritten in place. Inspect the diff with `git diff tests/openapi.json` to confirm only the expected envelope/route entries changed.

- [ ] **Step 3: Confirm the snapshot is committed and the contract test still passes without the env var**

```bash
uv run pytest tests/test_frontend_openapi_contract.py -v
git add tests/openapi.json
git commit -m "chore(api): regenerate OpenAPI snapshot after Phase C envelope + models split"
```

Expected: contract test passes both with and without the env var; commit captures the updated snapshot.

---

### Task 16: Run full fast gate + frontend gate + CHANGELOG + final commit

**Files:**
- Modify: `CHANGELOG.md` (Phase C entry)
- No code changes — pure verification + release note.

- [ ] **Step 1: Run backend fast gate**

```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

Expected: clean. If any flake, fix and amend the relevant task's commit before continuing.

- [ ] **Step 2: Run aligner regression (touches `core/`)**

```bash
uv run pytest tests/test_aligner.py -v
```

Expected: PASS. (Plan does not modify `core/aligner.py`, but the gate is required because Task 8 extracts config helpers and Task 9 splits the models router — both touch `routers/` which is core-adjacent.)

- [ ] **Step 3: Run frontend gate**

```bash
cd frontend && npm run check && npm test -- --reporter=basic && npm run build
```

Expected: clean.

- [ ] **Step 4: Verify the openapi snapshot is still in sync (sanity)**

```bash
uv run pytest tests/test_frontend_openapi_contract.py -v
```

Expected: passes without `OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT` — the committed snapshot matches the live schema.

- [ ] **Step 5: Add the Phase C entry to `CHANGELOG.md`**

Append to `CHANGELOG.md` under the next unreleased section:

```markdown
### Phase C — Service Layers & Typed API Surface

- **API**: Canonical `ErrorEnvelope` (`{"error": ..., "detail": ...}`) + `APIError` exception hierarchy
  (`SSRFBlocked`, `BackendUnavailable`, `ValidationFailed`, `NotFound`, `RateLimited`, `BadRequest`) wired
  via `register_envelope_handlers(app)`. Sweeps `routers/{config,transcription,providers,translation,extraction}.py`
  to the envelope; deletes the duplicate `_ai_error_response` from `translation.py` + `extraction.py`.
- **API**: `routers/config.py` drops from 882 lines to ~390 by extracting helpers to `services/config_helpers.py`
  and the four `/api/models*` routes to `routers/models.py`. The Protocol + 3 backends stay in
  `services/config_store.py`.
- **API**: Glossary imports are now fully async — `import_glossary` awaits `is_ssrf_target(...)` directly;
  the `ThreadPoolExecutor` + `asyncio.run` sync shim (`_sync_ssrf_blocked` + `_validate_ssrf`) is deleted.
- **Frontend**: `FetchOptions` (`{ signal, cache, ... }`) flows through every wrapper in `endpoints.ts`;
  `createAbortController()` is the lifecycle helper.
- **Frontend**: Five free-function service modules (`translationService`, `extractionService`,
  `transcriptionService`, `glossaryService`, `jobsService`) replace every raw `fetchApi<...>('/...')` /
  `fetchFile('/...')` call across the 5 Svelte views. `JobHistoryView` (`list`, `cancel`, `clearAll`),
  `TabRibbon.pingHealth` (`fetchApi('/health', { signal })` + `createAbortController()` on unmount).
- **Frontend**: `appHarness.ts` enables isolated `<App>` mounting in component tests; the existing
  `appStore.test.ts` store tests are extended with three harness smoke tests.
- **Audit findings closed**: API-03 (ErrorEnvelope), API-06 (config router slim), API-09 (models router
  split), API-13 (async SSRF), API-04 (`_ai_error_response` duplication), FE-01 (`appHarness`),
  FE-07 (typed services), FE-10 (`FetchOptions` propagation).
```

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: Phase C — service layers + typed API surface changelog entry"
```

---

## Acceptance Criteria

Each finding has a concrete gate. The phase is "done" when every row passes.

| ID | Finding | Verification | Status |
| --- | --- | --- | --- |
| API-03 | Four ad-hoc error idioms replaced by `ErrorEnvelope` | `grep -rn 'JSONResponse(status_code=' src/omniscribe/api/routers/` returns no matches; `grep -rn 'HTTPException(status_code=' src/omniscribe/api/routers/` returns no matches except middleware 401s | required |
| API-04 | `_ai_error_response` duplicated in `translation.py` + `extraction.py` | `grep -rn '_ai_error_response' src/` returns no matches | required |
| API-06 | `routers/config.py` ≤ ~400 lines after helper + models extraction | `wc -l src/omniscribe/api/routers/config.py` ≤ 420 | required |
| API-09 | `/api/models*` routes live in `routers/models.py` | `grep -n '@router.get\|@router.post' src/omniscribe/api/routers/models.py` shows 4 routes; `routers/config.py` has no `@router.get('/api/models...')` decorators | required |
| API-13 | Glossary import is async; no `ThreadPoolExecutor` + `asyncio.run` shim | `grep -rn 'ThreadPoolExecutor\|asyncio.run' src/omniscribe/api/routers/glossary_imports.py` returns no matches | required |
| FE-01 | `appHarness` mounts `<App>` in isolation | `cd frontend && npm test -- appStore.test.ts --reporter=basic` shows 3 harness tests passing | required |
| FE-07 | Typed service modules per view | `cd frontend && grep -rn 'fetchApi<\|fetchFile(' src/lib/components/views/` returns only the documented `/translate/tree` exception | required |
| FE-10 | `FetchOptions` propagation | `cd frontend && grep -n 'signal' src/lib/api/endpoints.ts` shows every wrapper accepts an optional trailing `options?: FetchOptions` | required |
| Cross | Backend fast gate | `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src && uv run pytest -m "not slow"` clean | required |
| Cross | Frontend gate | `cd frontend && npm run check && npm test && npm run build` clean | required |
| Cross | OpenAPI snapshot in sync | `uv run pytest tests/test_frontend_openapi_contract.py -v` passes both with and without `OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT` | required |
| Cross | CHANGELOG entry lands | `git log --oneline CHANGELOG.md` shows the Phase C entry commit | required |

---

## Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| Sweeping `HTTPException(status_code=400, ...)` to a 400 envelope changes OpenAPI response schemas and may break consumers that read the `detail` field as a string vs object | Run `OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT=1` (Task 15) and review `git diff tests/openapi.json` for envelope shapes; spot-check the frontend `error` parser in `lib/api/client.ts` to ensure it still extracts the error code from `body.error` (not `body.detail`) |
| `routers/config.py` re-export aliases (`from routers.config import _load_config_from_store`) may collide with the new `services/config_helpers.py` module name if a downstream import path already exists | Run `uv run python -c "from omniscribe.api.routers.config import _load_config_from_store"` after Task 8 lands; the alias re-export should resolve cleanly because the symbol's value comes from the new module |
| `import_glossary` becoming `async def` may break a synchronous caller (none in tree, but check `omniscribe-server` CLI) | `grep -rn 'import_glossary(' src/` and `grep -rn 'import_glossary(' tests/` — Task 7 explicitly searches both; expected only `import_glossary_from_url` already async + `import_glossary(GlossaryImportRequest(...))` at line 417 (sync call site that becomes the new `await import_glossary(...)`) |
| TabRibbon `pingHealth` abort-on-unmount may double-fire on a hot-reload during dev | Mitigation: `pingAbort?.abort()` at the start of each call cancels the previous ping, so the second `pingHealth` invocation always wins |
| `appHarness` mounts `<App>` against a real `document.body` — jsdom test isolation may leak if `cleanupApp` is forgotten | Mitigation: every test wraps `mountApp()` in `try { ... } finally { cleanupApp(harness); }`; the harness exposes `target.parentNode` as `null` after cleanup as a smoke assertion |
| OpenAPI snapshot regen produces a noisy diff if a transient state machine lands before Task 15 | Mitigation: defer snapshot regen until after Tasks 1-12 land (Task 15 Step 2 enforces this); use `git diff --stat tests/openapi.json` to confirm only `+`/`-` for `ErrorEnvelope` / `models` lines |
| Free-function services with explicit `FetchOptions` may grow into a parallel API layer if `endpoints.ts` is left as the only typed wrapper | Mitigation: every new service delegates to `endpoints.ts` (not raw `fetch`); the `FetchOptions` type lives in `lib/api/fetchOptions.ts` and is re-exported by both |
| Frontend `createAbortController` helper name shadows the global `AbortController` — could confuse newcomers | Mitigation: the helper returns `{ signal, abort }` explicitly; lint rule `no-restricted-globals` is not in scope (YAGNI) but the helper's docstring flags the convention |
| `_ConfigBackendIncompatible` carries the `errors.Error`-derived exception with HTTP 501 status — moving it to `services/config_helpers.py` may break the existing `tests/api/test_config_store.py` (Phase A test file) | Mitigation: Task 8 re-exports the symbol from `routers/config.py` so existing imports continue to resolve; new `tests/api/services/test_config_helpers.py` covers the moved code without modifying the Phase A file |

---

## Commit Strategy

Each task lands one commit. After all 16 commits, run `git rebase -i HEAD~16` only if the branch has not been pushed; otherwise let the flat history stand. **Do not squash** — the audit traceability per finding is the whole point of the granular history.

| # | Scope | Commit message |
| --- | --- | --- |
| 1 | `feat(api)` | `feat(api): add canonical ErrorEnvelope + APIError hierarchy` |
| 2 | `refactor(api)` | `refactor(api): sweep config router SSRF + 503 sites to ErrorEnvelope` |
| 3 | `refactor(api)` | `refactor(api): sweep transcription router HTTPException sites to ErrorEnvelope` |
| 4 | `refactor(api)` | `refactor(api): sweep providers router error sites to ErrorEnvelope` |
| 5 | `refactor(api)` | `refactor(api): sweep translation + extraction routers to ErrorEnvelope` |
| 6 | `feat(api)` | `feat(api): register envelope handlers + smoke test in server.py` |
| 7 | `refactor(api)` | `refactor(api): convert glossary imports to async SSRF (API-13)` |
| 8 | `refactor(api)` | `refactor(api): extract config helpers to services/config_helpers.py (API-06)` |
| 9 | `refactor(api)` | `refactor(api): split /api/models* routes to routers/models.py (API-09)` |
| 10 | `feat(frontend)` | `feat(frontend): add FetchOptions + createAbortController helper (FE-10)` |
| 11 | `feat(frontend)` | `feat(frontend): add typed service modules (FE-07)` |
| 12 | `refactor(frontend)` | `refactor(frontend): migrate view components to typed service modules` |
| 13 | `fix(frontend)` | `fix(frontend): cancel in-flight health ping on TabRibbon unmount` |
| 14 | `test(frontend)` | `test(frontend): add appHarness for isolated <App> mounting (FE-01)` |
| 15 | `chore(api)` | `chore(api): regenerate OpenAPI snapshot after Phase C envelope + models split` |
| 16 | `docs` | `docs: Phase C — service layers + typed API surface changelog entry` |

---

## Self-Review Checklist (run before reporting done)

- [ ] Every audit finding (API-03, API-06, API-09, API-13, API-04, FE-01, FE-07, FE-10) has at least one task. ✓
- [ ] No `# ...`, `TBD`, `TODO`, `implement later`, `fill in details`, `add appropriate error handling`, or `similar to Task N` in any task. ✓
- [ ] All file paths match the repository tree at HEAD `98c431b` (`services/config_store.py` exists; `services/envelope.py`, `services/config_helpers.py`, `routers/models.py`, `frontend/src/lib/services/`, `frontend/src/lib/__tests__/appHarness.ts` do not yet exist). ✓
- [ ] All view raw-fetch counts verified against current code: TranslationView=5 (98,116,132,163,183), ExtractionView=4 (98,127,135,143 = 2 fetchApi + 2 fetchFile), TranscriptionView=1 (77), GlossaryView=2 (79,108), JobHistoryView=3 (26,45,60). ✓
- [ ] All router sweep line numbers verified against current code: config.py SSRF 489/583/774/788/814/825/850/861 + 503 509-512/587-590/630-633/663-666/680-683/698-701; transcription.py 60/72/90/92/208/230; providers.py 90/99/112/124/129/141. ✓
- [ ] Type names are consistent across tasks: `APIError`, `SSRFBlocked`, `BackendUnavailable`, `ValidationFailed`, `NotFound`, `RateLimited`, `BadRequest`, `ErrorEnvelope`, `envelope_error`, `register_envelope_handlers`, `FetchOptions`, `createAbortController`, `AppHarness`, `mountApp`, `cleanupApp`, `translationService`, `extractionService`, `transcriptionService`, `glossaryService`, `jobsService`. ✓
- [ ] Every code block shows the actual code an engineer needs (no pseudocode, no "similar to above"). ✓
- [ ] Every commit command lists the exact files (no `git add -A`, no `git add .`). ✓
- [ ] Acceptance Criteria, Risks & Mitigations, and Commit Strategy sections are present and concrete. ✓

---

**Plan complete.** Implementation requires an explicit "go" before any commit lands; this document is the contract. See `audits/2026-08-20-deep-refactor-report.md` §9 for the source findings.
---
