from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import artifacts, state
from omniscribe.api.routers.common import get_access_token
from omniscribe.api.services.artifacts import TextArtifactStore


def test_get_access_token_emits_deprecation_warning_and_logs(
    caplog: pytest.LogCaptureFixture,
):
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        with caplog.at_level(logging.WARNING):
            token = get_access_token(token="legacy_token_123")

    assert token == "legacy_token_123"
    assert len(recorded_warnings) == 1
    assert issubclass(recorded_warnings[0].category, DeprecationWarning)
    assert (
        "Query parameter '?token=' is deprecated and will be removed in a future release. "
        "Use 'Authorization: Bearer <token>' or 'X-Artifact-Token' header instead."
    ) in str(recorded_warnings[0].message)

    assert any(
        "Deprecated query parameter '?token=' used; prefer 'Authorization: Bearer' or 'X-Artifact-Token' header."
        in record.message
        for record in caplog.records
    )


def test_get_access_token_header_precedence():
    # 1. X-Artifact-Token beats Authorization and token
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        token = get_access_token(
            token="legacy_token",
            authorization="Bearer auth_bearer_token",
            x_artifact_token="x_header_token",
        )
    assert token == "x_header_token"

    # 2. Authorization Bearer beats query token
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        token = get_access_token(
            token="legacy_token",
            authorization="Bearer auth_bearer_token",
            x_artifact_token=None,
        )
    assert token == "auth_bearer_token"

    # 3. Query token fallback
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        token = get_access_token(
            token="legacy_token",
            authorization=None,
            x_artifact_token=None,
        )
    assert token == "legacy_token"


def test_get_access_token_no_warning_when_using_headers(
    caplog: pytest.LogCaptureFixture,
):
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        with caplog.at_level(logging.WARNING):
            t1 = get_access_token(
                token=None,
                authorization="Bearer auth_token",
                x_artifact_token=None,
            )
            t2 = get_access_token(
                token=None,
                authorization=None,
                x_artifact_token="x_token",
            )

    assert t1 == "auth_token"
    assert t2 == "x_token"
    assert len(recorded_warnings) == 0
    assert not any(
        "Deprecated query parameter" in record.message for record in caplog.records
    )


def test_artifact_endpoint_with_deprecated_query_token_emits_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    app = FastAPI()
    app.include_router(artifacts.router)

    old_store = state.text_artifacts
    store = TextArtifactStore(artifact_dir=tmp_path)
    state.text_artifacts = store
    try:
        artifact_file = tmp_path / "test.json"
        artifact_file.write_text('{"pages": {}}', encoding="utf-8")
        handle = store.put(
            artifact_id="a" * 32,
            token="t" * 43,
            path=artifact_file,
        )

        client = TestClient(app)

        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")
            with caplog.at_level(logging.WARNING):
                response = client.get(
                    f"/api/text/{handle.artifact_id}?token={handle.token}"
                )

        assert response.status_code == 200
        assert len(recorded_warnings) >= 1
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "Query parameter '?token=' is deprecated" in str(w.message)
            for w in recorded_warnings
        )
        assert any(
            "Deprecated query parameter '?token=' used" in r.message
            for r in caplog.records
        )
    finally:
        state.text_artifacts = old_store
