from __future__ import annotations

"""Coverage push for the extraction and translation router surface (audit P3-11).

Targets the routes that were at ~38% line coverage in the audit:

- ``POST /api/export/docx`` / ``docx-tree`` / ``html`` / ``blocktree``
- ``POST /api/translate/tree`` (artifact load, SSRF guard, config fallback)
- ``POST /api/translate/async`` + ``GET /api/translate/status/{job_id}``
- ``POST /api/glossary``
- ``POST /api/translate/nllb``

Artifact-backed routes run against a fresh :class:`TextArtifactStore`
swapped onto ``state`` (restored after each test), so no real OCR run
is needed.
"""

import json  # noqa: E402  (after module docstring; from __future__ first)
from pathlib import Path  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from omniscribe.api.routers import (  # noqa: E402
    artifacts,
    config,
    extraction,
    state,
    translation,
)
from omniscribe.api.services.artifacts import TextArtifactStore  # noqa: E402
from omniscribe.api.services.envelope import register_envelope_handlers  # noqa: E402
from omniscribe.api.services.security import SERVER_ERROR_MESSAGE  # noqa: E402
from omniscribe.api.services.tree_artifact import write_tree_atomic  # noqa: E402
from omniscribe.core.block_tree import from_pages_data  # noqa: E402
from omniscribe.core.glossary import Glossary  # noqa: E402
from omniscribe.core.nllb_engine import NLLBResult  # noqa: E402
from omniscribe.core.translation_config import AsyncTranslationUnavailable  # noqa: E402
from omniscribe.utils.security import SSRFCheckResult  # noqa: E402

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(config.router)
    app.include_router(translation.router)
    app.include_router(extraction.router)
    app.include_router(artifacts.router)  # owns /api/export/docx
    return TestClient(app)


@pytest.fixture()
def artifact_store(tmp_path: Path):
    """Swap a tmp-dir text artifact store onto ``state`` for the test."""
    original_text = state.text_artifacts
    original_metadata = state.metadata_artifacts
    store = TextArtifactStore(artifact_dir=tmp_path / "text")
    metadata_store = TextArtifactStore(artifact_dir=tmp_path / "metadata")
    state.text_artifacts = store
    state.metadata_artifacts = metadata_store
    try:
        yield store, metadata_store
    finally:
        state.text_artifacts = original_text
        state.metadata_artifacts = original_metadata


async def _make_tree_artifact(store: TextArtifactStore, lines: list[str]):
    """Create a text artifact plus its ``.tree.json`` sidecar."""
    handle = await store.create({0: lines})
    tree = from_pages_data({0: [([0.0, 0.0, 1.0, 0.1], text) for text in lines]})
    write_tree_atomic(tree, Path(handle.path + ".tree.json"))
    return handle


# ---------------------------------------------------------------------------
# /api/export/docx — markdown -> docx passthrough
# ---------------------------------------------------------------------------


def test_export_docx_route_returns_word_document():
    client = _client()
    response = client.post("/api/export/docx", json={"text": "# Title\n\nBody text."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(_DOCX_MEDIA_TYPE)
    assert "document.docx" in response.headers["content-disposition"]
    # .docx is a zip container — PK magic bytes.
    assert response.content[:2] == b"PK"


# ---------------------------------------------------------------------------
# /api/export/blocktree — tree sidecar, legacy fallback, token binding
# ---------------------------------------------------------------------------


def test_export_blocktree_reads_tree_sidecar(artifact_store):
    store, _ = artifact_store
    handle = _run(store.create({0: ["alpha", "beta"]}))
    tree = from_pages_data(
        {0: [([0.0, 0.0, 1.0, 0.1], "alpha"), ([0.0, 0.2, 1.0, 0.3], "beta")]}
    )
    write_tree_atomic(tree, Path(handle.path + ".tree.json"))

    client = _client()
    response = client.post(
        "/api/export/blocktree",
        json={
            "text_artifact_id": handle.artifact_id,
            "text_artifact_token": handle.token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    blocks = payload["pages"][0]["children"]
    assert [block["text"] for block in blocks] == ["alpha", "beta"]


def test_export_blocktree_falls_back_to_legacy_text_artifact(artifact_store):
    store, _ = artifact_store
    # No .tree.json sidecar — the pre-Phase-D shape.
    handle = _run(store.create({0: ["legacy line"]}))

    client = _client()
    response = client.post(
        "/api/export/blocktree",
        json={
            "text_artifact_id": handle.artifact_id,
            "text_artifact_token": handle.token,
        },
    )

    assert response.status_code == 200
    blocks = response.json()["pages"][0]["children"]
    assert len(blocks) == 1
    assert blocks[0]["text"] == "legacy line"


def test_export_blocktree_attaches_metadata_report(artifact_store):
    store, metadata_store = artifact_store
    handle = _run(store.create({0: ["body"]}))
    meta_handle = _run(metadata_store.create({0: ["report payload"]}))

    client = _client()
    response = client.post(
        "/api/export/blocktree",
        json={
            "text_artifact_id": handle.artifact_id,
            "text_artifact_token": handle.token,
            "metadata_artifact_id": meta_handle.artifact_id,
            "metadata_artifact_token": meta_handle.token,
        },
    )

    assert response.status_code == 200
    report = response.json()["metadata"]["processor_report"]
    assert report == {"0": ["report payload"]}


def test_export_blocktree_unknown_artifact_is_404(artifact_store):
    client = _client()
    response = client.post(
        "/api/export/blocktree",
        json={"text_artifact_id": "0" * 32, "text_artifact_token": "a" * 32},
    )

    assert response.status_code == 404


def test_export_blocktree_wrong_token_is_404(artifact_store):
    store, _ = artifact_store
    handle = _run(store.create({0: ["guarded"]}))

    client = _client()
    response = client.post(
        "/api/export/blocktree",
        json={
            "text_artifact_id": handle.artifact_id,
            "text_artifact_token": "b" * 43,  # well-formed but wrong
        },
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/export/html + /api/export/docx-tree — artifact-backed renderers
# ---------------------------------------------------------------------------


def test_export_html_renders_tree_blocks(artifact_store):
    store, _ = artifact_store
    handle = _run(_make_tree_artifact(store, ["unique-block-text"]))

    client = _client()
    response = client.post(
        "/api/export/html",
        json={
            "text_artifact_id": handle.artifact_id,
            "text_artifact_token": handle.token,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "unique-block-text" in response.text


def test_export_docx_tree_returns_word_document(artifact_store):
    store, _ = artifact_store
    handle = _run(_make_tree_artifact(store, ["structured paragraph"]))

    client = _client()
    response = client.post(
        "/api/export/docx-tree",
        json={
            "text_artifact_id": handle.artifact_id,
            "text_artifact_token": handle.token,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(_DOCX_MEDIA_TYPE)
    assert response.content[:2] == b"PK"


def test_export_html_unknown_artifact_is_404(artifact_store):
    client = _client()
    response = client.post(
        "/api/export/html",
        json={"text_artifact_id": "0" * 32, "text_artifact_token": "a" * 32},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/translate/tree — artifact load, SSRF guard, config fallback
# ---------------------------------------------------------------------------


def _tree_request(handle) -> dict:
    return {
        "text_artifact_id": handle.artifact_id,
        "text_artifact_token": handle.token,
        "target_language": "Spanish",
    }


def test_translate_tree_translates_artifact_blocks(artifact_store):
    store, _ = artifact_store
    handle = _run(store.create({0: ["hello world"]}))

    async def fake_call_llm(**kwargs):
        return "hola mundo"

    client = _client()
    with (
        patch(
            "omniscribe.api.routers.translation.is_ssrf_target",
            new=AsyncMock(
                return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1")
            ),
        ),
        patch("omniscribe.core.llm_client.call_llm", fake_call_llm),
    ):
        response = client.post("/api/translate/tree", json=_tree_request(handle))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["page_count"] == 1
    assert payload["block_count"] == 1
    assert payload["tree"]["pages"][0]["children"][0]["text"] == "hola mundo"


def test_translate_tree_missing_artifact_is_404(artifact_store):
    client = _client()
    response = client.post(
        "/api/translate/tree",
        json={
            "text_artifact_id": "0" * 32,
            "text_artifact_token": "a" * 32,
            "target_language": "Spanish",
        },
    )

    assert response.status_code == 404


def test_translate_tree_blocks_unsafe_request_api_base(artifact_store):
    """Regression for the precedence bug: a request-level ``api_base``
    must reach the SSRF guard (previously ``hasattr(state, "config")``
    made the whole branch dead code)."""
    store, _ = artifact_store
    handle = _run(store.create({0: ["hello"]}))

    request = _tree_request(handle)
    request["api_base"] = "http://internal.corp/v1"

    client = _client()
    with patch(
        "omniscribe.api.routers.translation.is_ssrf_target",
        new=AsyncMock(
            return_value=SSRFCheckResult(
                allowed=False, resolved_ip=None, reason="mock-blocked"
            )
        ),
    ):
        response = client.post("/api/translate/tree", json=request)

    assert response.status_code == 403
    assert response.json() == {
        "error": "ssrf_blocked",
        "detail": "URL targets a blocked address: api_base_blocked",
    }


def test_translate_tree_empty_artifact_short_circuits(artifact_store):
    store, _ = artifact_store
    handle = _run(store.create({}))

    client = _client()
    response = client.post("/api/translate/tree", json=_tree_request(handle))

    assert response.status_code == 200
    assert response.json() == {"status": "empty", "translated_pages": {}}


# ---------------------------------------------------------------------------
# /api/glossary — entries vs paired-lines text vs 422
# ---------------------------------------------------------------------------


def test_upload_glossary_accepts_entries():
    client = _client()
    response = client.post(
        "/api/glossary",
        json={"entries": [{"source": "ledger", "target": "libro mayor"}]},
    )

    assert response.status_code == 200
    parsed = Glossary.from_dict(response.json())
    assert [(e.source, e.target) for e in parsed.entries] == [("ledger", "libro mayor")]


def test_upload_glossary_parses_paired_lines_text():
    client = _client()
    response = client.post(
        "/api/glossary", json={"text": "invoice = factura\n# comment\n"}
    )

    assert response.status_code == 200
    parsed = Glossary.from_dict(response.json())
    assert [(e.source, e.target) for e in parsed.entries] == [("invoice", "factura")]


def test_upload_glossary_without_entries_or_text_is_422():
    client = _client()
    response = client.post("/api/glossary", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/translate/async — Celery dispatch
# ---------------------------------------------------------------------------


def test_translate_async_returns_job_id(artifact_store):
    class _Task:
        id = "celery-job-1"

    class _DelayedTask:
        @staticmethod
        def delay(*args, **kwargs):
            return _Task()

    client = _client()
    with patch("omniscribe.api.tasks.process_translation_task", _DelayedTask):
        response = client.post(
            "/api/translate/async",
            json={
                "text_artifact_id": "0" * 32,
                "text_artifact_token": "a" * 32,
                "target_language": "Spanish",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"job_id": "celery-job-1", "status": "Processing"}


def test_translate_async_503_when_extras_missing(artifact_store):
    class _UnavailableTask:
        @staticmethod
        def delay(*args, **kwargs):
            raise AsyncTranslationUnavailable("celery not installed")

    client = _client()
    with patch("omniscribe.api.tasks.process_translation_task", _UnavailableTask):
        response = client.post(
            "/api/translate/async",
            json={
                "text_artifact_id": "0" * 32,
                "text_artifact_token": "a" * 32,
                "target_language": "Spanish",
            },
        )

    assert response.status_code == 503
    assert "celery not installed" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/translate/status/{job_id} — PENDING / FAILURE / unavailable shapes
# ---------------------------------------------------------------------------


def test_translation_status_pending_shape():
    class _Task:
        state = "PENDING"
        info = None

    client = _client()
    with patch(
        "omniscribe.api.celery_app.celery_app.AsyncResult", return_value=_Task()
    ):
        response = client.get("/api/translate/status/job-9")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-9",
        "state": "PENDING",
        "status": "Pending...",
    }


def test_translation_status_failure_shape_is_stable():
    class _Task:
        state = "FAILURE"
        info = "Traceback: super-secret-stack-frame"

    client = _client()
    with patch(
        "omniscribe.api.celery_app.celery_app.AsyncResult", return_value=_Task()
    ):
        response = client.get("/api/translate/status/job-9")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "job_id": "job-9",
        "state": "FAILURE",
        "error": SERVER_ERROR_MESSAGE,
    }
    assert "super-secret-stack-frame" not in json.dumps(payload)


def test_translation_status_503_when_extras_missing():
    def _unavailable(job_id):
        raise AsyncTranslationUnavailable("celery not installed")

    client = _client()
    with patch("omniscribe.api.celery_app.celery_app.AsyncResult", _unavailable):
        response = client.get("/api/translate/status/job-9")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /api/translate/nllb — validation + engine availability
# ---------------------------------------------------------------------------


def test_translate_nllb_requires_text():
    client = _client()
    response = client.post("/api/translate/nllb", json={"text": "   "})

    assert response.status_code == 422


def test_translate_nllb_503_when_engine_unavailable():
    class _StubEngine:
        def is_available(self) -> bool:
            return False

        async def translate(self, text, target_language):  # pragma: no cover
            raise AssertionError("translate must not run when unavailable")

    client = _client()
    with patch("omniscribe.core.nllb_engine.NLLBEngine", _StubEngine):
        response = client.post(
            "/api/translate/nllb",
            json={"text": "hello", "target_language": "French"},
        )

    assert response.status_code == 503
    assert "nllb" in response.json()["detail"].lower()


def test_translate_nllb_success_shape():
    class _StubEngine:
        def is_available(self) -> bool:
            return True

        async def translate(self, text, target_language):
            return NLLBResult(
                text="bonjour", source_lang="eng_Latn", target_lang="fra_Latn"
            )

    client = _client()
    with patch("omniscribe.core.nllb_engine.NLLBEngine", _StubEngine):
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a store coroutine on a private loop (TestClient owns its own)."""
    import asyncio

    return asyncio.run(coro)
