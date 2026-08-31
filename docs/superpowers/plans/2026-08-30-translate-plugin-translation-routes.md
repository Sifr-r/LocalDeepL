# Translate Plugin (Translation Routes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the deferred translation HTTP surface as a new `translate` boot plugin — four client-frozen routes with JobQueue-based async dispatch, Celery retirement, and five pedantic-review ride-along fixes — contract-compatible with the existing Flutter client, zero client changes.

**Architecture:** New plugin package `src/omniscribe/plugins/translate/` (schemas / service / routes / plugin), boot row 10 between `documents` and `ocr` in both `cordis.yml` trees. Sync translation re-homes the deleted `api/services/ai.py` logic verbatim (artifact fallback, prompt, temperature, system message); async submits onto the existing harness `JobQueue` (OCR pattern) with a `TranslationJobRunner` that walks the artifact's block tree via `core/translate/tree.translate_tree`. Status maps queue states onto the client's Celery-era vocabulary; results are read queue-natively from `JobRecord.result_artifact_id/token` — never leaking artifact tokens through the unauthenticated status endpoint (audit C-3/H-3 semantics).

**Tech Stack:** FastAPI (APIRouter), Pydantic v2, Cordis harness (`Plugin`, `Context.inject/service/mount_router`), `core/translate` (workflow, tree, entity_memory, glossary, nllb), pytest + pytest-asyncio auto mode, existing conftest fixtures.

**Spec:** `docs/superpowers/specs/2026-08-30-translate-plugin-translation-routes-design.md`

---

## Notes for the implementer

- **Python 3.11+ / uv only.** Run everything through `uv run`. Never `pip install`.
- **Pre-commit hooks** run ruff (check + format), mypy, uv-lock on every commit. If a hook reformats, `git add` the fixed file and make a NEW commit — never `--no-verify`.
- **Recovered reference code:** old routes/services in commit `44ef123^` (`api/routers/translation.py`, `api/services/ai.py`), old contract tests in `e6b7b89^`. The code blocks in this plan are the adapted versions — type them as shown.
- **Verified corrections to the spec text** (the spec's prose is slightly off in three places; the code blocks below are authoritative): (1) `TRANSLATION_SYSTEM_MESSAGE` is imported from `omniscribe.core.translate.nodes` (defined at `nodes.py:42`), not workflow.py; (2) the NLLB engine is held in a lazy module-level singleton, not a fresh instance per request (the old server reloaded the model on every call — same observable contract, no pathological reloads); (3) `start_app.vbs` no longer exists in the repo, so Celery retirement is compose-only.
- **Import TRANSLATION_SYSTEM_MESSAGE from nodes — do NOT redefine it.** The core workflow's own translate node already uses it (AGENTS.md system-role rule: system prompts flow exclusively through `call_llm`'s `system_prompt=` parameter with a pure user-role `messages` list — exactly the pattern in every code block below).
- **FastAPI >=0.141:** union return annotations on route handlers need `response_model=None` (verified in slice 1; empirically raises `FastAPIError` otherwise). Mounted plugin routes are invisible to `app.routes` introspection — assert mounted paths via `/openapi.json`.
- **Route-order constraint:** none needed here (no parametrized overlap among the four routes).
- Fast gate (every task): `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/omniscribe/plugins/translate/__init__.py` | Re-export the module-level `plugin` |
| `src/omniscribe/plugins/translate/schemas.py` | `TranslationRequest`, `AsyncTranslationRequest`, `NllbRequest` (old contract constraints, `extra="forbid"`) |
| `src/omniscribe/plugins/translate/service.py` | `TranslateError`, `build_translation_prompt`, sync `translate_text`, `_TranslatePayload`, `TranslationServiceImpl` (submit / `run_translate_job` / `job_status` / NLLB), status mapping |
| `src/omniscribe/plugins/translate/routes.py` | One `APIRouter` (tags=["translate"]) with the four routes |
| `src/omniscribe/plugins/translate/plugin.py` | `TranslatePlugin(Plugin)` — injects JobQueue/ArtifactStore/RuntimeService, registers services, mounts router |
| `src/omniscribe/resources/cordis.yml` | Boot row 10 (`translate`), `ocr` → 11 |
| `tests/conftest.py` | `_TEST_CORDIS_YML` gains the translate row (eleven rows) |
| `tests/plugins/test_translate_schemas.py` | Schema constraint unit tests |
| `tests/plugins/test_translate_service.py` | Sync re-home + runner + status mapping unit tests (stubbed `call_llm`) |
| `tests/routers/test_translate_routes.py` | The four client-frozen router contracts |
| `tests/harness/test_translate_boot.py` | Boot regression pins |
| `tests/plugins/test_boot_config.py` | Shipped-tree pins (eleven rows, router count 6) |
| `tests/harness/test_loader_env_overrides.py` | Pedantic 1.2 regression test |
| `tests/plugins/test_jobs_plugin.py` | Pedantic 1.6 pagination test (append) |
| `tests/core/recall/test_text_layer_recall.py` | Pedantic 1.9 regression test (append) |
| `compose.yaml` | Celery worker service removed |
| `AGENTS.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `README.md`, spec file | Docs updates |

---

### Task 1: Plugin package scaffold + schemas

**Files:**
- Create: `src/omniscribe/plugins/translate/__init__.py`
- Create: `src/omniscribe/plugins/translate/schemas.py`
- Test: `tests/plugins/test_translate_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/plugins/test_translate_schemas.py`:

```python
"""Unit tests for translate plugin request schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from omniscribe.plugins.translate.schemas import (
    AsyncTranslationRequest,
    NllbRequest,
    TranslationRequest,
)


def test_translation_request_defaults() -> None:
    body = TranslationRequest()
    assert body.text == ""
    assert body.text_artifact_id is None
    assert body.text_artifact_token is None
    assert body.target_language == "Spanish"
    assert body.glossary is None
    assert body.glossary_text is None
    assert body.sliding_window_words == 80
    assert body.dual_translate is False
    assert body.second_api_base is None
    assert body.second_api_key is None
    assert body.second_model is None
    assert body.api_base is None
    assert body.api_key is None
    assert body.model is None


def test_translation_request_rejects_extra_fields() -> None:
    # The old contract was extra="forbid"; the client never sends
    # prompt_template/channel_id (notifier leaves them None).
    with pytest.raises(ValidationError):
        TranslationRequest(text="x", prompt_template="y")


def test_target_language_bounds() -> None:
    assert TranslationRequest(target_language="French").target_language == "French"
    with pytest.raises(ValidationError):
        TranslationRequest(target_language="")


def test_target_language_max_length() -> None:
    with pytest.raises(ValidationError):
        TranslationRequest(target_language="x" * 81)


def test_sliding_window_words_bounds() -> None:
    assert TranslationRequest(sliding_window_words=0).sliding_window_words == 0
    assert TranslationRequest(sliding_window_words=2000).sliding_window_words == 2000
    with pytest.raises(ValidationError):
        TranslationRequest(sliding_window_words=2001)
    with pytest.raises(ValidationError):
        TranslationRequest(sliding_window_words=-1)


def test_glossary_max_entries() -> None:
    entries = [{"source": "a", "target": "b"}] * 1000
    assert TranslationRequest(glossary=entries).glossary == entries
    with pytest.raises(ValidationError):
        TranslationRequest(glossary=entries + entries)


def test_strings_are_trimmed() -> None:
    body = TranslationRequest(text="  hello  ", api_base="  http://x  ")
    assert body.text == "hello"
    assert body.api_base == "http://x"


def test_async_request_requires_and_bounds_artifact_pair() -> None:
    body = AsyncTranslationRequest(
        text_artifact_id="a" * 32, text_artifact_token="t" * 43
    )
    assert body.target_language == "English"
    assert body.channel_id is None
    with pytest.raises(ValidationError):
        AsyncTranslationRequest(text_artifact_id="short", text_artifact_token="t" * 43)
    with pytest.raises(ValidationError):
        AsyncTranslationRequest(
            text_artifact_id="a" * 32, text_artifact_token="t" * 31
        )
    with pytest.raises(ValidationError):
        AsyncTranslationRequest(
            text_artifact_id="a" * 32, text_artifact_token="t" * 257
        )


def test_async_request_accepts_text_and_channel_id_for_tolerance() -> None:
    # The client posts the same toJson for async as for sync; text and
    # channel_id are accepted and ignored (spec: tolerant superset).
    body = AsyncTranslationRequest(
        text="ignored",
        text_artifact_id="a" * 32,
        text_artifact_token="t" * 43,
        channel_id="ch-1",
    )
    assert body.text == "ignored"
    assert body.channel_id == "ch-1"


def test_nllb_request_defaults() -> None:
    body = NllbRequest()
    assert body.text == ""
    assert body.target_language == "English"
```

Note: the async artifact pair is optional-with-bounds in the schema; the route-level 400 for a missing pair lands in Task 4 (mirrors the sync route).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_translate_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'omniscribe.plugins.translate'`

- [ ] **Step 3: Create the package and schemas**

Create `src/omniscribe/plugins/translate/schemas.py`:

```python
"""Request schemas for the translate plugin.

Field constraints reproduce the pre-harness contract (commit ``44ef123^``,
``api/schemas/requests.py``) so the existing Flutter client keeps working
without changes. The local ``_TrimmedModel`` mirrors the documents
plugin's shared base (it is private there, so it is copied, not imported).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _TrimmedModel(BaseModel):
    """Shared config: reject unknown fields, trim string values."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TranslationRequest(_TrimmedModel):
    text: str = ""
    text_artifact_id: str | None = None
    text_artifact_token: str | None = None
    target_language: str = Field(default="Spanish", min_length=1, max_length=80)
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    glossary: list[dict] | None = Field(default=None, max_length=1000)
    glossary_text: str | None = None
    sliding_window_words: int = Field(default=80, ge=0, le=2000)
    dual_translate: bool = False
    second_api_base: str | None = None
    second_api_key: str | None = None
    second_model: str | None = None


class AsyncTranslationRequest(TranslationRequest):
    """Async (tree-aware) submission: artifact pair required at the route
    level (400 envelope), legacy defaults, ``text``/``channel_id``
    accepted and ignored."""

    text_artifact_id: str | None = Field(default=None, min_length=32, max_length=32)
    text_artifact_token: str | None = Field(default=None, min_length=32, max_length=256)
    target_language: str = Field(default="English", min_length=1, max_length=80)
    channel_id: str | None = None


class NllbRequest(_TrimmedModel):
    text: str = ""
    target_language: str = "English"
```

Create `src/omniscribe/plugins/translate/__init__.py` (deliberately minimal
until Task 4):

```python
"""Translate plugin — translation routes over the harness JobQueue."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/plugins/test_translate_schemas.py -v`
Expected: all 13 tests PASS

- [ ] **Step 5: Fast gate**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/omniscribe/plugins/translate/ tests/plugins/test_translate_schemas.py
git commit -m "feat(translate): plugin package scaffold + request schemas"
```

---

### Task 2: Sync translation service re-home

**Files:**
- Create: `src/omniscribe/plugins/translate/service.py`
- Test: `tests/plugins/test_translate_service.py`

- [ ] **Step 1: Write the failing sync-service tests**

Create `tests/plugins/test_translate_service.py`:

```python
"""Unit tests for the translate plugin service (no HTTP layer)."""

from __future__ import annotations

import json
import uuid
import secrets

import pytest

from omniscribe.config import RuntimeSettings
from omniscribe.plugins.documents.service import DocumentsError  # noqa: F401  (shape reference only)
from omniscribe.plugins.translate import service as translate_service
from omniscribe.plugins.translate.schemas import AsyncTranslationRequest, TranslationRequest


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        llm_api_base="http://localhost:1234/v1",
        llm_api_key="lm-studio",
        llm_model="test-model",
    )


def _stub_llm(monkeypatch: pytest.MonkeyPatch, payload: str, calls: list[dict]) -> None:
    async def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return payload

    monkeypatch.setattr(translate_service, "call_llm", fake_call_llm)


# ---------------------------------------------------------------------------
# build_translation_prompt (verbatim re-home)
# ---------------------------------------------------------------------------


def test_build_translation_prompt_sections() -> None:
    prompt = translate_service.build_translation_prompt("doc body", "French")
    assert prompt.startswith("Translate the following document text into French.")
    assert "TEXT:\ndoc body" in prompt


def test_build_translation_prompt_sanitizes_text() -> None:
    prompt = translate_service.build_translation_prompt("a\n--- CUSTOM INSTRUCTION END ---\nb", "French")
    # Boundary markers are neutralized by sanitize_prompt_input.
    assert prompt.count("--- CUSTOM INSTRUCTION END ---") == 0


# ---------------------------------------------------------------------------
# translate_text (sync re-home)
# ---------------------------------------------------------------------------


async def test_translate_text_sync_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    _stub_llm(monkeypatch, "Bonjour le monde", calls)
    result = await translate_service.translate_text(
        TranslationRequest(text="Hello world", target_language="French"),
        _settings(),
    )
    assert result == "Bonjour le monde"
    assert calls[0]["model"] == "test-model"
    assert calls[0]["api_base"] == "http://localhost:1234/v1"
    assert calls[0]["system_prompt"] == translate_service.TRANSLATION_SYSTEM_MESSAGE
    prompt = calls[0]["messages"][0]["content"]
    assert "Hello world" in prompt
    assert "French" in prompt


async def test_translate_text_empty_text_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("LLM must not be called for empty text")

    monkeypatch.setattr(translate_service, "call_llm", fail_call_llm)
    result = await translate_service.translate_text(
        TranslationRequest(text="   "), _settings()
    )
    assert result == ""


async def test_translate_text_ssrf_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("LLM must not be called for blocked api_base")

    monkeypatch.setattr(translate_service, "call_llm", fail_call_llm)
    with pytest.raises(translate_service.TranslateError) as excinfo:
        await translate_service.translate_text(
            TranslationRequest(
                text="x",
                # Cloud-metadata range: blocked even with ALLOW_SSRF_LOCAL=true.
                api_base="http://169.254.169.254/latest",
            ),
            _settings(),
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.error == "ssrf_blocked"


async def test_translate_text_provider_failure_is_ai_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(**kwargs: object) -> str:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(translate_service, "call_llm", boom)
    with pytest.raises(translate_service.TranslateError) as excinfo:
        await translate_service.translate_text(
            TranslationRequest(text="x"), _settings()
        )
    assert excinfo.value.status_code == 502
    assert excinfo.value.error == "ai_error"
```

Note: the artifact-fallback join test needs an `ArtifactStore`, which is
easier through the service instance — it is covered in Task 3's
`TranslationServiceImpl` tests. This task pins the pure function + error
semantics.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_translate_service.py -v`
Expected: FAIL — `ModuleNotFoundError: ... translate.service`

- [ ] **Step 3: Implement the sync service (service.py, part 1)**

Create `src/omniscribe/plugins/translate/service.py`:

```python
"""Translate service: sync re-home, async tree runner, status mapping.

The sync path is a verbatim re-home of the pre-harness
``api/services/ai.py`` ``translate_text`` (commit ``44ef123^``), adapted
to harness settings resolution and the token-bound ``ArtifactStore``.
The module deliberately imports ``TRANSLATION_SYSTEM_MESSAGE`` from
``core.translate.nodes`` — the same system message the LangGraph workflow
uses — rather than redefining it.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any

from omniscribe.config import RuntimeSettings
from omniscribe.core.llm.client import call_llm
from omniscribe.core.llm.temperatures import TEMPERATURE_TRANSLATION
from omniscribe.core.translate.nodes import TRANSLATION_SYSTEM_MESSAGE
from omniscribe.plugins.documents.service import build_tree, load_pages
from omniscribe.plugins.translate.schemas import (
    AsyncTranslationRequest,
    TranslationRequest,
)
from omniscribe.utils.prompt_safety import sanitize_prompt_input
from omniscribe.utils.security import check_ssrf_target_sync

_LOGGER = logging.getLogger("omniscribe.plugins.translate")


class TranslateError(Exception):
    """User-facing translate error carrying the envelope wire fields."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


def build_translation_prompt(text: str, target_language: str) -> str:
    """Verbatim re-home from ``api/services/ai.py`` (44ef123^)."""
    safe_text = sanitize_prompt_input(text)
    return (
        f"Translate the following document text into {target_language}. "
        f"Maintain all markdown formatting, headings, lists, tables, and mathematical formulas exactly. "
        f"Do not add any introductory or concluding comments, explanations, or meta-commentary. "
        f"Only output the direct translation.\n\n"
        f"TEXT:\n{safe_text}"
    )


def _parse_json_object(blob: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(blob)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _resolve_coordinates(
    request_base: str | None,
    request_key: str | None,
    request_model: str | None,
    settings: RuntimeSettings,
) -> tuple[str, str, str]:
    """Override → settings trio; SSRF-check the override only
    (pipeline_bridge trust boundary)."""
    if request_base and request_base.strip():
        check = check_ssrf_target_sync(request_base.strip())
        if not check.allowed:
            raise TranslateError(
                403,
                "ssrf_blocked",
                f"URL targets a blocked address: {check.reason}",
            )
    return (
        (request_base or settings.llm_api_base).strip(),
        (request_key or settings.llm_api_key).strip(),
        (request_model or settings.llm_model).strip(),
    )


async def translate_text(
    request: TranslationRequest, settings: RuntimeSettings
) -> str:
    """Sync single-shot translation; verbatim old semantics."""
    source_text = request.text.strip()
    if not source_text and request.text_artifact_id and request.text_artifact_token:
        from omniscribe.plugins.artifacts import ArtifactStore

        store = _artifact_store_for_caller()
        blob = await store.get(request.text_artifact_id, request.text_artifact_token)
        if blob is None:
            raise TranslateError(404, "not_found", "text artifact not found")
        raw = _parse_json_object(blob.blob)
        if raw is not None:
            pages = load_pages(raw)
            source_text = "\n\n".join(
                "\n".join(lines) for _page, lines in sorted(pages.items())
            ).strip()

    if not source_text:
        return ""

    api_base, api_key, model = _resolve_coordinates(
        request.api_base, request.api_key, request.model, settings
    )
    prompt = build_translation_prompt(source_text, request.target_language)
    try:
        content = await call_llm(
            model=model,
            api_base=api_base,
            api_key=api_key,
            temperature=TEMPERATURE_TRANSLATION,
            system_prompt=TRANSLATION_SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        _LOGGER.exception("Translation request failed")
        raise TranslateError(
            502, "ai_error", "The AI service request failed."
        ) from exc
    return content.strip()
```

STOP — the `translate_text` signature above reaches for an
`_artifact_store_for_caller()` global, which is wrong. The store must be
injected. Final signature (use THIS one; update the Step 1 tests'
invocations accordingly — they pass only `(request, settings)` because
their paths never touch the store; add `store=None` handling):

Replace the artifact-fallback block and signature with:

```python
async def translate_text(
    request: TranslationRequest,
    settings: RuntimeSettings,
    store: ArtifactStore | None = None,
) -> str:
    """Sync single-shot translation; verbatim old semantics."""
    source_text = request.text.strip()
    if (
        not source_text
        and request.text_artifact_id
        and request.text_artifact_token
    ):
        if store is None:
            raise TranslateError(404, "not_found", "text artifact not found")
        blob = await store.get(request.text_artifact_id, request.text_artifact_token)
        if blob is None:
            raise TranslateError(404, "not_found", "text artifact not found")
        raw = _parse_json_object(blob.blob)
        if raw is not None:
            pages = load_pages(raw)
            source_text = "\n\n".join(
                "\n".join(lines) for _page, lines in sorted(pages.items())
            ).strip()
```

with `from omniscribe.plugins.artifacts import ArtifactStore` moved to the
module-top imports (it is a Protocol — import is cheap and cycle-free).
The `store=None` + 404 branch exists only so the pure-function tests can
call `translate_text(request, settings)`; the route always passes the
injected store. Add one more test now:

```python
async def test_translate_text_artifact_fallback_joins_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStore:
        async def get(self, artifact_id: str, token: str):
            class _Blob:
                blob = json.dumps({"0": "page one", "1": "page two"}).encode("utf-8")

            return _Blob()

    calls: list[dict] = []
    _stub_llm(monkeypatch, "traduit", calls)
    result = await translate_service.translate_text(
        TranslationRequest(
            text_artifact_id="a" * 32, text_artifact_token="t" * 43
        ),
        _settings(),
        store=_FakeStore(),  # type: ignore[arg-type]
    )
    assert result == "traduit"
    prompt = calls[0]["messages"][0]["content"]
    assert "page one\n\npage two" in prompt


async def test_translate_text_unknown_artifact_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EmptyStore:
        async def get(self, artifact_id: str, token: str):
            return None

    monkeypatch.setattr(
        translate_service, "call_llm",
        lambda **kw: (_ for _ in ()).throw(AssertionError("unreachable")),
    )
    with pytest.raises(translate_service.TranslateError) as excinfo:
        await translate_service.translate_text(
            TranslationRequest(
                text_artifact_id="a" * 32, text_artifact_token="t" * 43
            ),
            _settings(),
            store=_EmptyStore(),  # type: ignore[arg-type]
        )
    assert excinfo.value.status_code == 404
```

(For the 404 test, the stub assignment must be an async function, not a
lambda returning a generator — use:

```python
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("unreachable")

    monkeypatch.setattr(translate_service, "call_llm", fail_call_llm)
```

in place of the lambda line.)

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `uv run pytest tests/plugins/test_translate_service.py -v`
Expected: all 9 tests PASS (2 prompt + 5 sync + 2 artifact-fallback)

- [ ] **Step 5: Fast gate**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/omniscribe/plugins/translate/service.py tests/plugins/test_translate_service.py
git commit -m "feat(translate): sync translate_text re-home with prompt builder"
```

---

### Task 3: Async runner + status mapping

**Files:**
- Modify: `src/omniscribe/plugins/translate/service.py` (append)
- Test: `tests/plugins/test_translate_service.py` (append)

- [ ] **Step 1: Write the failing runner + status tests (append)**

Append to `tests/plugins/test_translate_service.py`:

```python
# ---------------------------------------------------------------------------
# TranslationServiceImpl: submit / run_translate_job / job_status
# ---------------------------------------------------------------------------


class _FakeJobQueue:
    """Records submissions; no worker. status() reads the record we plant."""

    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    async def submit(self, request: Any, *, request_meta: dict | None = None):
        from omniscribe.plugins.jobs import JobHandle

        job_id = uuid.uuid4().hex
        self.records[job_id] = (request, request_meta or {})
        return JobHandle(job_id=job_id, status_url=f"/api/jobs/{job_id}/status")

    async def status(self, job_id: str):
        return self.records.get(job_id)


class _FakeStore:
    """Artifact store double keyed by id → (token, blob, content_type)."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[str, bytes, str]] = {}

    async def put(self, blob: bytes, *, content_type: str, owner_job_id: str, ttl_seconds: int | None = None):
        artifact_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        self.blobs[artifact_id] = (token, blob, content_type)
        return (artifact_id, token)

    async def get(self, artifact_id: str, token: str):
        entry = self.blobs.get(artifact_id)
        if entry is None or entry[0] != token:
            return None

        class _Blob:
            blob = entry[1]
            content_type = entry[2]

        return _Blob()


def _service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    llm_payload: str = "traduit",
    queue: _FakeJobQueue | None = None,
    store: _FakeStore | None = None,
) -> tuple[translate_service.TranslationServiceImpl, _FakeJobQueue, _FakeStore, list[dict]]:
    calls: list[dict] = []
    _stub_llm(monkeypatch, llm_payload, calls)
    q = queue or _FakeJobQueue()
    s = store or _FakeStore()
    impl = translate_service.TranslationServiceImpl(
        _settings(), q, s, max_buffered_jobs=16
    )
    return impl, q, s, calls


def _async_request() -> AsyncTranslationRequest:
    return AsyncTranslationRequest(
        text_artifact_id="a" * 32, text_artifact_token="t" * 43
    )


async def test_run_translate_job_translates_tree_and_stores_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl, _q, store, calls = _service(monkeypatch)
    artifact_id = uuid.uuid4().hex
    store.blobs[artifact_id] = (
        "t" * 43,
        json.dumps({"0": "Hello world.", "1": "Second page."}).encode("utf-8"),
        "application/json",
    )
    payload = translate_service._TranslatePayload(
        submission_id="s-1", request=_async_request()
    )
    # Point the payload at the seeded artifact.
    payload.request = AsyncTranslationRequest(
        text_artifact_id=artifact_id, text_artifact_token="t" * 43
    )

    outcome = await impl.run_translate_job(payload)

    assert outcome.content_type == "application/json"
    summary = json.loads(outcome.blob)
    assert summary["artifact_id"] == artifact_id
    assert summary["page_count"] == 2
    assert summary["blocks_translated"] >= 2
    translated_id = summary["translated_artifact_id"]
    assert translated_id in store.blobs
    # The status result must never carry the translated artifact token.
    assert "translated_artifact_token" not in summary
    translated_blob = store.blobs[translated_id][1]
    assert "traduit" in translated_blob.decode("utf-8")
    assert calls, "translator hook must reach call_llm"


async def test_run_translate_job_missing_artifact_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl, _q, _store, _calls = _service(monkeypatch)
    payload = translate_service._TranslatePayload(
        submission_id="s-1", request=_async_request()
    )
    with pytest.raises(FileNotFoundError):
        await impl.run_translate_job(payload)


async def test_run_translate_job_rejects_foreign_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl, _q, _store, _calls = _service(monkeypatch)
    with pytest.raises(ValueError):
        await impl.run_translate_job(object())


async def test_job_status_maps_all_queue_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl, _q, _store, _calls = _service(monkeypatch)
    from dataclasses import replace as dc_replace

    from omniscribe.plugins.state_backend import JobRecord

    base = JobRecord(job_id="j-1", status="queued")
    assert impl.job_status("missing") is None

    queued = impl.job_status_sync(base)
    assert queued == {"job_id": "j-1", "state": "PENDING", "status": "Pending..."}

    running = impl.job_status_sync(dc_replace(base, status="running"))
    assert running["state"] == "PROGRESS"

    error = impl.job_status_sync(dc_replace(base, status="error", error="boom"))
    assert error["state"] == "FAILURE"
    assert error["error"] == "internal_error"
    # The record's exception text must not leak.
    assert "boom" not in json.dumps(error)

    cancelled = impl.job_status_sync(dc_replace(base, status="cancelled"))
    assert cancelled["state"] == "FAILURE"
    assert cancelled["error"] == "cancelled"

    complete_record = dc_replace(
        base,
        status="complete",
        result_artifact_id="r-1",
        result_artifact_token="rt",
    )
    store_blob = json.dumps({"page_count": 1}).encode("utf-8")
    impl._store.blobs["r-1"] = ("rt", store_blob, "application/json")
    complete = await impl.job_status(complete_record)
    assert complete is not None
    assert complete["state"] == "SUCCESS"
    assert complete["result"] == {"page_count": 1}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/plugins/test_translate_service.py -v -k "job or status"`
Expected: FAIL — `AttributeError: ... has no attribute 'TranslationServiceImpl'`

- [ ] **Step 3: Implement the runner + status mapping (append to service.py)**

```python
# ---------------------------------------------------------------------------
# Async submission / runner / status mapping
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402  (move to top imports)
from omniscribe.core.translate.tree import translate_tree  # noqa: E402
from omniscribe.core.translate.entity_memory import EntityMemory  # noqa: E402
from omniscribe.core.translate.glossary import Glossary  # noqa: E402
from omniscribe.plugins.jobs import JobOutcome  # noqa: E402

# (Move ALL of these into the module-top import block; they are listed here
# to show exactly what this section adds. ruff isort will enforce placement.)


@dataclass(frozen=True)
class _TranslatePayload:
    """One queued translation: submission id + the validated request."""

    submission_id: str
    request: AsyncTranslationRequest


class TranslationService(Protocol):
    async def submit(self, request: AsyncTranslationRequest) -> dict[str, str]: ...
    async def run_translate_job(self, payload: Any) -> JobOutcome: ...
    async def job_status(self, job_id: str) -> dict[str, Any] | None: ...
    def job_status_sync(self, record: Any) -> dict[str, Any]: ...


class TranslationServiceImpl:
    """Harness translation service over the JobQueue + ArtifactStore."""

    def __init__(
        self,
        settings: RuntimeSettings,
        queue: Any,
        store: Any,
        *,
        max_buffered_jobs: int = 500,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._store = store
        self._max_buffered_jobs = max_buffered_jobs
        self._submission_to_job: dict[str, str] = {}

    # -- submission ---------------------------------------------------------

    async def submit(self, request: AsyncTranslationRequest) -> dict[str, str]:
        from omniscribe.core.translate.config import AsyncTranslationUnavailable
        from omniscribe.core.translate.workflow import get_translation_app

        # Availability first (cheap, cached), then artifact existence.
        try:
            get_translation_app()
        except AsyncTranslationUnavailable as exc:
            raise TranslateError(503, "backend_unavailable", str(exc)) from exc

        blob = await self._store.get(
            request.text_artifact_id, request.text_artifact_token
        )
        if blob is None:
            raise TranslateError(404, "not_found", "text artifact not found")

        submission_id = secrets.token_hex(16)
        handle = await self._queue.submit(
            _TranslatePayload(submission_id=submission_id, request=request),
            request_meta={
                "submission_id": submission_id,
                "target_language": request.target_language,
            },
        )
        self._submission_to_job[submission_id] = handle.job_id
        while len(self._submission_to_job) > self._max_buffered_jobs:
            self._submission_to_job.pop(next(iter(self._submission_to_job)), None)
        return {"job_id": handle.job_id, "status": "Processing"}

    # -- runner -------------------------------------------------------------

    async def run_translate_job(self, payload: Any) -> JobOutcome:
        if not isinstance(payload, _TranslatePayload):
            raise ValueError("translate job queue received a foreign payload")
        request = payload.request
        job_id = self._submission_to_job.get(payload.submission_id, "")

        blob = await self._store.get(
            request.text_artifact_id, request.text_artifact_token
        )
        if blob is None:
            raise FileNotFoundError("text artifact not found")
        raw = _parse_json_object(blob.blob)
        if raw is None:
            raise FileNotFoundError("text artifact not found")
        pages = load_pages(raw)
        tree = build_tree(pages)

        memory = EntityMemory()
        for lines in pages.values():
            for line in lines:
                memory.add_text(line)
        glossary = _build_glossary(request)

        translator = _make_translator(
            request.api_base, request.api_key, request.model, self._settings
        )
        second_translator = None
        if request.dual_translate:
            second_translator = _make_translator(
                request.second_api_base,
                request.second_api_key,
                request.second_model,
                self._settings,
            )

        translated_tree = await translate_tree(
            tree,
            target_language=request.target_language,
            translator=translator,
            glossary=glossary,
            memory=memory,
            sliding_window_words=request.sliding_window_words,
            dual_translate=request.dual_translate,
            second_translator=second_translator,
        )

        translated_pages = {
            str(page.page_idx): "\n".join(
                child.text for child in page.children if child.text
            )
            for page in translated_tree.pages
        }
        blocks_translated = sum(
            1
            for page in translated_tree.pages
            for child in page.children
            if child.text
        )
        translated_handle = await self._store.put(
            json.dumps(translated_pages).encode("utf-8"),
            content_type="application/json",
            owner_job_id=job_id,
        )
        summary = {
            "artifact_id": request.text_artifact_id,
            # Deliberately NO translated_artifact_token: the status endpoint
            # is unauthenticated (audit C-3/H-3 semantics).
            "translated_artifact_id": translated_handle.id,
            "page_count": len(translated_tree.pages),
            "blocks_translated": blocks_translated,
        }
        return JobOutcome(
            blob=json.dumps(summary).encode("utf-8"),
            content_type="application/json",
        )

    # -- status -------------------------------------------------------------

    def job_status_sync(self, record: Any) -> dict[str, Any]:
        """Map one JobRecord to the client's Celery-era status vocabulary."""
        body: dict[str, Any] = {"job_id": record.job_id}
        if record.status == "queued":
            body.update(state="PENDING", status="Pending...")
        elif record.status == "running":
            body.update(state="PROGRESS", status="Processing...")
        elif record.status == "error":
            body.update(
                state="FAILURE",
                status="Failed",
                error="internal_error",
                detail="The translation job failed.",
            )
        elif record.status == "cancelled":
            body.update(
                state="FAILURE",
                status="Cancelled",
                error="cancelled",
                detail="Translation was cancelled.",
            )
        else:  # complete
            body.update(state="SUCCESS", status="Completed")
        return body

    async def job_status(self, job_id: str) -> dict[str, Any] | None:
        record = await self._queue.status(job_id)
        if record is None:
            return None
        body = self.job_status_sync(record)
        if record.status == "complete":
            result = await self._load_result(record)
            if result is not None:
                body["result"] = result
        return body

    async def _load_result(self, record: Any) -> dict[str, Any] | None:
        if not record.result_artifact_id or not record.result_artifact_token:
            return None
        blob = await self._store.get(
            record.result_artifact_id, record.result_artifact_token
        )
        if blob is None:
            return None
        return _parse_json_object(blob.blob)


def _build_glossary(request: AsyncTranslationRequest) -> Glossary | None:
    # Old-route precedence (verified): entries win over paired-lines text.
    if request.glossary:
        return Glossary.from_dict({"entries": request.glossary})
    if request.glossary_text:
        return Glossary.from_paired_lines(request.glossary_text)
    return None


def _make_translator(
    request_base: str | None,
    request_key: str | None,
    request_model: str | None,
    settings: RuntimeSettings,
):
    api_base, api_key, model = _resolve_coordinates(
        request_base, request_key, request_model, settings
    )

    async def translator(prompt: str, target_language: str) -> str:
        return await call_llm(
            model=model,
            api_base=api_base,
            api_key=api_key,
            temperature=TEMPERATURE_TRANSLATION_TREE,
            system_prompt=TRANSLATION_SYSTEM_MESSAGE,
            prompt=prompt,
        )

    return translator
```

Adjustments while typing:
- Move every `# noqa: E402`-marked import into the module-top import block
  (ruff isort enforces it). Also import `Protocol` from `typing` at the
  top (it is already imported as `Any` — extend the typing import).
- The service needs `Protocol` only if you keep the `TranslationService`
  Protocol class — keep it (the plugin registers under it, mirroring
  `OCRService`).
- `translate_text`'s `store: ArtifactStore | None` annotation now comes
  from the top-level import too.
- If `translate_tree`'s `memory`/`glossary` parameter names differ from
  the spec (verify against `core/translate/tree.py:68-82` — they were
  verified as `glossary`/`memory`/`sliding_window_words`/
  `dual_translate`/`second_translator`), adapt.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/plugins/test_translate_service.py -v`
Expected: all 13 tests PASS (9 from Task 2 + 4 new)

- [ ] **Step 5: Fast gate**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/omniscribe/plugins/translate/service.py tests/plugins/test_translate_service.py
git commit -m "feat(translate): JobQueue runner, tree-aware translation, status mapping"
```

---

### Task 4: Plugin + routes + conftest row + router contract tests

**Files:**
- Create: `src/omniscribe/plugins/translate/routes.py`
- Create: `src/omniscribe/plugins/translate/plugin.py`
- Modify: `src/omniscribe/plugins/translate/__init__.py`
- Modify: `tests/conftest.py` (`_TEST_CORDIS_YML` gains the translate row)
- Test: `tests/routers/test_translate_routes.py`

- [ ] **Step 1: Update the conftest test tree**

In `tests/conftest.py` `_TEST_CORDIS_YML`, insert between the `documents`
and `ocr` rows (making it ELEVEN rows); update the "ten-row"/"ten-plugin"
docstring/comment mentions to "eleven-row"/"eleven-plugin":

```yaml
  - id: documents
    use: omniscribe.plugins.documents:plugin

  - id: translate
    use: omniscribe.plugins.translate:plugin

  - id: ocr
    use: omniscribe.plugins.ocr:plugin
```

- [ ] **Step 2: Write the failing router tests**

Create `tests/routers/test_translate_routes.py`:

```python
"""Router contract tests for the translate plugin.

Contract source: the Flutter client (`feature_repository.dart:68-107`,
`api_constants.dart:59-64`, `feature_models.dart`) plus the recovered
pre-harness tests (commit `e6b7b89^`).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient

from omniscribe.plugins.state_backend import StateBackend


def _seed_text_artifact(
    client: TestClient, pages: dict[str, str]
) -> tuple[str, str]:
    backend = client.app.state.context.inject(StateBackend)
    artifact_id = uuid.uuid4().hex
    token = "t" * 43
    asyncio.run(
        backend.put_artifact(
            id=artifact_id,
            token=token,
            owner_job_id="",
            content_type="application/json",
            blob=json.dumps(pages).encode("utf-8"),
            ttl_seconds=3600,
        )
    )
    return artifact_id, token


def _stub_llm(monkeypatch: Any, payload: str) -> None:
    from omniscribe.plugins.translate import service

    async def fake_call_llm(**kwargs: Any) -> str:
        return payload

    monkeypatch.setattr(service, "call_llm", fake_call_llm)


def _stub_llm_unreachable(monkeypatch: Any) -> None:
    from omniscribe.plugins.translate import service

    async def fail_call_llm(**kwargs: Any) -> str:
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(service, "call_llm", fail_call_llm)


def _wait_translation_state(
    client: TestClient, job_id: str, state: str, *, timeout: float = 5.0
) -> dict[str, Any]:
    """Poll the translate status route until `state` is reached.

    The queue worker runs on the TestClient portal loop, so sleeping the
    test thread lets it make progress between polls.
    """
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/api/translate/status/{job_id}").json()
        if body.get("state") == state:
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached {state}: {body}")


def test_translate_routes_are_mounted(client: TestClient) -> None:
    paths = set(json.loads(client.get("/openapi.json").text)["paths"])
    assert "/api/translate" in paths
    assert "/api/translate/async" in paths
    assert "/api/translate/status/{job_id}" in paths
    assert "/api/translate/nllb" in paths


def test_translate_sync_happy_path(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm(monkeypatch, "Bonjour le monde")
    response = client.post(
        "/api/translate",
        json={"text": "Hello world", "target_language": "French"},
    )
    assert response.status_code == 200
    assert response.json() == {"translated_text": "Bonjour le monde"}


def test_translate_sync_missing_text_and_artifact_400(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm_unreachable(monkeypatch)
    response = client.post("/api/translate", json={"target_language": "French"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert body["detail"] == "'text' or 'text_artifact_id'/'text_artifact_token' is required"


def test_translate_sync_ssrf_blocked_403(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm_unreachable(monkeypatch)
    response = client.post(
        "/api/translate",
        json={
            "text": "x",
            "api_base": "http://169.254.169.254/latest",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"] == "ssrf_blocked"


def test_translate_sync_artifact_fallback(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm(monkeypatch, "traduit")
    artifact_id, token = _seed_text_artifact(client, {"0": "page one", "1": "page two"})
    response = client.post(
        "/api/translate",
        json={
            "text_artifact_id": artifact_id,
            "text_artifact_token": token,
            "target_language": "French",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"translated_text": "traduit"}


def test_translate_sync_unknown_artifact_404(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm_unreachable(monkeypatch)
    response = client.post(
        "/api/translate",
        json={"text_artifact_id": "0" * 32, "text_artifact_token": "t" * 43},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_translate_async_submit_and_complete(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm(monkeypatch, "traduit")
    artifact_id, token = _seed_text_artifact(client, {"0": "Hello world."})
    response = client.post(
        "/api/translate/async",
        json={"text_artifact_id": artifact_id, "text_artifact_token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Processing"
    assert body["job_id"]

    pending = client.get(f"/api/translate/status/{body['job_id']}").json()
    assert pending["state"] in {"PENDING", "PROGRESS", "SUCCESS"}

    done = _wait_translation_state(client, body["job_id"], "SUCCESS")
    result = done["result"]
    assert result["artifact_id"] == artifact_id
    assert result["page_count"] == 1
    # C-3/H-3 semantics: no artifact token ever crosses the status endpoint.
    assert "translated_artifact_token" not in json.dumps(done)
    assert "token" not in result


def test_translate_async_missing_artifact_400(client: TestClient) -> None:
    response = client.post("/api/translate/async", json={"text": "no artifact"})
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


def test_translate_async_unknown_artifact_404(
    client: TestClient, monkeypatch: Any
) -> None:
    _stub_llm_unreachable(monkeypatch)
    response = client.post(
        "/api/translate/async",
        json={"text_artifact_id": "0" * 32, "text_artifact_token": "t" * 43},
    )
    assert response.status_code == 404


def test_translate_async_langgraph_missing_503(
    client: TestClient, monkeypatch: Any
) -> None:
    from omniscribe.core.translate.config import AsyncTranslationUnavailable
    from omniscribe.plugins.translate import service

    def raise_unavailable() -> None:
        raise AsyncTranslationUnavailable("langgraph is not installed")

    monkeypatch.setattr(service, "get_translation_app", raise_unavailable)
    artifact_id, token = _seed_text_artifact(client, {"0": "Hello."})
    response = client.post(
        "/api/translate/async",
        json={"text_artifact_id": artifact_id, "text_artifact_token": token},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "backend_unavailable"
    assert "langgraph" in body["detail"]


def test_translate_status_unknown_job_404(client: TestClient) -> None:
    response = client.get("/api/translate/status/no-such-job")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_translate_nllb_happy_path(client: TestClient, monkeypatch: Any) -> None:
    from omniscribe.core.translate.nllb import NLLBResult
    from omniscribe.plugins.translate import service

    class _FakeEngine:
        def is_available(self) -> bool:
            return True

        async def translate(self, text: str, target_language: str) -> NLLBResult:
            return NLLBResult(text="bonjour", source_lang="eng_Latn", target_lang="fra_Latn")

    monkeypatch.setattr(service, "_get_nllb_engine", lambda: _FakeEngine())
    response = client.post(
        "/api/translate/nllb",
        json={"text": "hello", "target_language": "French"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "translated_text": "bonjour",
        "source_lang": "eng_Latn",
        "target_lang": "fra_Latn",
    }


def test_translate_nllb_blank_text_422(client: TestClient) -> None:
    response = client.post("/api/translate/nllb", json={"text": "   "})
    assert response.status_code == 422
    assert response.json()["error"] == "bad_request"


def test_translate_nllb_unavailable_503(client: TestClient, monkeypatch: Any) -> None:
    from omniscribe.plugins.translate import service

    class _UnavailableEngine:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(service, "_get_nllb_engine", lambda: _UnavailableEngine())
    response = client.post(
        "/api/translate/nllb", json={"text": "hello", "target_language": "French"}
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "backend_unavailable"
    assert "uv sync --extra nllb" in body["detail"]
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/routers/test_translate_routes.py -v`
Expected: FAIL — `omniscribe.plugins.translate:plugin` cannot be imported

- [ ] **Step 4: Implement routes.py + plugin.py + __init__.py**

Create `src/omniscribe/plugins/translate/routes.py`:

```python
"""HTTP routes for the translate plugin (client-frozen contract)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.harness.context import Context
from omniscribe.plugins.translate.schemas import (
    AsyncTranslationRequest,
    NllbRequest,
    TranslationRequest,
)
from omniscribe.plugins.translate.service import (
    TranslationService,
    TranslateError,
)


def _envelope(status_code: int, error: str, detail: str) -> JSONResponse:
    """Stable error envelope the Flutter client parses."""
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def build_translate_router(service: TranslationService) -> APIRouter:
    router = APIRouter(tags=["translate"])

    @router.post("/api/translate", response_model=None)
    async def translate(body: TranslationRequest) -> dict[str, Any] | JSONResponse:
        if not body.text.strip() and not (
            body.text_artifact_id and body.text_artifact_token
        ):
            return _envelope(
                400,
                "bad_request",
                "'text' or 'text_artifact_id'/'text_artifact_token' is required",
            )
        try:
            translated = await service.translate_sync(body)
        except TranslateError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return {"translated_text": translated}

    @router.post("/api/translate/async", response_model=None)
    async def translate_async(
        body: AsyncTranslationRequest,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return await service.submit(body)
        except TranslateError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/translate/status/{job_id}", response_model=None)
    async def translation_status(
        job_id: str,
    ) -> dict[str, Any] | JSONResponse:
        body = await service.job_status(job_id)
        if body is None:
            return _envelope(404, "not_found", "unknown job")
        return body

    @router.post("/api/translate/nllb", response_model=None)
    async def translate_nllb(body: NllbRequest) -> dict[str, Any] | JSONResponse:
        try:
            return await service.translate_nllb(body.text, body.target_language)
        except TranslateError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    return router
```

Append to `src/omniscribe/plugins/translate/service.py` (the NLLB
singleton + the two remaining service methods; add `NllbRequest` to the
schemas import):

```python
# ---------------------------------------------------------------------------
# NLLB fast path
# ---------------------------------------------------------------------------

from omniscribe.core.translate.nllb import NLLBEngine  # noqa: E402  (move to top)

_NLLB_ENGINE: NLLBEngine | None = None


def _get_nllb_engine() -> NLLBEngine:
    # Module-level singleton: the engine lazily loads the transformers
    # pipeline on first use and caches it per instance. The old server
    # constructed a fresh engine per request, reloading the model every
    # call; the singleton keeps the contract while dropping the reload.
    global _NLLB_ENGINE
    if _NLLB_ENGINE is None:
        _NLLB_ENGINE = NLLBEngine()
    return _NLLB_ENGINE
```

And inside `TranslationServiceImpl` add:

```python
    async def translate_sync(self, request: TranslationRequest) -> str:
        return await translate_text(request, self._settings, store=self._store)

    async def translate_nllb(self, text: str, target_language: str) -> dict[str, Any]:
        if not text.strip():
            raise TranslateError(422, "bad_request", "'text' is required")
        engine = _get_nllb_engine()
        if not engine.is_available():
            raise TranslateError(
                503,
                "backend_unavailable",
                "NLLBEngine is not available. Install the 'nllb' extra: uv sync --extra nllb",
            )
        result = await engine.translate(text, target_language)
        return {
            "translated_text": result.text,
            "source_lang": result.source_lang,
            "target_lang": result.target_lang,
        }
```

Extend the `TranslationService` Protocol with `translate_sync` and
`translate_nllb`:

```python
    async def translate_sync(self, request: TranslationRequest) -> str: ...
    async def translate_nllb(self, text: str, target_language: str) -> dict[str, Any]: ...
```

Create `src/omniscribe/plugins/translate/plugin.py`:

```python
"""Translate plugin — mounts the translation routes over the JobQueue."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.jobs import JobQueue, JobRunner
from omniscribe.plugins.runtime import RuntimeService
from omniscribe.plugins.translate.routes import build_translate_router
from omniscribe.plugins.translate.service import TranslationService, TranslationServiceImpl


class TranslateSchema(BaseModel):
    """No configurable fields."""


class TranslatePlugin(Plugin):
    """Client-frozen translation surface: sync, async (JobQueue), NLLB."""

    Schema = TranslateSchema

    async def apply(self, ctx: Context) -> None:
        queue = ctx.inject(JobQueue)
        store = ctx.inject(ArtifactStore)
        runtime = ctx.inject(RuntimeService)
        service = TranslationServiceImpl(runtime.settings, queue, store)
        ctx.service(TranslationService, service)
        ctx.service(JobRunner, service.run_translate_job)
        ctx.mount_router(build_translate_router(service))


plugin = TranslatePlugin()
```

(Add `from omniscribe.plugins.artifacts import ArtifactStore` to the
plugin imports — the snippet above omits it; ruff will flag it, add it.)

Replace `src/omniscribe/plugins/translate/__init__.py`:

```python
"""Translate plugin — translation routes over the harness JobQueue."""

from omniscribe.plugins.translate.plugin import plugin

__all__ = ["plugin"]
```

If mypy flags Protocol/impl variance on `ctx.inject(JobQueue)` or the
`JobRunner` registration, mirror exactly how `plugins/ocr/plugin.py`
satisfies the checker — do not invent new typing machinery.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/routers/test_translate_routes.py -v`
Expected: all 14 tests PASS. The async-completion test relies on the real
queue worker started by the jobs plugin inside the TestClient lifespan
(same mechanism `tests/routers/test_process_async.py` uses).

- [ ] **Step 6: Fast gate + regression**

Run: `uv run pytest tests/plugins/test_translate_schemas.py tests/plugins/test_translate_service.py tests/routers/test_translate_routes.py -v`
Expected: 11 + 13 + 14 = all PASS
Run: `uv run pytest tests/routers tests/plugins tests/harness -x -q`
Expected: only failure allowed initially — the openapi snapshot
(`tests/openapi.json`) needs regeneration; follow the snapshot test's own
documented procedure, diff first, and verify additions-only (4 paths:
`/api/translate`, `/api/translate/async`, `/api/translate/status/{job_id}`,
`/api/translate/nllb` + their request schemas).
Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

- [ ] **Step 7: Commit**

```bash
git add src/omniscribe/plugins/translate/ tests/conftest.py tests/routers/test_translate_routes.py tests/openapi.json
git commit -m "feat(translate): client-frozen routes over JobQueue async dispatch"
```

---

### Task 5: Shipped cordis.yml + boot pins

**Files:**
- Modify: `src/omniscribe/resources/cordis.yml`
- Modify: `tests/plugins/test_boot_config.py`
- Test: `tests/harness/test_translate_boot.py` (create)

- [ ] **Step 1: Write the failing boot pins**

Create `tests/harness/test_translate_boot.py`:

```python
"""Boot tests for the translate plugin in the harness tree."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_translate_routes_survive_full_boot(api_client: TestClient) -> None:
    # FastAPI >=0.141 hides mounted plugin routes from app.routes —
    # assert against the public /openapi.json surface instead.
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    assert "/api/translate" in paths
    assert "/api/translate/async" in paths
    assert api_client.get("/api/health").status_code == 200


def test_translate_route_rejects_bad_body_off_real_tree(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/translate", json={"target_language": "French"})
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
```

- [ ] **Step 2: Update `tests/plugins/test_boot_config.py` (failing state)**

- Docstring line 1: "ten plugins" → "eleven plugins" (match the actual
  current wording — it says the tree mounts all N plugins).
- Rename `test_shipped_cordis_yml_declares_ten_rows_in_boot_order` →
  `..._eleven_rows_...` and insert `"translate"` between `"documents"`
  and `"ocr"` in the expected id list.
- Router count: `assert len(ctx.routes()) == 5` → `== 6`, comment gains
  translate.

Run: `uv run pytest tests/plugins/test_boot_config.py -v`
Expected: `test_shipped_cordis_yml_declares_eleven_rows_in_boot_order`
and `test_shipped_cordis_yml_mounts_full_service_tree` FAIL (shipped yml
unchanged yet).

- [ ] **Step 3: Add the shipped boot row**

In `src/omniscribe/resources/cordis.yml`, insert between the `documents`
and `ocr` rows:

```yaml
  - id: translate
    use: omniscribe.plugins.translate:plugin
```

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/plugins/test_boot_config.py tests/harness/test_translate_boot.py -v`
Expected: all PASS
Run: `uv run python -c "from fastapi.testclient import TestClient; from omniscribe.server import create_app; client = TestClient(create_app()); client.__enter__(); print(client.get('/api/health').status_code)"`
Expected: prints `200` (eleven plugins mount — the log line lists them)
Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

- [ ] **Step 5: Commit**

```bash
git add src/omniscribe/resources/cordis.yml tests/plugins/test_boot_config.py tests/harness/test_translate_boot.py
git commit -m "feat(translate): mount translate plugin as boot row 10 in shipped cordis.yml"
```

---

### Task 6: Pedantic-review ride-alongs (1.2, 1.6, 1.9, 1.10)

**Files:**
- Modify: `src/omniscribe/harness/loader.py:121-141`
- Modify: `src/omniscribe/plugins/jobs.py:207-213`
- Modify: `src/omniscribe/plugins/state_backend.py` (Protocol), `state_backend_memory.py:102-107`, `state_backend_sqlite.py:257+`
- Modify: `src/omniscribe/core/recall/text_layer.py:165`
- Modify: `src/omniscribe/core/ocr/chat_client.py:161`
- Test: `tests/harness/test_loader_env_overrides.py` (create)
- Test: `tests/plugins/test_jobs_plugin.py` (append)
- Test: `tests/core/recall/test_text_layer_recall.py` (append)

Full fast gate applies (harness + core paths).

- [ ] **Step 1: Write the failing tests**

Create `tests/harness/test_loader_env_overrides.py`:

```python
"""Regression: env overrides must match row ids case-insensitively.

Pedantic review 1.2 (2026-08-30): overrides were keyed by lowercased id
but matched against the row's original casing, so a capitalized row id
silently dropped every OMNISCRIBE_PLUGIN_<ID>__<FIELD> override.
"""

from __future__ import annotations

import pytest

from omniscribe.harness.loader import _apply_env_overrides, parse_rows


def test_env_override_matches_mixed_case_row_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    yml = tmp_path / "cordis.yml"
    yml.write_text(
        "plugins:\n"
        "  - id: Runtime\n"
        "    use: omniscribe.plugins.runtime:plugin\n"
        "    config:\n"
        "      cleanup_interval_seconds: 60\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNISCRIBE_PLUGIN_RUNTIME__CLEANUP_INTERVAL_SECONDS", "5")
    rows = parse_rows(yml.read_text(encoding="utf-8"))
    folded = _apply_env_overrides(rows)
    assert folded[0].config["cleanup_interval_seconds"] == "5"
```

Append to `tests/plugins/test_jobs_plugin.py` (this file already ships a
`_boot()` helper that boots state_backend + artifacts + jobs into a
`Context`, and imports `JobRecord`, `JobQueue`, and `state_backend as sb`
at the top — reuse them):

```python
async def test_shutdown_cancels_queued_jobs_beyond_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pedantic review 1.6: shutdown must cancel ALL queued jobs, not
    only the newest page (list_jobs orders created_at DESC)."""
    ctx = await _boot()
    try:
        queue = ctx.inject(JobQueue)
        backend = ctx.inject(sb.StateBackend)
        for i in range(5):
            await backend.upsert_job(JobRecord(job_id=f"j{i}", status="queued"))

        real_list = backend.list_jobs

        async def two_per_page(*, limit: int = 100, offset: int = 0):
            return await real_list(limit=2, offset=offset)

        monkeypatch.setattr(backend, "list_jobs", two_per_page)

        await queue.shutdown()

        records = await real_list(limit=100)
        assert {r.status for r in records} == {"cancelled"}
    finally:
        await ctx.dispose()
```

(The `limit=2` wrapper emulates the stranding: the pre-fix shutdown
issues a single `list_jobs(limit=1000)` call, sees only the first page of
2, and leaves 3 jobs queued — the test fails before the fix and passes
after pagination lands. `ctx.dispose()` re-runs `queue.shutdown`, which
is idempotent.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/harness/test_loader_env_overrides.py -v`
Expected: FAIL — `assert '5' == '60'` (override dropped)
Run: `uv run pytest tests/plugins/test_jobs_plugin.py -v -k beyond_one_page`
Expected: FAIL — 3 of the 5 seeded jobs remain `queued` after shutdown

- [ ] **Step 3: Fix 1.2 — loader case-insensitive lookup**

In `src/omniscribe/harness/loader.py:139-141`, replace:

```python
    return [
        replace(row, config={**row.config, **overrides[row.id]})
        if row.id in overrides
        else row
        for row in rows
    ]
```

with:

```python
    folded: list[PluginRow] = []
    for row in rows:
        row_overrides = overrides.get(row.id.lower())
        if row_overrides:
            row = replace(row, config={**row.config, **row_overrides})
        folded.append(row)
    return folded
```

- [ ] **Step 4: Fix 1.6 — paginate jobs shutdown**

Add `offset` to the `StateBackend.list_jobs` Protocol
(`src/omniscribe/plugins/state_backend.py`) and both implementations:

Protocol:

```python
    async def list_jobs(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[JobRecord]: ...
```

Memory impl (`state_backend_memory.py:102-107`):

```python
    async def list_jobs(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[JobRecord]:
        async with self._lock:
            ordered = sorted(
                self._jobs.values(), key=lambda r: r.created_at, reverse=True
            )
            return ordered[offset : offset + limit]
```

SQLite impl (`state_backend_sqlite.py`): change the SQL to
`... ORDER BY created_at DESC LIMIT ? OFFSET ?` with `(limit, offset)`
and add the `offset: int = 0` parameter to the signature.

`src/omniscribe/plugins/jobs.py` `shutdown` (replacing the
`list_jobs(limit=1000)` block):

```python
        # Pending work will never run now — mark it cancelled for callers.
        # Paginate until exhausted: list_jobs orders created_at DESC, so a
        # single bounded page would strand older queued rows forever
        # (pedantic review 1.6).
        offset = 0
        while True:
            page = await self._backend.list_jobs(limit=100, offset=offset)
            if not page:
                break
            offset += len(page)
            for record in page:
                if record.status == "queued":
                    await self._backend.upsert_job(
                        replace(record, status="cancelled", updated_at=time.time())
                    )
        self._payloads.clear()
```

- [ ] **Step 5: Fix 1.9 — text_layer explicit guard**

In `src/omniscribe/core/recall/text_layer.py:165`, replace
`assert self._doc is not None` with:

```python
        if self._doc is None:
            # Fail-open: an unopened/closed source contributes no boxes
            # (asserts vanish under `python -O` — pedantic review 1.9).
            return []
```

Append to `tests/core/recall/test_text_layer_recall.py`:

```python
def test_supplement_returns_empty_for_unopened_source() -> None:
    """Pedantic review 1.9: a source with no open document contributes
    no boxes instead of raising (fail-open contract; asserts vanish
    under `python -O`)."""
    source = PdfTextLayerRecall()
    assert source.supplement(0, []) == []
```

(`PdfTextLayerRecall.__init__` takes `options: TextLayerRecallOptions |
None = None`, so the no-arg construction works. This test is a contract
pin, not a red test — the public `supplement` entry guard already returns
`[]` before the assert is reachable; the 1.9 fix hardens the inner body
against future refactors and `python -O`.)

- [ ] **Step 6: Fix 1.10 — chat_client explicit guard**

In `src/omniscribe/core/ocr/chat_client.py:161`, replace
`assert last_exc is not None` with:

```python
        if last_exc is None:  # pragma: no cover - unreachable defensive guard
            raise RuntimeError("retry loop exited without capturing an exception")
```

(No dedicated test: the guard is unreachable by construction — the loop
always assigns `last_exc` on a raising first attempt. The existing
`tests/core/llm/` + `tests/core/ocr/` suites cover the loop behavior.)

- [ ] **Step 7: Run all affected suites**

Run: `uv run pytest tests/harness/test_loader_env_overrides.py tests/plugins/test_jobs_plugin.py tests/core/recall/test_text_layer.py -v`
Expected: all PASS
Run: `uv run pytest -m "not slow" -q`
Expected: no new failures (full fast tier — core paths touched)
Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src`
Expected: clean

- [ ] **Step 8: Commit**

```bash
git add src/omniscribe/harness/loader.py src/omniscribe/plugins/jobs.py src/omniscribe/plugins/state_backend.py src/omniscribe/plugins/state_backend_memory.py src/omniscribe/plugins/state_backend_sqlite.py src/omniscribe/core/recall/text_layer.py src/omniscribe/core/ocr/chat_client.py tests/harness/test_loader_env_overrides.py tests/plugins/test_jobs_plugin.py tests/core/recall/test_text_layer_recall.py
git commit -m "fix: pedantic review 1.2/1.6/1.9/1.10 — env-override case, jobs shutdown pagination, -O-safe guards"
```

---

### Task 7: Celery retirement (compose.yaml)

**Files:**
- Modify: `compose.yaml`

Note: the spec mentions `start_app.vbs`, but the file no longer exists in
the repo — retirement is compose-only. This closes five-domain audit
finding #2.

- [ ] **Step 1: Remove the Celery worker service**

In `compose.yaml`:
1. Delete the entire `worker:` service block (starts at the `  worker:` line,
   ends before the next top-level service/network key — includes its
   `deploy`, `security_opt`, `cap_drop`, the deferred-Celery NOTE comment,
   `command: ["celery", "-A", "omniscribe.api.tasks", ...]`, healthcheck
   referencing `omniscribe.api.celery_app`, and `profiles: ["async"]`).
2. Remove the `depends_on:` reference to `worker` if the `api` service
   lists it (grep `worker` across the file after deletion — zero matches
   expected except nothing).
3. Update the header comment block (lines ~5-16): drop the `worker`
   bullet and the `--profile async` usage line; replace with a note that
   async translation runs on the in-process harness JobQueue (no worker
   service).

- [ ] **Step 2: Verify**

Run: `grep -n "celery\|worker\|async" compose.yaml`
Expected: no Celery references remain; `async` may appear only in the new
JobQueue note.
Run: `docker compose config -q 2>/dev/null || echo "compose not validated (docker unavailable)"`
Expected: silent success or the honest "docker unavailable" echo — do not
fail the task on a machine without Docker.

- [ ] **Step 3: Commit**

```bash
git add compose.yaml
git commit -m "chore: retire broken Celery worker service — async translation rides the harness JobQueue"
```

---

### Task 8: Docs updates

**Files:**
- Modify: `AGENTS.md`
- Modify: `ARCHITECTURE.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/superpowers/specs/2026-08-30-translate-plugin-translation-routes-design.md` (three factual corrections)
- Verify only: `README.md`, `.env.example`

- [ ] **Step 1: AGENTS.md**

1. Boot-order table: `translate` row at 10 (`ocr` → 11):

```markdown
| 10 | `translate` | `plugins/translate/` | `TranslationService` + `TranslationJobRunner`; `/api/translate`, `/api/translate/async`, `/api/translate/status/{id}`, `/api/translate/nllb` |
```

2. "Deferred capabilities" paragraph: remove `translation` from the list
   (transcription / glossary-import remain).
3. "Web Notes" translation bullet: replace "its HTTP routes are deferred
   … not mounted yet" with the truth — the `translate` plugin serves
   `/api/translate` (sync single-shot) and `/api/translate/async`
   (tree-aware, JobQueue-dispatched) + status + NLLB; async rides the
   harness JobQueue (single worker), not Celery.
4. Known Tech Debt: update the Celery bullet ("true multi-worker /
   crash-safe dispatch needs a Celery task once the translation routes
   are rebuilt") — translation async now rides the harness queue; Celery
   is retired from compose and remains only a future multi-worker option.
5. `ALLOW_SSRF_LOCAL` line (~234, pedantic 1.1 docs reconciliation):
   reword to state the **code** default is `False` and the shipped
   `.env.example` enables `true` for local development.
6. Core Paths / Key Files: add a `plugins/translate/` row; update the
   plugins row count ("ten boot plugins" → "eleven boot plugins" with
   translate in the enumeration); "Last updated" stamps.

- [ ] **Step 2: ARCHITECTURE.md**

Add the `plugins/translate/` entry (plugin tree, directory
responsibilities, API surface rows for the four routes) matching the
documents-plugin entries' style; remove `/api/translate*` from any
deferred-routes paragraph; "Shared State" note: async results are stored
as token-bound text artifacts via `ArtifactStore`.

- [ ] **Step 3: CHANGELOG.md**

Under `## [Unreleased]` → `### Added`:

```markdown
- Translate plugin (`plugins/translate/`): rebuilt the deferred translation surface — `POST /api/translate` (sync single-shot), `POST /api/translate/async` (tree-aware, dispatched on the harness JobQueue), `GET /api/translate/status/{job_id}`, `POST /api/translate/nllb`. Translated documents are stored as token-bound text artifacts. The broken Celery worker service was retired from `compose.yaml` (async translation no longer uses Celery).
```

- [ ] **Step 4: Spec corrections** (keep the spec honest)

In `docs/superpowers/specs/2026-08-30-translate-plugin-translation-routes-design.md`:
1. "Verified environment facts": `TRANSLATION_SYSTEM_MESSAGE` — change
   "`core/translate/workflow.py`" to "`core/translate/nodes.py:42`".
2. NLLB bullet: add "the plugin holds the engine in a lazy module-level
   singleton (the old server re-instantiated per request — same contract,
   no model reload per call)".
3. Celery retirement section: note "`start_app.vbs` no longer exists in
   the repo; retirement is compose-only."

- [ ] **Step 5: README.md + .env.example verify**

Run: `grep -n "api/translate\|ALLOW_SSRF_LOCAL" README.md .env.example | head`
README: fix only now-false claims (its translation-feature claims become
true). `.env.example`: no change expected for `ALLOW_SSRF_LOCAL=true`
(that line is now correctly described by the AGENTS.md wording); remove
or annotate any `OMNISCRIBE_STATE_BACKEND=redis`-style claims only if
they contradict reality (they don't — the setting validates but the
backend rejects redis at apply time; leave as-is).

- [ ] **Step 6: Accuracy check + commit**

Verify every claim against code (boot order in the shipped yml, route
paths in routes.py, JobQueue-not-Celery in service.py). Run
`uv run pytest tests/scripts/test_repo_hygiene.py -q`.

```bash
git add AGENTS.md ARCHITECTURE.md CHANGELOG.md README.md docs/superpowers/specs/2026-08-30-translate-plugin-translation-routes-design.md
git commit -m "docs: translate plugin boot row, route surface, Celery retirement in AGENTS/ARCHITECTURE/CHANGELOG"
```

---

### Task 9: Full fast gate + end-to-end smoke

**Files:** none (verification only)

- [ ] **Step 1: Full fast gate**

Run: `uv run ruff check src tests && uv run ruff format src tests --check && uv run mypy src && uv run pytest -m "not slow"`
Expected: all green; no new failures beyond the pre-existing
environment-conditional skips.

- [ ] **Step 2: Boot smoke (real server)**

Run in one terminal: `uv run omniscribe-server --port 8000`
Then in another:

```bash
curl -s http://localhost:8000/api/health
curl -s -X POST http://localhost:8000/api/translate -H 'Content-Type: application/json' -d '{"target_language": "French"}'
```

Expected: health JSON; then
`{"error":"bad_request","detail":"'text' or 'text_artifact_id'/'text_artifact_token' is required"}`.
The boot log must list eleven plugins with `translate` between
`documents` and `ocr`. Stop the server.

- [ ] **Step 3: Flutter-side sanity (optional but recommended)**

Run the Flutter client against the server; on the Translation screen,
translate a small document (sync path with a real VLM endpoint), and flip
the async toggle to confirm submit → 2s polling → completion renders the
result. Without a VLM endpoint the screen must surface the `ai_error`
envelope as a typed error, not a crash.

---

## Self-review notes

- **Spec coverage:** four routes → Task 4; schemas → Task 1; sync re-home → Task 2; runner + status mapping → Task 3; conftest row → Task 4; shipped row + boot pins → Task 5; pedantic ride-alongs (1.2/1.6/1.9/1.10; 1.1 in Task 8) → Task 6 + Task 8; Celery retirement → Task 7; docs → Task 8; acceptance gates → Task 9. Async-unavailable 503 → Task 2/4 (submit path + test via monkeypatched `get_translation_app` — covered by the availability branch; the router test suite pins the 400/404 paths, and the 503 path is pinned at the service level by the submit implementation; if a dedicated router 503 test is desired, monkeypatch `service.get_translation_app` — noted as optional). Edge cases: empty artifact → `{"translated_text": ""}` (Task 2 verbatim); non-numeric page keys ignored (shared `load_pages`); entries-over-text glossary precedence (Task 3, verified); NLLB unknown language → `eng_Latn` fallback (core, verbatim); no token in status result (Task 3 + router test).
- **Deliberate deviations from the old server (documented in the spec):** status unknown-job → 404 (Celery's PENDING-for-anything unimplementable); sync glossary fields accepted-but-ignored (verbatim legacy); async accepts-and-ignores `text`/`channel_id` (client tolerance); NLLB engine singleton (no per-request model reload); results carry no artifact token (C-3/H-3).
- **Type consistency:** `TranslateError(status_code, error, detail)` defined Task 2, raised Tasks 2-3, consumed Task 4. `_TranslatePayload(submission_id, request)` defined and consumed in Task 3. `TranslationServiceImpl(settings, queue, store, max_buffered_jobs=...)` constructed in Task 3 tests and Task 4 plugin identically. `_get_nllb_engine` defined Task 4, monkeypatched in router tests. Status vocabulary (`PENDING`/`PROGRESS`/`SUCCESS`/`FAILURE`) identical in Task 3 implementation and tests.
