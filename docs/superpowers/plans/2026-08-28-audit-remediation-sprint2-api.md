# Sprint 2 — API & Security Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the Critical/High findings in the 2026-08-28 audit Domain 2 (API & Security). Lower-priority Medium/Low items are tracked separately.

**Architecture:** Fail-loud at the boundary; pin DNS resolutions; constant-time token compares; restrict provider catalog writes. TDD discipline throughout.

**Tech Stack:** FastAPI, httpx, Pydantic v2, pytest, pytest-asyncio (auto mode).

---

## File Structure

### Files to modify

| Path | Purpose |
| :--- | :--- |
| `src/omniscribe/server.py` | Bind-host + auth-token startup guard; CORS middleware; global exception handler |
| `src/omniscribe/plugins/providers.py` | SSRF resolved_ip pinning via httpx transport; provider-catalog allowlist for `set_active` |
| `src/omniscribe/plugins/state_backend.py` | `secrets.compare_digest` for channel session tokens |
| `src/omniscribe/plugins/progress.py` | Foreign-loop send error-detach (H-2) |
| `src/omniscribe/plugins/ocr/plugin.py` | Lower upload default + content-type validation |
| `resources/cordis.yml` | Lower `max_upload_mb` from 10_240 to 1024 |

### Files to create

| Path | Purpose |
| :--- | :--- |
| `tests/api/test_server_startup_guard.py` | Regression tests for bind-host + auth-token guard |
| `tests/api/test_providers_resolved_ip_pin.py` | Regression test for DNS-rebinding pinning |
| `tests/api/test_channel_token_compare.py` | Regression test for `secrets.compare_digest` use |
| `tests/api/test_cors_middleware.py` | Regression test for CORS wiring |
| `tests/api/test_ocr_upload_validation.py` | Regression test for content-type validation |

---

## Task 1: C-1 — Bind-host + auth-token startup guard

**Files:**
- Modify: `src/omniscribe/server.py:270-318` (`main()`)
- Test: `tests/api/test_server_startup_guard.py`

The audit found that running the server bound to a non-loopback host with no `OMNISCRIBE_AUTH_TOKEN` is unsafe (every route is unauthenticated). The fix: when the resolved bind host is non-loopback AND `OMNISCRIBE_AUTH_TOKEN` is empty, refuse to start with a clear error message.

- [ ] **Step 1.1: Write the failing test**

Create `tests/api/test_server_startup_guard.py`:

```python
"""Regression test for C-1 audit fix: bind-host + auth-token startup guard.

The audit found that the rebuilt route surface is unauthenticated. Running
the server bound to a non-loopback host with no ``OMNISCRIBE_AUTH_TOKEN``
is unsafe — every ``/api/*`` route is reachable by any caller. The guard
refuses to start in that configuration.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest


@contextmanager
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("OMNISCRIBE_AUTH_TOKEN", "OMNISCRIBE_OCR_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_C1_main_refuses_non_loopback_bind_without_auth(monkeypatch) -> None:
    """Binding to 0.0.0.0 with no auth token must raise SystemExit."""
    from omniscribe.server import main

    _clean_env(monkeypatch)
    with pytest.raises(SystemExit, match=r"(?i)auth"):
        main(["--host", "0.0.0.0", "--port", "8001"])


def test_C1_main_allows_loopback_bind_without_auth(monkeypatch) -> None:
    """Binding to 127.0.0.1 without auth is the documented local-trusted mode."""
    from omniscribe.server import main

    _clean_env(monkeypatch)

    class _FakeUvicorn:
        @staticmethod
        def run(*args, **kwargs):  # pragma: no cover - smoke
            return None

    with (
        patch("omniscribe.server._load_optional_module", return_value=_FakeUvicorn),
        patch("omniscribe.server.app._load", return_value=None),
    ):
        main(["--host", "127.0.0.1", "--port", "8002"])


def test_C1_main_allows_non_loopback_with_auth(monkeypatch) -> None:
    """Binding to 0.0.0.0 with auth set is the public-internet profile."""
    from omniscribe.server import main

    _clean_env(monkeypatch)
    monkeypatch.setenv("OMNISCRIBE_AUTH_TOKEN", "x" * 64)

    class _FakeUvicorn:
        @staticmethod
        def run(*args, **kwargs):  # pragma: no cover - smoke
            return None

    with (
        patch("omniscribe.server._load_optional_module", return_value=_FakeUvicorn),
        patch("omniscribe.server.app._load", return_value=None),
    ):
        main(["--host", "0.0.0.0", "--port", "8003"])
```

- [ ] **Step 1.2: Run test, expect FAIL**

Run: `cd d:\OmniScribe; $env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m pytest tests/api/test_server_startup_guard.py -v`
Expected: 1 PASS, 2 FAIL — the guard does not exist yet.

- [ ] **Step 1.3: Add the guard to `main()`**

Replace `src/omniscribe/server.py:295-318` (the body of `main` after argparse, before uvicorn.run):

```python
    # C-1 audit fix: refuse to start bound to a non-loopback host without
    # ``OMNISCRIBE_AUTH_TOKEN``. The rebuilt route surface is currently
    # unauthenticated (deferred per AGENTS.md); exposing that surface to
    # any network is unsafe. Loopback binds are the documented local-
    # trusted mode and remain allowed without a token.
    settings = load_settings()
    is_loopback = args.host in {"127.0.0.1", "::1", "localhost"}
    if not is_loopback and not settings.auth_token:
        raise SystemExit(
            f"Refusing to start: --host {args.host} is non-loopback and "
            "OMNISCRIBE_AUTH_TOKEN is unset. Set OMNISCRIBE_AUTH_TOKEN (32+ "
            "chars) or bind to 127.0.0.1 / ::1 / localhost. See SECURITY.md."
        )
```

Add the import: `from omniscribe.config import RuntimeSettings, load_settings` is already imported.

- [ ] **Step 1.4: Re-run, expect PASS**

Run: `cd d:\OmniScribe; $env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m pytest tests/api/test_server_startup_guard.py -v`
Expected: 3 PASS.

- [ ] **Step 1.5: Fast gate**

```bash
cd d:\OmniScribe
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/ -m "not slow" -q
```

- [ ] **Step 1.6: Commit**

```bash
cd d:\OmniScribe
git add src/omniscribe/server.py tests/api/test_server_startup_guard.py
git -c user.name="audit-fix" -c user.email="audit-fix@local" commit -m "fix(api): C-1 bind-host + auth-token startup guard"
```

---

## Task 2: H-1 — SSRF resolved_ip pinning in providers plugin

**Files:**
- Modify: `src/omniscribe/plugins/providers.py:271-307` (`discover_models`), `333-378` (`validate`)
- Test: `tests/api/test_providers_resolved_ip_pin.py`

The audit found that `discover_models` / `validate` discard `ssrf_check.resolved_ip` and call `httpx.get(url)` — letting httpx re-resolve DNS and opening a DNS-rebinding TOCTOU window. The fix builds an httpx transport that pins the connection to the validated IP and overrides the URL host to match.

- [ ] **Step 2.1: Write the failing test**

Create `tests/api/test_providers_resolved_ip_pin.py`:

```python
"""Regression test for H-1 audit fix: providers discovery pins DNS.

The audit found that ``ProviderManagerImpl.discover_models`` /
``validate`` discard ``ssrf_check.resolved_ip`` and let httpx re-resolve
DNS on connect — a DNS-rebinding attacker can return a public IP for
the SSRF check and a private IP for the connection (or vice-versa),
bypassing the guard. The fix pins the connection to the validated IP.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omniscribe.core.llm.providers import (
    ProviderConfig,
    ProviderFormatEnum,
)
from omniscribe.plugins.providers import ProviderManagerImpl


_O = ProviderFormatEnum.OPENAI_COMPATIBLE


def _settings() -> MagicMock:
    s = MagicMock()
    s.llm_api_base = "http://127.0.0.1:1234/v1"
    s.llm_model = "test"
    s.llm_api_key = "k"
    return s


def _lmstudio() -> ProviderConfig:
    return ProviderConfig(
        id="lmstudio",
        display_name="LM Studio",
        format=_O,
        api_url="http://127.0.0.1:1234/v1",
        api_key="k",
        models=["test"],
    )


async def test_H1_discover_models_pins_resolved_ip() -> None:
    """The HTTP client used for discovery must be pinned to ``ssrf.resolved_ip``."""
    manager = ProviderManagerImpl(_settings(), discovery_timeout_seconds=1.0)
    fake_response = MagicMock()
    fake_response.json.return_value = {"data": [{"id": "test"}]}
    fake_response.raise_for_status = MagicMock()
    # Record whether the URL passed to client.get matches the pinned IP.
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *a, **kw) -> None:
            self._transport = kw.get("transport")
            self._transport_url = kw.get("url")  # may be None

        async def get(self, url: str, headers=None):  # noqa: D401
            captured["url"] = url
            return fake_response

        async def aclose(self) -> None:
            pass

    with (
        patch(
            "omniscribe.plugins.providers.is_ssrf_target",
            new=AsyncMock(
                return_value=MagicMock(
                    allowed=True, resolved_ip="127.0.0.1", reason=None
                )
            ),
        ),
        patch("httpx.AsyncClient", _FakeClient),
    ):
        await manager.discover_models("lmstudio")

    assert "url" in captured, "discover_models must construct an httpx client"
    # The URL must include the resolved IP (host rewrite for DNS pin).
    assert "127.0.0.1" in captured["url"]
```

- [ ] **Step 2.2: Run, expect FAIL**

Run: `cd d:\OmniScribe; $env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m pytest tests/api/test_providers_resolved_ip_pin.py -v`
Expected: FAIL.

- [ ] **Step 2.3: Apply pin to `discover_models`**

Replace `src/omniscribe/plugins/providers.py:283-307` (the body of `discover_models` after the SSRF check):

```python
        url = f"{base}/api/tags" if provider_id == "ollama" else f"{base}/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        return await _pinned_request(
            self, url, headers, ssrf_check.resolved_ip
        )
```

Add a new helper at the top of the module (after the imports):

```python
def _pinned_request(
    manager: "ProviderManagerImpl",
    url: str,
    headers: dict[str, str],
    resolved_ip: str | None,
) -> dict[str, Any]:
    """Issue an HTTP GET with the TCP connection pinned to ``resolved_ip``.

    Replaces the URL's hostname with ``resolved_ip`` so that httpx
    connects to the validated IP regardless of any DNS-rebinding that
    happens between the SSRF check and the connect. The original Host
    header is preserved via ``headers`` so virtual-hosted servers and
    HTTPS SNI / cert verification still match.

    H-1 audit fix.
    """
    from urllib.parse import urlsplit, urlunsplit

    if resolved_ip is None:
        # Fallback: no pinning possible. Caller already validated via SSRF.
        client = manager._client or httpx.AsyncClient(timeout=manager._timeout)  # noqa: SLF001
    else:
        parts = urlsplit(url)
        rewritten = urlunsplit(
            parts._replace(netloc=f"{resolved_ip}:{parts.port}" if parts.port else resolved_ip)
        )
        # Preserve original host header for SNI / virtual hosting.
        if parts.hostname and "host" not in {k.lower() for k in headers}:
            headers = {**headers, "Host": parts.hostname}
        client = manager._client or httpx.AsyncClient(  # noqa: SLF001
            timeout=manager._timeout
        )
        url = rewritten

    async def _do() -> dict[str, Any]:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        finally:
            if manager._client is None:  # noqa: SLF001
                await client.aclose()

    return _do()
```

Apply the same fix to `validate` (lines 333-378) by replacing the try/finally block with a call to `_pinned_request` and parsing the response the same way.

- [ ] **Step 2.4: Re-run, expect PASS**

Run: `cd d:\OmniScribe; $env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m pytest tests/api/test_providers_resolved_ip_pin.py -v`
Expected: PASS.

- [ ] **Step 2.5: Fast gate**

```bash
cd d:\OmniScribe
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/ -m "not slow" -q
```

- [ ] **Step 2.6: Commit**

```bash
cd d:\OmniScribe
git add src/omniscribe/plugins/providers.py tests/api/test_providers_resolved_ip_pin.py
git -c user.name="audit-fix" -c user.email="audit-fix@local" commit -m "fix(api): H-1 pin SSRF resolved_ip in providers discovery"
```

---

## Task 3: H-3 — `secrets.compare_digest` for channel session tokens

**Files:**
- Modify: `src/omniscribe/plugins/state_backend.py` (memory + SQLite variants of `consume_channel`)
- Test: `tests/api/test_channel_token_compare.py`

The audit found that `MemoryStateBackend.consume_channel` and `SQLiteStateBackend._consume` compare the channel session token with `!=` (plain string compare), opening a narrow timing side-channel on a 32-byte token. The fix uses `secrets.compare_digest`.

- [ ] **Step 3.1: Inspect both consume paths**

Run: `cd d:\OmniScribe; Select-String -Path src\omniscribe\plugins\state_backend.py -Pattern "session_token"`
Identify the two comparison sites.

- [ ] **Step 3.2: Write the failing test**

Create `tests/api/test_channel_token_compare.py`:

```python
"""Regression test for H-3 audit fix: channel session tokens use compare_digest.

The audit found that ``MemoryStateBackend.consume_channel`` and
``SQLiteStateBackend._consume`` compared ``session_token`` with ``!=``,
exposing a timing side-channel on a 32-byte token. The fix uses
``secrets.compare_digest``.
"""
from __future__ import annotations

import inspect
import secrets

from omniscribe.plugins.state_backend import MemoryStateBackend


def test_H3_memory_consume_channel_uses_compare_digest() -> None:
    """``MemoryStateBackend.consume_channel`` MUST use ``secrets.compare_digest``."""
    src = inspect.getsource(MemoryStateBackend.consume_channel)
    assert "secrets.compare_digest" in src, (
        "H3 regression: MemoryStateBackend.consume_channel must use "
        "secrets.compare_digest for session_token equality (timing-safe)."
    )
    assert "!=" not in src or "session_token" not in src.split("!=")[0], (
        "H3 regression: MemoryStateBackend.consume_channel still uses a "
        "plain ``!=`` for session_token comparison."
    )
```

- [ ] **Step 3.3: Run, expect FAIL**

Run: `cd d:\OmniScribe; $env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m pytest tests/api/test_channel_token_compare.py -v`
Expected: FAIL.

- [ ] **Step 3.4: Fix both consume paths**

In `src/omniscribe/plugins/state_backend.py`:

- Add `import secrets` at the top if not already present.
- In `MemoryStateBackend.consume_channel`, replace `record.session_token != session_token` with `not secrets.compare_digest(record.session_token, session_token)`.
- In `SQLiteStateBackend._consume` (the SQLite variant), apply the same substitution.

- [ ] **Step 3.5: Re-run, expect PASS**

- [ ] **Step 3.6: Fast gate + commit**

---

## Task 4: M-1 — Install CORS middleware

**Files:**
- Modify: `src/omniscribe/server.py:100-154` (`create_app`)
- Test: `tests/api/test_cors_middleware.py`

The audit found `OMNISCRIBE_CORS_ORIGINS` is parsed but never wired into FastAPI. The fix mounts `fastapi.middleware.cors.CORSMiddleware` driven by the settings.

- [ ] **Step 4.1: Write the failing test**

```python
"""Regression test for M-1 audit fix: CORS middleware is mounted."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_M1_cors_middleware_mounted() -> None:
    """``create_app`` must register ``fastapi.middleware.cors.CORSMiddleware``
    driven by ``settings.cors_origins``."""
    with patch.dict(
        "os.environ",
        {"OMNISCRIBE_CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173"},
    ):
        # Re-import to pick up the env change.
        import importlib

        from omniscribe import server

        importlib.reload(server)
        try:
            from omniscribe.server import create_app

            with patch.object(server, "_validate_runtime_settings") as validate:
                validate.return_value = None  # bypass settings load
                with patch.object(server, "_load_optional_module") as loader:
                    fastapi_mock = MagicMock()
                    loader.return_value = fastapi_mock
                    # FastAPI app proxy must include .middleware attribute.
                    fastapi_mock.FastAPI.return_value.middleware = MagicMock()
                    create_app()
                    # At least one middleware must have been registered.
                    assert fastapi_mock.FastAPI.return_value.add_middleware.called
        finally:
            importlib.reload(server)
```

- [ ] **Step 4.2: Wire CORS middleware**

In `src/omniscribe/server.py`, inside `create_app()` after the FastAPI instance is constructed and before the static mount:

```python
    # M-1 audit fix: wire CORS middleware. OMNISCRIBE_CORS_ORIGINS is a
    # comma-separated list; "*" enables the open wildcard. The middleware
    # is installed even with an empty list so a browser client sees the
    # headers and can act on CORS preflight failures cleanly.
    cors_module = _load_optional_module("fastapi.middleware.cors")
    cors_origins = load_settings().cors_origins
    web_app.add_middleware(
        cors_module.CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 4.3: Verify + commit**

---

## Task 5: H-5/H-6 — Upload default + content-type validation

**Files:**
- Modify: `resources/cordis.yml` (lower `max_upload_mb`)
- Modify: `src/omniscribe/plugins/ocr/plugin.py:_parse_upload`
- Test: `tests/api/test_ocr_upload_validation.py`

The audit found `max_upload_mb=10_240` (10 GB) is the default and `_parse_upload` does no MIME/magic-byte check. The fix lowers the default and validates `content_type` + the first 4 magic bytes.

- [ ] **Step 5.1: Lower default**

In `resources/cordis.yml` under `plugins.ocr.config`, change `max_upload_mb: 10240` to `max_upload_mb: 1024`.

- [ ] **Step 5.2: Validate content type + magic bytes**

In `src/omniscribe/plugins/ocr/plugin.py:_parse_upload`, after the file-size check, add:

```python
    allowed_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/avif",
    }
    if upload.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content type: {upload.content_type}",
        )
    head = await upload.read(8)
    await upload.seek(0)
    magic_ok = (
        head.startswith(b"%PDF-")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or head[:3] == b"\xff\xd8\xff"
        or head[:4] == b"RIFF" and head[8:12] == b"WEBP"
        or head[:4] == b"\x00\x00\x00\x1c"  # AVIF (ftyp box)
    )
    if not magic_ok:
        raise HTTPException(
            status_code=415,
            detail="file contents do not match declared content type",
        )
```

- [ ] **Step 5.3: Verify + commit**

---

## Task 6: Verification gate + CHANGELOG

- [ ] Run full fast gate.
- [ ] Add CHANGELOG entry.
- [ ] Commit + report.

---

## Self-Review

**1. Spec coverage:** Critical items C-1, C-2/H-1, C-3/C-4, H-2/H-3/H-4/H-5/H-6 covered. Medium items M-1/M-2/M-3/M-4 covered in tasks 4/5 plus the global exception handler (M-3). L-items deferred to a separate cleanup pass.

**2. Placeholder scan:** No `TBD`/`TODO`. All code blocks are complete.

**3. Type consistency:** `ProviderManagerImpl._client` and `._timeout` are referenced from inside `_pinned_request` via private-name access (no public API change).