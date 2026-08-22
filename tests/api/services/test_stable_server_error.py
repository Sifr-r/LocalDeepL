"""Envelope-shape regression test for ``stable_server_error``.

Phase C follow-up: ``stable_server_error()`` previously routed through
``api_error_response(status_code, SERVER_ERROR_MESSAGE)`` which placed the
human-readable sentence in the ``error`` field. The wire contract requires
``error`` to be a stable machine code, so this test pins:

- ``error == "internal_error"``
- ``detail == SERVER_ERROR_MESSAGE``
- ``status_code`` is preserved from the call site (default 500, customizable
  to 503 for backend-unavailable cases).
"""

from __future__ import annotations

import json

from fastapi.responses import JSONResponse

from omniscribe.api.services.api_helpers import stable_server_error
from omniscribe.api.services.security import SERVER_ERROR_MESSAGE


def _body(response: JSONResponse) -> dict:
    """Decode the JSONResponse body, returning an empty dict for empty bodies."""
    raw = response.body
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def test_stable_server_error_default_is_500_with_stable_code() -> None:
    """The default call must return 500 + canonical envelope shape.

    ``error`` must be the stable ``internal_error`` code (NOT the
    human-readable ``SERVER_ERROR_MESSAGE`` sentence), and ``detail``
    must carry the human-readable message."""
    response = stable_server_error()

    assert response.status_code == 500
    body = _body(response)
    assert body == {
        "error": "internal_error",
        "detail": SERVER_ERROR_MESSAGE,
    }


def test_stable_server_error_custom_status_preserved() -> None:
    """A caller-supplied status code (e.g. 503) must be reflected in the response."""
    response = stable_server_error(503)

    assert response.status_code == 503
    body = _body(response)
    assert body["error"] == "internal_error"
    assert body["detail"] == SERVER_ERROR_MESSAGE


def test_stable_server_error_does_not_leak_sentence_in_error_field() -> None:
    """The human-readable ``SERVER_ERROR_MESSAGE`` must NOT appear in the
    ``error`` field. This is the regression that triggered this fix."""
    response = stable_server_error()
    body = _body(response)

    assert "error" in body
    assert body["error"] != SERVER_ERROR_MESSAGE, (
        "error field must be a stable machine code, not the human-readable "
        "SERVER_ERROR_MESSAGE sentence"
    )


def test_stable_server_error_returns_jsonresponse_instance() -> None:
    """The return type must remain ``JSONResponse`` so the 3 callers in
    ``routers/translation.py`` + ``routers/extraction.py`` +
    ``routers/transcription.py`` keep compiling."""
    response = stable_server_error()
    assert isinstance(response, JSONResponse)
