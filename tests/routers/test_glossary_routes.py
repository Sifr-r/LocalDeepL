"""Router contract tests for the glossary plugin (client-frozen).

Ports the pre-harness pins (`e6b7b89^:tests/api/routers/
test_glossary_imports_route.py`, `_envelope.py`, `_async.py`) onto the
booted harness with a fake in-memory LexiconStore.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.plugins.test_glossary_service import FakeLexiconStore

FIXTURES = Path(__file__).parent.parent / "fixtures" / "glossary"


def _inject_store(api_client: TestClient) -> FakeLexiconStore:
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
    payload: dict[str, Any] = {"source": {"format": "json_pairs", "text": text}}
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
        return json.dumps({"entries": [{"source": "Hi", "target": "Salut"}]}).encode(
            "utf-8"
        )

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

    empty = api_client.post("/api/glossary/library/reorder", json={"ordered_ids": []})
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
    _import_json_pairs(api_client, '{"entries": [{"source": "A", "target": "1"}]}', "T")
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

    # One-line JSON text has 0 newlines → estimate 1; threshold 0 forces
    # every import onto the async path deterministically.
    monkeypatch.setattr(glossary_service, "SYNC_THRESHOLD", 0)
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
    store = _get_service(api_client)._store_provider()
    while deadline > 0 and not store.list_glossaries():
        time.sleep(0.01)
        deadline -= 0.01
    assert len(store.list_glossaries()) == 1
    assert store.list_glossaries()[0].entry_count == 2
