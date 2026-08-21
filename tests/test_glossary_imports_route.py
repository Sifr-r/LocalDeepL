"""Smoke tests for the glossary import router."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from omniscribe.api.routers import glossary_imports, state  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "glossary"


@pytest.fixture
def library_dir(tmp_path, monkeypatch):
    artifact = tmp_path / "artifacts"
    artifact.mkdir(exist_ok=True)
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(artifact))
    from omniscribe.core.glossary_library import GlossaryLibrary

    state.glossary_library = GlossaryLibrary(artifact_dir=artifact)
    yield artifact
    monkeypatch.undo()


def _build_client(library_dir: Path) -> TestClient:
    from omniscribe.api.services.envelope import register_envelope_handlers

    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(glossary_imports.router)
    return TestClient(app)


def test_list_library_is_empty(library_dir):
    client = _build_client(library_dir)
    response = client.get("/api/glossary/library")
    assert response.status_code == 200
    assert response.json() == []


def test_import_inline_text_sync(library_dir):
    client = _build_client(library_dir)
    payload = json.dumps({"entries": [{"source": "Hi", "target": "Salut"}]})
    response = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "json_pairs",
                "text": payload,
                "name": "Inline",
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entry_count"] == 1
    assert body["queued"] is False
    assert body["format"] == "json_pairs"


def test_import_csv_inline_bytes_sync(library_dir):
    client = _build_client(library_dir)
    raw = (FIXTURES / "pairs.csv").read_bytes()
    body = {
        "source": {
            "format": "csv",
            "inline_bytes_b64": base64.b64encode(raw).decode("ascii"),
            "name": "FromCSV",
        }
    }
    response = client.post("/api/glossary/import", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["entry_count"] >= 4
    listing = client.get("/api/glossary/library").json()
    assert len(listing) == 1
    assert listing[0]["entry_count"] == payload["entry_count"]


def test_import_requires_text_or_bytes(library_dir):
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/import",
        json={"source": {"format": "csv"}},
    )
    assert response.status_code == 422


def test_max_entries_too_small_returns_bad_request(library_dir):
    client = _build_client(library_dir)
    raw = (FIXTURES / "pairs.csv").read_bytes()
    body = {
        "source": {
            "format": "csv",
            "inline_bytes_b64": base64.b64encode(raw).decode("ascii"),
            "max_entries": 2,
        }
    }
    response = client.post("/api/glossary/import", json=body)
    assert response.status_code == 400, response.text
    body_json = response.json()
    assert body_json["error"] == "bad_request"
    assert "max 2" in body_json["detail"]


def test_toggle_endpoint_persists(library_dir):
    client = _build_client(library_dir)
    payload = json.dumps({"entries": [{"source": "A", "target": "1"}]})
    response = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "json_pairs",
                "text": payload,
                "name": "T",
            }
        },
    )
    assert response.status_code == 200
    glossary_id = response.json()["glossary_id"]

    toggle = client.post(
        f"/api/glossary/library/{glossary_id}/enable",
        json={"enabled": False},
    )
    assert toggle.status_code == 200
    assert toggle.json()["enabled"] is False

    listing = client.get("/api/glossary/library").json()
    assert listing[0]["enabled"] is False


def test_toggle_unknown_returns_404(library_dir):
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/library/missing-id/enable",
        json={"enabled": False},
    )
    assert response.status_code == 404


def test_delete_endpoint_removes_entry(library_dir):
    client = _build_client(library_dir)
    payload = json.dumps({"entries": [{"source": "A", "target": "1"}]})
    response = client.post(
        "/api/glossary/import",
        json={"source": {"format": "json_pairs", "text": payload, "name": "T"}},
    )
    glossary_id = response.json()["glossary_id"]
    delete = client.delete(f"/api/glossary/library/{glossary_id}")
    assert delete.status_code == 200
    listing = client.get("/api/glossary/library").json()
    assert listing == []


def test_preview_endpoint_reports_conflicts(library_dir):
    client = _build_client(library_dir)
    payload_a = json.dumps({"entries": [{"source": "Hello", "target": "Hola"}]})
    payload_b = json.dumps({"entries": [{"source": "Hello", "target": "Bonjour"}]})
    client.post(
        "/api/glossary/import",
        json={"source": {"format": "json_pairs", "text": payload_a, "name": "A"}},
    )
    client.post(
        "/api/glossary/import",
        json={"source": {"format": "json_pairs", "text": payload_b, "name": "B"}},
    )
    response = client.get("/api/glossary/library/preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["enabled_glossaries"] == ["A", "B"]
    assert any(c["source"] == "hello" for c in payload["conflicts"])


def test_entries_endpoint_returns_entries(library_dir):
    client = _build_client(library_dir)
    payload = json.dumps({"entries": [{"source": "A", "target": "1"}]})
    response = client.post(
        "/api/glossary/import",
        json={"source": {"format": "json_pairs", "text": payload, "name": "T"}},
    )
    glossary_id = response.json()["glossary_id"]
    response = client.get(f"/api/glossary/library/{glossary_id}/entries")
    assert response.status_code == 200
    body = response.json()
    assert body["entries"] == [
        {"source": "A", "target": "1", "case_sensitive": False, "notes": ""}
    ]
