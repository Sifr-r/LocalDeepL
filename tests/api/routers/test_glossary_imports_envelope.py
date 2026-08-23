"""Envelope-shape regression tests for the swept glossary_imports routes.

Phase C follow-up: the 10 raw ``HTTPException`` sites in
``src/omniscribe/api/routers/glossary_imports.py`` were replaced with typed
envelope exceptions (``ValidationFailed`` for 422 sites, ``NotFound`` for
404 sites). This file pins the new envelope shape so any regression to a
raw ``{"detail": "..."}`` body fails loudly.

The tests mirror the ``library_dir`` fixture pattern from
``tests/api/routers/test_glossary_imports_route.py`` — a tmp-dir ``GlossaryLibrary``
swapped onto ``state.glossary_library`` and torn down at fixture exit.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import glossary_imports, state
from omniscribe.core.lexicon import LanceDBLexiconStore, get_default_embedding_model

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "glossary"


@pytest.fixture
def library_dir(tmp_path, monkeypatch):
    artifact = tmp_path / "artifacts"
    artifact.mkdir(exist_ok=True)
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(artifact))
    store = LanceDBLexiconStore(
        path=artifact / "lexicon.lance",
        embedding_model=get_default_embedding_model(),
    )
    state.lexicon_store = store
    yield artifact
    monkeypatch.undo()


def _build_client(library_dir: Path) -> TestClient:
    from omniscribe.api.services.envelope import register_envelope_handlers

    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(glossary_imports.router)
    return TestClient(app)


def _seed_glossary(client: TestClient) -> str:
    """Seed a tiny JSON-pairs glossary and return its glossary_id."""
    payload = json.dumps({"entries": [{"source": "A", "target": "1"}]})
    response = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "json_pairs",
                "text": payload,
                "name": "Seed",
            }
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["glossary_id"]


# ---------------------------------------------------------------------------
# 404 envelope coverage — toggle / reorder / delete / entries
# ---------------------------------------------------------------------------


def test_toggle_unknown_glossary_returns_envelope(library_dir):
    """``POST /api/glossary/library/{unknown}/enable`` must return 404 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/library/missing-id/enable",
        json={"enabled": False},
    )

    assert response.status_code == 404
    body = response.json()
    assert body == {"error": "not_found", "detail": "Glossary not found."}


def test_reorder_unknown_glossary_returns_envelope(library_dir):
    """``POST /api/glossary/library/reorder`` with an unknown id must return 404 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/library/reorder",
        json={"ordered_ids": ["does-not-exist"]},
    )

    assert response.status_code == 404
    body = response.json()
    assert body == {"error": "not_found", "detail": "Glossary not found."}


def test_delete_unknown_glossary_returns_envelope(library_dir):
    """``DELETE /api/glossary/library/{unknown}`` must return 404 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.delete("/api/glossary/library/missing-id")

    assert response.status_code == 404
    body = response.json()
    assert body == {"error": "not_found", "detail": "Glossary not found."}


def test_entries_unknown_glossary_returns_envelope(library_dir):
    """``GET /api/glossary/library/{unknown}/entries`` must return 404 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.get("/api/glossary/library/missing-id/entries")

    assert response.status_code == 404
    body = response.json()
    assert body == {"error": "not_found", "detail": "Glossary not found."}


# ---------------------------------------------------------------------------
# 422 envelope coverage — reorder ValueError + inline-format validators
# ---------------------------------------------------------------------------


def test_reorder_bad_input_returns_validation_failed(library_dir):
    """Exercise both branches of ``reorder_library`` to lock down the envelope shape.

    The library's reorder allows any id set; the empty-list branch
    short-circuits to 200, the unknown-id branch raises ``GlossaryNotFoundError``
    → ``NotFound`` (404), and the ``ValueError`` branch is defensive and
    unreachable from the public surface today (kept as a placeholder so
    that any future change that exposes it has a clear test site).
    """
    client = _build_client(library_dir)
    glossary_id = _seed_glossary(client)

    # Empty list → 200 (reorder is a no-op).
    response_empty = client.post(
        "/api/glossary/library/reorder",
        json={"ordered_ids": []},
    )
    assert response_empty.status_code == 200
    assert response_empty.json() == {"ok": True}

    # Unknown id → 404 + canonical envelope (exercises the swept NotFound branch).
    response_404 = client.post(
        "/api/glossary/library/reorder",
        json={"ordered_ids": ["ghost-id"]},
    )
    assert response_404.status_code == 404
    body = response_404.json()
    assert body["error"] == "not_found"
    assert body["detail"] == "Glossary not found."

    # Sanity: a happy reorder with the real id still works.
    response_ok = client.post(
        "/api/glossary/library/reorder",
        json={"ordered_ids": [glossary_id]},
    )
    assert response_ok.status_code == 200
    assert response_ok.json() == {"ok": True}


def test_import_csv_without_text_or_bytes_returns_validation_failed(library_dir):
    """``POST /api/glossary/import`` for CSV with neither ``text`` nor
    ``inline_bytes_b64`` must return 422 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/import",
        json={"source": {"format": "csv"}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert "text" in body["detail"] and "inline_bytes_b64" in body["detail"]


def test_import_csv_invalid_base64_returns_validation_failed(library_dir):
    """``POST /api/glossary/import`` for CSV with an ``inline_bytes_b64``
    that is not valid base64 must return 422 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "csv",
                "inline_bytes_b64": "!!! not base64 !!!",
            }
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert "base64" in body["detail"]


def test_import_sql_missing_fields_returns_validation_failed(library_dir):
    """``POST /api/glossary/import`` for SQL with missing fields must return
    422 + canonical envelope (not the legacy FastAPI ``{"detail": ...}`` shape)."""
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "sql_table",
                "sql_dsn": "sqlite:///tmp/example.db",
                # Missing sql_source_table / sql_source_col / sql_target_col
            }
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert "sql_dsn" in body["detail"]


def test_import_sql_unsafe_dsn_returns_validation_failed(library_dir):
    """``POST /api/glossary/import`` for SQL with an unsafe DSN (semicolon)
    must return 422 + canonical envelope."""
    client = _build_client(library_dir)
    response = client.post(
        "/api/glossary/import",
        json={
            "source": {
                "format": "sql_table",
                "sql_dsn": "sqlite:///tmp/example.db; DROP TABLE users;",
                "sql_source_table": "glossary",
                "sql_source_col": "source",
                "sql_target_col": "target",
            }
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert "unsafe" in body["detail"]


def test_import_csv_inline_bytes_happy_path_still_works(library_dir):
    """Sanity: a valid CSV with ``inline_bytes_b64`` still flows through the
    sweep site to the parser without affecting the envelope shape."""
    client = _build_client(library_dir)
    raw = (FIXTURES / "pairs.csv").read_bytes()
    response = client.post(
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
    body = response.json()
    assert body["entry_count"] >= 4
    assert body["queued"] is False
