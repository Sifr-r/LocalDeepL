from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import (
    artifacts,
    config,
    extraction,
    jobs,
    ocr,
    state,
    translation,
    websocket,
)
from omniscribe.api.routers.config import _config
from omniscribe.api.routers.ocr import _run_ocr_pipeline
from omniscribe.api.services.artifacts import TextArtifactStore
from omniscribe.api.services.ocr_settings import resolve_process_settings
from omniscribe.api.services.security import (
    UploadValidationError,
    api_error_response,
    save_validated_upload,
)
from omniscribe.core.document import DocumentResult
from omniscribe.utils.security import is_ssrf_target


class _AsyncUpload:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(config.router)
    app.include_router(translation.router)
    app.include_router(extraction.router)
    app.include_router(ocr.router)
    app.include_router(websocket.router)
    app.include_router(jobs.router)
    app.include_router(artifacts.router)
    return TestClient(app)


def _public_dns(host: str, port, *args, **kwargs):
    if host == "api.openai.com":
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.3.161", 443))]
    raise socket.gaierror(-2, "Name or service not known")


def _process_form() -> dict[str, str]:
    return {
        "client_id": "same-client",
        "api_base": "http://api.openai.com/v1",
        "api_key": "test-key",
        "model": "openai/test-model",
        "pipeline_mode": "hybrid",
        "dpi": "200",
        "concurrency": "1",
        "dense_mode": "auto",
        "dense_threshold": "60",
        "refine": "true",
        "max_image_dim": "1024",
        "self_correction": "false",
        "binarize": "false",
        "dual_engine": "false",
        "spellcheck": "none",
        "cross_page": "false",
        "preprocess_pages": "false",
        "orientation_detection": "false",
        "deskew": "false",
        "denoise": "false",
        "normalize_contrast": "false",
        "crop_cleanup": "false",
        "quality_routing": "false",
    }


def _process_form_kwargs() -> dict[str, str]:
    """Same as :func:`_process_form` but expressed as kwargs for ``resolve_process_settings``.

    Tests that drive :func:`omniscribe.api.routers.ocr._run_ocr_pipeline`
    directly (rather than via :class:`fastapi.testclient.TestClient`) need
    a ``ProcessSettings`` instance, which means going through
    :func:`omniscribe.api.services.ocr_settings.resolve_process_settings`.
    That resolver accepts the same fields as ``_process_form`` but spread
    as keyword arguments.
    """
    form = _process_form()
    # ``client_id`` is a FastAPI form field, not a ProcessSettings field;
    # it is accepted but ignored by the resolver.
    form.pop("client_id", None)
    return form


def _pdf_upload() -> tuple[str, bytes, str]:
    return ("input.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")


def test_ssrf_fails_closed_and_requires_explicit_local_allowance():
    import asyncio

    with patch.dict(os.environ, {}, clear=True):
        with patch("omniscribe.utils.security.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.side_effect = _public_dns
            assert asyncio.run(is_ssrf_target("http://api.openai.com/v1")) is False
            assert asyncio.run(is_ssrf_target("localhost:1234/v1")) is True
            assert asyncio.run(is_ssrf_target("ftp://api.openai.com/v1")) is True
            assert asyncio.run(is_ssrf_target(None)) is True

    with patch.dict(os.environ, {}, clear=True):
        with patch("omniscribe.utils.security.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.side_effect = socket.gaierror(-2, "Name or service not known")
            assert (
                asyncio.run(is_ssrf_target("http://does-not-resolve.example/v1"))
                is True
            )

    with patch.dict(os.environ, {"ALLOW_SSRF_LOCAL": "true"}, clear=True):
        assert asyncio.run(is_ssrf_target("http://127.0.0.1:1234/v1")) is False
        assert asyncio.run(is_ssrf_target("http://metadata.google.internal/v1")) is True


def test_config_update_rejects_string_booleans_and_local_api_base():
    client = _api_client()

    response = client.post("/api/config", json={"refine": "false"})
    assert response.status_code == 422

    with patch.dict(os.environ, {}, clear=True):
        response = client.post(
            "/api/config", json={"api_base": "http://127.0.0.1:1234/v1"}
        )
    assert response.status_code == 403
    assert "127.0.0.1" not in response.json()["error"]


def test_upload_validation_uses_streaming_limit_and_content_signature():
    async def run_checks():
        with pytest.raises(UploadValidationError) as too_large:
            await save_validated_upload(
                _AsyncUpload(b"%PDF-1.4\n" + b"x" * 16),  # type: ignore[arg-type]
                max_bytes=8,
            )
        assert too_large.value.status_code == 413

        with pytest.raises(UploadValidationError) as bad_type:
            await save_validated_upload(_AsyncUpload(b"not a pdf"), max_bytes=1024)  # type: ignore[arg-type]
        assert bad_type.value.status_code == 415

    asyncio.run(run_checks())


def test_process_issues_opaque_text_artifact_ids_and_prevents_client_id_lookup(
    tmp_path,
):
    class DummyPipeline:
        def __init__(self, *args, **kwargs):
            self.last_failed_pages: list[int] = []

        async def run(self, input_path, output_path, **kwargs):
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["safe text"]}

    client = _api_client()

    with (
        patch("omniscribe.utils.security.socket.getaddrinfo", side_effect=_public_dns),
        patch(
            "omniscribe.api.services.ocr_pipeline_factory.OCRPipeline", DummyPipeline
        ),
        patch(
            "omniscribe.api.services.ocr_pipeline_factory.OCRProcessor",
            lambda *args, **kwargs: SimpleNamespace(),
        ),
        patch(
            "omniscribe.api.services.ocr_pipeline_factory.HybridAligner",
            lambda *args, **kwargs: SimpleNamespace(),
        ),
        patch(
            "omniscribe.api.services.ocr_pipeline_factory.PDFHandler",
            lambda *args, **kwargs: SimpleNamespace(),
        ),
    ):
        first = client.post(
            "/process", data=_process_form(), files={"file": _pdf_upload()}
        )
        second = client.post(
            "/process", data=_process_form(), files={"file": _pdf_upload()}
        )

    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.headers["X-Text-Artifact-Id"]
    second_id = second.headers["X-Text-Artifact-Id"]
    first_token = first.headers["X-Text-Artifact-Token"]
    second_token = second.headers["X-Text-Artifact-Token"]
    assert first_id != second_id
    assert first_token != second_token
    assert len(first_id) == 32

    assert (
        client.get(
            "/text/same-client",
            headers={"Authorization": f"Bearer {first_token}"},
        ).status_code
        == 404
    )
    assert client.get(f"/text/{first_id}").status_code == 403
    assert (
        client.get(
            f"/text/{first_id}",
            headers={"Authorization": f"Bearer {second_token}"},
        ).status_code
        == 403
    )
    text_response = client.get(
        f"/text/{first_id}",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert text_response.status_code == 200
    assert text_response.json() == {"0": ["safe text"]}


def test_text_artifact_retrieval_expires_router_store(tmp_path):
    clock = SimpleNamespace(value=0.0)

    def now() -> float:
        return clock.value

    original_store = state.text_artifacts
    try:
        store = TextArtifactStore(ttl_seconds=5, clock=now, artifact_dir=tmp_path)
        state.text_artifacts = store
        handle = asyncio.run(store.create({0: ["expiring text"]}))
        client = _api_client()

        response = client.get(
            f"/text/{handle.artifact_id}",
            headers={"Authorization": f"Bearer {handle.token}"},
        )
        assert response.status_code == 200

        clock.value = 6.0
        response = client.get(
            f"/text/{handle.artifact_id}",
            headers={"Authorization": f"Bearer {handle.token}"},
        )
        assert response.status_code == 404
        assert not Path(handle.path).exists()
    finally:
        state.text_artifacts = original_store


def test_process_omits_document_metadata_artifact_when_no_report(tmp_path: Path):
    class DummyPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = []

        async def run(self, input_path, output_path, **kwargs):
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["safe text"]}

    original_text_store = state.text_artifacts
    original_metadata_store = state.metadata_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    state.metadata_artifacts = TextArtifactStore(artifact_dir=tmp_path / "metadata")

    try:
        client = _api_client()
        with (
            patch(
                "omniscribe.utils.security.socket.getaddrinfo",
                side_effect=_public_dns,
            ),
            patch(
                "omniscribe.api.services.ocr_pipeline_factory.OCRPipeline",
                DummyPipeline,
            ),
            patch("omniscribe.api.services.ocr_pipeline_factory.HybridAligner"),
            patch("omniscribe.api.services.ocr_pipeline_factory.PDFHandler"),
        ):
            response = client.post(
                "/process", data=_process_form(), files={"file": _pdf_upload()}
            )

        assert response.status_code == 200
        assert "X-Text-Artifact-Id" in response.headers
        assert "X-Document-Metadata-Artifact-Id" not in response.headers
        assert "X-Document-Metadata-Artifact-Token" not in response.headers
    finally:
        state.text_artifacts = original_text_store
        state.metadata_artifacts = original_metadata_store


def test_process_exposes_token_bound_document_metadata_artifact(tmp_path: Path):
    class DummyPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = []

        async def run(self, input_path, output_path, **kwargs):
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            document = DocumentResult.from_pages_data(
                {0: [([0.1, 0.1, 0.4, 0.2], "Invoice")]}
            )
            page = document.pages[0]
            block = page.blocks[0]
            block.reading_order = 0
            block.kind = "heading"
            block.metadata["structure"] = {
                "kind": "heading",
                "confidence": 0.9,
                "signals": ["test_heading"],
            }
            block.metadata["section"] = {
                "section_index": 0,
                "title": "Invoice",
                "heading_page_index": 0,
                "heading_block_index": 0,
            }
            page.metadata["quality"] = {
                "block_count": 1,
                "text_char_count": 7,
                "text_density": 70.0,
                "findings": [],
            }
            page.metadata["structure"] = {
                "block_kinds": {"heading": 1},
                "has_key_values": False,
                "has_tables": False,
            }
            page.metadata["sections"] = {
                "section_count": 1,
                "active_section": "Invoice",
                "headings": [block.metadata["section"]],
            }
            self.last_document_result = document
            return {0: ["safe text"]}

    original_text_store = state.text_artifacts
    original_metadata_store = state.metadata_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    state.metadata_artifacts = TextArtifactStore(artifact_dir=tmp_path / "metadata")

    try:
        client = _api_client()
        with (
            patch(
                "omniscribe.utils.security.socket.getaddrinfo",
                side_effect=_public_dns,
            ),
            patch(
                "omniscribe.api.services.ocr_pipeline_factory.OCRPipeline",
                DummyPipeline,
            ),
            patch("omniscribe.api.services.ocr_pipeline_factory.HybridAligner"),
            patch("omniscribe.api.services.ocr_pipeline_factory.PDFHandler"),
        ):
            response = client.post(
                "/process", data=_process_form(), files={"file": _pdf_upload()}
            )

        assert response.status_code == 200
        artifact_id = response.headers["X-Document-Metadata-Artifact-Id"]
        token = response.headers["X-Document-Metadata-Artifact-Token"]

        denied = client.get(
            f"/metadata/{artifact_id}",
            headers={"Authorization": f"Bearer {'A' * 43}"},
        )
        assert denied.status_code == 403

        metadata_response = client.get(
            f"/metadata/{artifact_id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert metadata_response.status_code == 200
        payload = metadata_response.json()

        assert payload["summary"]["processors"] == [
            "quality_analysis",
            "reading_order",
            "section_analysis",
            "structure_analysis",
        ]
        assert payload["pages"][0]["metadata"]["quality"]["block_count"] == 1
        block_report = payload["pages"][0]["blocks"][0]
        assert block_report["reading_order"] == 0
        assert block_report["metadata"]["structure"]["kind"] == "heading"
        assert "text" not in block_report
    finally:
        state.text_artifacts = original_text_store
        state.metadata_artifacts = original_metadata_store


def test_document_export_artifact_is_token_bound(tmp_path: Path):
    original_text_store = state.text_artifacts
    original_export_store = state.export_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    state.export_artifacts = TextArtifactStore(artifact_dir=tmp_path / "export")

    try:
        handle = asyncio.run(state.text_artifacts.create({0: ["alpha", "beta"]}))
        client = _api_client()
        response = client.post(
            "/api/export/document",
            json={
                "text_artifact_id": handle.artifact_id,
                "text_artifact_token": handle.token,
                "export_format": "markdown",
            },
        )
        assert response.status_code == 200
        body = response.json()

        denied = client.get(
            f"/export/{body['artifact_id']}",
            headers={"Authorization": f"Bearer {'A' * 43}"},
        )
        assert denied.status_code == 403

        exported = client.get(
            f"/export/{body['artifact_id']}",
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        assert exported.status_code == 200
        assert exported.text.startswith("## Page 1")
    finally:
        state.text_artifacts = original_text_store
        state.export_artifacts = original_export_store


def test_progress_session_uses_token_bound_websocket_channels():
    client = _api_client()

    session_response = client.post(
        "/api/progress/session", json={"client_id": "visible-client"}
    )
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["channel_id"] != "visible-client"
    assert session["session_token"] != "visible-client"

    with client.websocket_connect(
        f"/ws/{session['channel_id']}?token={session['session_token']}"
    ):
        assert websocket.manager.is_authorized(
            session["channel_id"], session["session_token"]
        )
        assert not websocket.manager.is_authorized(session["channel_id"], "A" * 32)


def test_process_surfaces_partial_page_failures_in_headers_and_history(tmp_path: Path):
    """A page whose OCR call raises must be reported in the response
    ``X-Failed-Pages`` header and the job-history record. The job
    status stays ``"complete"`` — the pipeline degrades gracefully and
    writes a PDF even with bad pages.

    The WebSocket frame shape is covered separately by
    ``test_websocket_manager_emits_warning_flag``; here we just confirm
    the router wires the partial-failure signal through.
    """

    class _FailingDummyPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = [1]  # 0-indexed page 1 fails

        async def run(self, input_path, output_path, **kwargs):
            on_warning = kwargs.get("on_warning")
            if on_warning is not None:
                await on_warning(1, RuntimeError("simulated page 1 failure"))
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["page0"], 1: [], 2: ["page2"]}

    client = _api_client()

    with (
        patch("omniscribe.utils.security.socket.getaddrinfo", side_effect=_public_dns),
        patch(
            "omniscribe.api.services.ocr_pipeline_factory.OCRPipeline",
            _FailingDummyPipeline,
        ),
        patch("omniscribe.api.services.ocr_pipeline_factory.HybridAligner"),
        patch("omniscribe.api.services.ocr_pipeline_factory.PDFHandler"),
    ):
        response = client.post(
            "/process",
            data=_process_form(),
            files={"file": _pdf_upload()},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Failed-Pages") == "1"

    # The job record reflects the partial failure.
    jobs = client.get("/api/jobs").json()
    assert jobs, "no job history recorded"
    latest = jobs[0]
    assert latest["status"] == "complete"
    assert latest["failed_pages"] == [1]


def test_websocket_manager_emits_warning_flag():
    """The ConnectionManager.send_progress path must serialize the
    ``warning`` flag in the WebSocket frame so the UI can render a
    partial-failure indicator without parsing the message text."""
    from omniscribe.api.routers.websocket import ConnectionManager

    sent_frames: list[dict] = []

    class _StubWS:
        async def accept(self):
            pass

        async def send_json(self, payload):
            sent_frames.append(payload)

    async def _drive():
        manager = ConnectionManager()
        await manager.connect(_StubWS(), "abcd" * 8, "efgh" * 8)  # 32-char tokens
        await manager.send_progress("abcd" * 8, "all good", 50, stage="ocr")
        await manager.send_progress(
            "abcd" * 8,
            "OCR failed for page 7: TimeoutError",
            0,
            stage="ocr",
            warning=True,
        )

    asyncio.run(_drive())

    assert sent_frames[0] == {
        "status": "all good",
        "percent": 50,
        "stage": "ocr",
    }
    assert sent_frames[1] == {
        "status": "OCR failed for page 7: TimeoutError",
        "percent": 0,
        "stage": "ocr",
        "warning": True,
    }


def test_translate_error_response_does_not_expose_internal_exception():
    async def fail_completion(*args, **kwargs):
        raise RuntimeError("secret-api-key leaked by provider")

    client = _api_client()
    with (
        patch("omniscribe.utils.security.socket.getaddrinfo", side_effect=_public_dns),
        patch("omniscribe.api.services.ai.call_llm", fail_completion),
    ):
        response = client.post(
            "/api/translate",
            json={
                "text": "hello",
                "target_language": "Spanish",
                "api_base": "http://api.openai.com/v1",
                "model": "openai/test-model",
                "api_key": "secret-api-key",
            },
        )

    assert response.status_code == 500
    payload = json.dumps(response.json())
    assert "secret-api-key" not in payload
    assert "provider" not in payload


def test_static_js_has_no_html_injection_sinks():
    static_js = Path("src/omniscribe/static/js")
    for path in static_js.glob("*.js"):
        source = path.read_text(encoding="utf-8")
        assert "innerHTML" not in source
        assert "insertAdjacentHTML" not in source
        assert "outerHTML" not in source


# ---------------------------------------------------------------------------
# Phase 2: API security hardening
# ---------------------------------------------------------------------------


def test_security_settings_parses_environment_defaults(monkeypatch):
    """Empty env ⇒ personal/local posture: no auth, no CORS, no rate limit.

    The default upload cap is the 10 GB minimum the size-limits tests
    pin (see ``test_size_limits.py``); we verify the *contract* of the
    parser here, not the specific Megabyte value.
    """
    from omniscribe.api.services.security_config import (
        DEFAULT_MAX_UPLOAD_MB,
        SecuritySettings,
    )

    monkeypatch.delenv("OMNISCRIBE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OMNISCRIBE_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("OMNISCRIBE_MAX_UPLOAD_MB", raising=False)
    monkeypatch.delenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", raising=False)

    settings = SecuritySettings.from_env()
    assert settings.auth_token is None
    assert settings.auth_enabled is False
    assert settings.cors_origins == []
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    assert settings.rate_limit_per_minute is None
    assert settings.rate_limit_enabled is False


def test_security_settings_cors_parses_csv_and_trims(monkeypatch):
    from omniscribe.api.services.security_config import SecuritySettings

    monkeypatch.setenv(
        "OMNISCRIBE_CORS_ORIGINS",
        "https://app.example.com, https://admin.example.com ,, ",
    )
    settings = SecuritySettings.from_env()
    assert settings.cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_security_settings_rate_limit_zero_disables(monkeypatch):
    from omniscribe.api.services.security_config import SecuritySettings

    monkeypatch.setenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", "0")
    settings = SecuritySettings.from_env()
    assert settings.rate_limit_per_minute is None
    assert settings.rate_limit_enabled is False


def test_security_settings_max_upload_clamps(monkeypatch):
    from omniscribe.api.services.security_config import (
        ABSOLUTE_MAX_UPLOAD_MB,
        SecuritySettings,
    )

    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "999999")
    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == ABSOLUTE_MAX_UPLOAD_MB * 1024 * 1024

    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "0")
    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == 1 * 1024 * 1024


def test_security_settings_invalid_ints_fall_back_to_default(monkeypatch):
    from omniscribe.api.services.security_config import (
        DEFAULT_MAX_UPLOAD_MB,
        SecuritySettings,
    )

    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "not-a-number")
    monkeypatch.setenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", "garbage")
    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    assert settings.rate_limit_per_minute is None


def _create_app_with_security(monkeypatch, **env):
    """Build the full app via `create_app()` so middleware is wired."""
    from omniscribe import server

    for key in (
        "OMNISCRIBE_AUTH_TOKEN",
        "OMNISCRIBE_CORS_ORIGINS",
        "OMNISCRIBE_MAX_UPLOAD_MB",
        "OMNISCRIBE_RATE_LIMIT_PER_MIN",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    app = server.create_app()
    return app


def test_bearer_auth_required_when_token_set(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_AUTH_TOKEN="s3cret")
    client = TestClient(app)

    unauthorized = client.get("/api/config")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"] == "Unauthorized"

    wrong = client.get("/api/config", headers={"Authorization": "Bearer wrong-token"})
    assert wrong.status_code == 401

    right = client.get(
        "/api/config",
        headers={"Authorization": "Bearer s3cret"},
    )
    assert right.status_code == 200


def test_bearer_auth_accepts_lowercase_scheme(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_AUTH_TOKEN="token")
    client = TestClient(app)
    response = client.get("/api/config", headers={"Authorization": "bearer token"})
    assert response.status_code == 200


def test_max_upload_size_rejects_oversized_content_length(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_MAX_UPLOAD_MB="1")
    client = TestClient(app)
    response = client.post(
        "/api/config",
        content=b"x" * (2 * 1024 * 1024),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    payload = response.json()
    assert payload["limit_bytes"] == str(1 * 1024 * 1024)


def test_max_upload_size_passes_undersized(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_MAX_UPLOAD_MB="10")
    client = TestClient(app)
    response = client.get("/api/config")
    assert response.status_code == 200


def test_rate_limit_rejects_after_cap(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_RATE_LIMIT_PER_MIN="3")
    client = TestClient(app)

    for _ in range(3):
        assert client.get("/api/config").status_code == 200

    assert client.get("/api/config").status_code == 429
    assert client.get("/api/config").status_code == 429


def test_rate_limit_isolates_per_client_ip(monkeypatch):
    """Two different client IPs share independent buckets.

    TestClient doesn't let us spoof the address easily, so the second
    bucket is driven by a freshly-constructed middleware instance on
    the same client; the underlying deque-by-key isolation is what
    the property is exercising.
    """
    from omniscribe.api.services.security_middleware import RateLimitMiddleware

    fake_app_calls: list[str] = []

    async def passthrough(scope, receive, send):
        fake_app_calls.append(scope.get("client", ("unknown",))[0])

    rm = RateLimitMiddleware(passthrough, per_minute=2)

    async def drive(client_ip: str) -> None:
        rm._hits.clear()
        captured: list[bool] = []

        async def fake_receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        class _CaptureSend:
            def __init__(self):
                self.status: int | None = None

            async def __call__(self, msg):
                if msg["type"] == "http.response.start":
                    self.status = msg["status"]

        for _ in range(3):
            cap = _CaptureSend()
            await rm(
                {
                    "type": "http",
                    "client": (client_ip, 1234),
                    "headers": [],
                    "method": "GET",
                    "path": "/x",
                    "raw_path": b"/x",
                    "query_string": b"",
                    "scheme": "http",
                    "server": ("test", 80),
                },
                fake_receive,
                cap,
            )
            captured.append(cap.status)

        assert captured == [None, None, 429]

    asyncio.run(drive("10.0.0.1"))
    asyncio.run(drive("10.0.0.2"))


def test_namespaced_ocr_and_artifact_aliases_are_registered():
    client = _api_client()

    assert client.post("/process").status_code == 422
    assert client.post("/api/process").status_code == 422
    assert client.post("/process/async").status_code == 422
    assert client.post("/api/process/async").status_code == 422
    assert client.get("/process/status/missing").status_code == 404
    assert client.get("/api/process/status/missing").status_code == 404

    def _extract_paths(routes):
        paths = set()
        for route in routes:
            if hasattr(route, "path") and route.path:
                paths.add(route.path)
            if hasattr(route, "routes"):
                paths.update(_extract_paths(route.routes))
            elif hasattr(route, "original_router") and hasattr(
                route.original_router, "routes"
            ):
                paths.update(_extract_paths(route.original_router.routes))
            elif hasattr(route, "router") and hasattr(route.router, "routes"):
                paths.update(_extract_paths(route.router.routes))
            elif hasattr(route, "app") and hasattr(route.app, "routes"):
                paths.update(_extract_paths(route.app.routes))
        return paths

    route_paths = _extract_paths(client.app.routes)
    assert {
        "/api/text/{artifact_id}",
        "/api/artifacts/text/{artifact_id}",
        "/api/metadata/{artifact_id}",
        "/api/artifacts/metadata/{artifact_id}",
        "/api/export/{artifact_id}",
        "/api/artifacts/export/{artifact_id}",
    } <= route_paths


def test_namespaced_text_artifact_aliases_share_legacy_handler():
    handle = asyncio.run(state.text_artifacts.create({1: ["alias text"]}))
    client = _api_client()
    headers = {"Authorization": f"Bearer {handle.token}"}
    try:
        legacy = client.get(f"/text/{handle.artifact_id}", headers=headers)
        canonical = client.get(f"/api/text/{handle.artifact_id}", headers=headers)
        frontend = client.get(
            f"/api/artifacts/text/{handle.artifact_id}", headers=headers
        )
        assert (
            legacy.status_code == canonical.status_code == frontend.status_code == 200
        )
        assert legacy.json() == canonical.json() == frontend.json()
    finally:
        asyncio.run(state.text_artifacts.delete(handle.artifact_id, handle.token))


def test_cancel_unknown_background_ocr_job_returns_404():
    response = _api_client().post("/api/jobs/missing/cancel")
    assert response.status_code == 404
    assert response.json() == {"error": "Job not found"}


def test_api_error_response_envelope_shape():
    # Without detail: opaque 500-style — no extra keys.
    response = api_error_response(500, "Server exploded.")
    assert response.status_code == 500
    assert response.body == b'{"error":"Server exploded."}'

    # With detail: structured extra context follows ``error``.
    response = api_error_response(422, "Bad shape.", detail={"field": "missing"})
    assert response.status_code == 422
    assert response.body == b'{"error":"Bad shape.","detail":{"field":"missing"}}'

    # Status code is preserved through the helper.
    response = api_error_response(403, "Forbidden.")
    assert response.status_code == 403
    assert response.body == b'{"error":"Forbidden."}'


# ---------------------------------------------------------------------------
# Refactor §3.1 — `POST /api/process` must not block the event loop
# ---------------------------------------------------------------------------
#
# The route handler dispatches ``pipeline.run`` to a worker thread via
# :func:`asyncio.to_thread` and bridges the async progress callbacks to the
# captured main loop via :func:`asyncio.run_coroutine_threadsafe`. The
# load-bearing property: ``pipeline.run`` must execute on a thread that is
# NOT the asyncio loop thread (``threading.get_ident()`` at the test's main
# thread == asyncio loop thread when driven by ``asyncio.run``). If the
# to_thread wrapper regresses, this test fails.


def test_run_ocr_pipeline_dispatches_to_thread_pool_worker(tmp_path: Path):
    """``_run_ocr_pipeline`` runs ``pipeline.run`` on a worker thread.

    Without the to_thread wrapper, ``pipeline.run`` would execute on the
    asyncio loop's thread (= the test's main thread when driven via
    ``asyncio.run``), pinning the event loop for the full pipeline
    duration. With the wrapper, the pipeline runs in a separate thread
    and the main loop is released for other work. The test records
    ``threading.get_ident()`` from inside the stubbed ``pipeline.run``
    and from inside the progress callback; both should equal the worker
    thread id, not the test's main thread id.

    See refactor §3.1 in
    ``docs/superpowers/specs/deep_refactor_report.md``.
    """
    import asyncio
    import threading

    main_thread_id = threading.get_ident()
    pipeline_thread_id: list[int] = []
    progress_thread_id: list[int] = []

    class _ThreadProbingPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = []

        async def run(
            self, input_path, output_path, *, progress=None, on_warning=None, **_
        ):
            pipeline_thread_id.append(threading.get_ident())
            if progress is not None:
                # The bridge callback runs synchronously in the worker
                # thread before returning the fire-and-forget awaitable,
                # so this ``threading.get_ident()`` is the worker thread.
                progress_thread_id.append(threading.get_ident())
                await progress("init", 0, 1, "starting")
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["page0"]}

    input_path = str(tmp_path / "input.pdf")
    output_path = str(tmp_path / "output.pdf")
    Path(input_path).write_bytes(b"%PDF-1.4\n%%EOF\n")

    original_text_store = state.text_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=None,
            **_process_form_kwargs(),
        )

        with (
            patch("omniscribe.api.routers.ocr.build_pipeline") as mock_build,
            patch("omniscribe.api.routers.ocr.verify_backend_model"),
        ):
            pipeline = _ThreadProbingPipeline()
            mock_build.return_value = (pipeline, None)

            asyncio.run(
                _run_ocr_pipeline(
                    settings=settings,
                    input_path=input_path,
                    output_path=output_path,
                    progress_target=None,
                )
            )
    finally:
        state.text_artifacts = original_text_store

    assert pipeline_thread_id, "pipeline.run was not called"
    assert pipeline_thread_id[0] != main_thread_id, (
        "pipeline.run executed on the asyncio loop thread — "
        "the to_thread wrapper regressed; the event loop will block "
        "for the full pipeline duration"
    )
    # The progress callback fires from the same thread as pipeline.run
    # (both run inside the worker thread's asyncio.run).
    assert progress_thread_id, "progress callback was not invoked"
    assert progress_thread_id[0] == pipeline_thread_id[0], (
        "progress callback ran on a different thread than pipeline.run — "
        "the bridge is no longer co-located with the pipeline execution"
    )


def test_run_ocr_pipeline_progress_bridge_does_not_block_worker_thread(
    tmp_path: Path,
):
    """The progress bridge must be fire-and-forget, not block on the main loop.

    Each progress frame would normally take some time on the main loop
    (WebSocket send). If the bridge were implemented as ``await
    run_coroutine_threadsafe(...).asyncio.Future`` (block-on-result), the
    worker thread would serialize on the main loop and the
    event-loop-release benefit would be lost. The test stubs the
    connection manager's ``send_progress`` to sleep 0.1s on each call.
    A block-on-result bridge would cause the 3-frame pipeline to take
    ≥ 0.3s; a fire-and-forget bridge completes in well under 0.3s
    because the worker thread schedules and continues.

    See refactor §3.1 in
    ``docs/superpowers/specs/deep_refactor_report.md``.
    """
    import asyncio
    import time

    class _CountingPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = []

        async def run(
            self, input_path, output_path, *, progress=None, on_warning=None, **_
        ):
            if progress is not None:
                for i in range(3):
                    await progress("ocr", i, 3, f"page {i}")
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["page0"]}

    input_path = str(tmp_path / "input.pdf")
    output_path = str(tmp_path / "output.pdf")
    Path(input_path).write_bytes(b"%PDF-1.4\n%%EOF\n")

    # Stub manager.send_progress to simulate a slow WebSocket send (0.1s).
    # With a fire-and-forget bridge, the worker thread schedules the
    # coroutine and continues without waiting. With a block-on-result
    # bridge, the worker thread would serialize on these sleeps.
    class _SlowConnectionManager:
        async def send_progress(self, *args, **kwargs):
            await asyncio.sleep(0.1)

        async def send_block(self, *args, **kwargs):
            return None

        async def send_page_complete(self, *args, **kwargs):
            return None

        async def send_block_retry(self, *args, **kwargs):
            return None

        async def send_block_revised(self, *args, **kwargs):
            return None

        async def send_quality_summary(self, *args, **kwargs):
            return None

    original_manager = ocr.manager
    ocr.manager = _SlowConnectionManager()  # type: ignore[assignment]
    original_text_store = state.text_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=None,
            **_process_form_kwargs(),
        )

        with (
            patch("omniscribe.api.routers.ocr.build_pipeline") as mock_build,
            patch("omniscribe.api.routers.ocr.verify_backend_model"),
        ):
            pipeline = _CountingPipeline()
            mock_build.return_value = (pipeline, None)

            started = time.monotonic()
            asyncio.run(
                _run_ocr_pipeline(
                    settings=settings,
                    input_path=input_path,
                    output_path=output_path,
                    progress_target=None,
                )
            )
            elapsed = time.monotonic() - started
    finally:
        ocr.manager = original_manager  # type: ignore[assignment]
        state.text_artifacts = original_text_store

    # 3 progress frames × 0.1s = 0.3s if the bridge is fire-and-forget.
    # Block-on-result would push elapsed time to ≥ 0.3s per call, so we
    # assert the elapsed time is well under 0.5s (which would still
    # allow for some serial dispatch overhead).
    assert elapsed < 0.5, (
        f"pipeline.run took {elapsed:.3f}s; the progress bridge appears "
        "to be blocking on the main loop instead of fire-and-forget. "
        "Check that the bridge returns an immediately-resolving "
        "awaitable rather than awaiting the concurrent.futures.Future."
    )
