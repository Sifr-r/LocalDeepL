"""Router contract tests for the documents plugin export family.

Contract source: the Flutter client (`feature_repository.dart`,
`api_constants.dart`, `feature_models.dart`) plus the recovered
pre-harness tests (commit `e6b7b89^`).
"""

from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient

from omniscribe.plugins.state_backend import StateBackend

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _seed_artifact(
    api_client: TestClient,
    *,
    blob: bytes,
    content_type: str = "application/json",
) -> tuple[str, str]:
    """Seed one artifact through the app's StateBackend (no events emitted)."""
    backend = api_client.app.state.context.inject(StateBackend)
    artifact_id = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    asyncio.run(
        backend.put_artifact(
            id=artifact_id,
            token=token,
            owner_job_id="",
            content_type=content_type,
            blob=blob,
            ttl_seconds=3600,
        )
    )
    return artifact_id, token


def _seed_text_artifact(
    api_client: TestClient, pages: dict[str, str]
) -> tuple[str, str]:
    return _seed_artifact(
        api_client,
        blob=json.dumps(pages).encode("utf-8"),
        content_type="application/json",
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_documents_plugin_is_mounted(api_client: TestClient) -> None:
    # FastAPI >= 0.141 keeps include_router() results wrapped in private
    # _IncludedRouter objects inside app.routes, so the stable public
    # surface for path assertions is the OpenAPI schema.
    paths = set(api_client.get("/openapi.json").json()["paths"])
    assert "/api/extract" in paths
    assert "/api/export/document" in paths
    assert "/api/export/docx" in paths
    assert "/api/export/html" in paths
    assert "/api/export/docx-tree" in paths
    assert "/api/export/blocktree" in paths
    assert "/api/text/{artifact_id}" in paths
    assert "/api/metadata/{artifact_id}" in paths
    assert "/api/export/{artifact_id}" in paths


def test_export_document_markdown_round_trip(api_client: TestClient) -> None:
    artifact_id, token = _seed_text_artifact(
        api_client, {"0": "hello\nworld", "1": "next"}
    )

    response = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": artifact_id,
            "text_artifact_token": token,
            "export_format": "markdown",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"artifact_id", "token", "format"}
    assert body["format"] == "markdown"
    assert len(body["artifact_id"]) == 32

    fetched = api_client.get(
        f"/api/export/{body['artifact_id']}", headers=_bearer(body["token"])
    )
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("text/markdown")
    assert fetched.text.startswith("## Page 1\n\nhello\nworld")


def test_export_document_fetch_requires_bearer(api_client: TestClient) -> None:
    artifact_id, token = _seed_text_artifact(api_client, {"0": "hello"})
    created = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": artifact_id,
            "text_artifact_token": token,
            "export_format": "text",
        },
    ).json()

    no_token = api_client.get(f"/api/export/{created['artifact_id']}")
    assert no_token.status_code == 403
    assert no_token.json()["error"] == "forbidden"

    wrong_token = api_client.get(
        f"/api/export/{created['artifact_id']}", headers=_bearer("t" * 43)
    )
    assert wrong_token.status_code == 404
    assert wrong_token.json()["error"] == "not_found"


def test_export_document_unknown_artifact_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": "0" * 32,
            "text_artifact_token": "t" * 43,
            "export_format": "json",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_export_document_json_payload_shape(api_client: TestClient) -> None:
    artifact_id, token = _seed_text_artifact(api_client, {"0": "a\nb"})

    response = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": artifact_id,
            "text_artifact_token": token,
            "export_format": "json",
        },
    )
    assert response.status_code == 200
    exported_id = response.json()["artifact_id"]
    exported_token = response.json()["token"]
    fetched = api_client.get(
        f"/api/export/{exported_id}", headers=_bearer(exported_token)
    )
    payload: dict[str, Any] = fetched.json()
    assert payload["pages"] == [{"page_index": 0, "lines": ["a", "b"], "text": "a\nb"}]
    assert payload["metadata"] is None


def test_export_document_with_metadata_artifact(api_client: TestClient) -> None:
    artifact_id, token = _seed_text_artifact(api_client, {"0": "a"})
    meta_id, meta_token = _seed_artifact(
        api_client, blob=json.dumps({"quality": "ok"}).encode("utf-8")
    )

    response = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": artifact_id,
            "text_artifact_token": token,
            "export_format": "json",
            "metadata_artifact_id": meta_id,
            "metadata_artifact_token": meta_token,
        },
    )
    assert response.status_code == 200
    exported_id = response.json()["artifact_id"]
    exported_token = response.json()["token"]
    payload = api_client.get(
        f"/api/export/{exported_id}", headers=_bearer(exported_token)
    ).json()
    assert payload["metadata"] == {"quality": "ok"}


def test_export_document_unknown_metadata_404(api_client: TestClient) -> None:
    artifact_id, token = _seed_text_artifact(api_client, {"0": "a"})
    response = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": artifact_id,
            "text_artifact_token": token,
            "export_format": "json",
            "metadata_artifact_id": "0" * 32,
            "metadata_artifact_token": "t" * 43,
        },
    )
    assert response.status_code == 404


def test_export_docx_post_inline_bytes(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/export/docx", json={"text": "# Title\n\nBody text."}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(DOCX_MEDIA_TYPE)
    assert "document.docx" in response.headers["content-disposition"]
    assert response.content[:2] == b"PK"


def test_export_docx_get_query_param(api_client: TestClient) -> None:
    # The Flutter ExportModal calls getBytes with query parameters.
    response = api_client.get("/api/export/docx", params={"text": "# Title\n\nBody."})
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert "document.docx" in response.headers["content-disposition"]


def test_export_docx_empty_text_is_lenient(api_client: TestClient) -> None:
    response = api_client.post("/api/export/docx", json={"text": ""})
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


def test_get_text_artifact_token_semantics(api_client: TestClient) -> None:
    artifact_id, token = _seed_text_artifact(api_client, {"0": "hello\nworld"})

    ok = api_client.get(f"/api/text/{artifact_id}", headers=_bearer(token))
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/json")
    assert ok.json() == {"0": "hello\nworld"}

    missing = api_client.get(f"/api/text/{artifact_id}")
    assert missing.status_code == 403
    assert missing.json()["error"] == "forbidden"

    unknown = api_client.get(f"/api/text/{'0' * 32}", headers=_bearer(token))
    assert unknown.status_code == 404


def test_get_metadata_artifact_token_semantics(api_client: TestClient) -> None:
    meta_id, meta_token = _seed_artifact(
        api_client, blob=json.dumps({"page_count": 1}).encode("utf-8")
    )

    ok = api_client.get(f"/api/metadata/{meta_id}", headers=_bearer(meta_token))
    assert ok.status_code == 200
    assert ok.json() == {"page_count": 1}

    missing = api_client.get(f"/api/metadata/{meta_id}")
    assert missing.status_code == 403


def test_validation_rejects_malformed_artifact_ids(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/export/document",
        json={
            "text_artifact_id": "short",
            "text_artifact_token": "t" * 43,
            "export_format": "json",
        },
    )
    assert response.status_code == 422
