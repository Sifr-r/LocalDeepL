"""Token-bound artifact stores: opaque ids, TTL, metadata, exports.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from omniscribe.api.routers import state
from omniscribe.api.services.artifacts import TextArtifactStore
from omniscribe.core.document import DocumentResult
from tests.api._safety_helpers import (
    _api_client,
    _pdf_upload,
    _process_form,
    _public_dns,
)


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
            "omniscribe.api.services.ocr_pipeline_factory.get_shared_hybrid_aligner",
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
            patch(
                "omniscribe.api.services.ocr_pipeline_factory.get_shared_hybrid_aligner"
            ),
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
            patch(
                "omniscribe.api.services.ocr_pipeline_factory.get_shared_hybrid_aligner"
            ),
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
