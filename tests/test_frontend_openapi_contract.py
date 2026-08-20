"""Frontend ↔ OpenAPI contract test (audit P3-11).

The audit found a live contract break (``GET /api/glossary/merged`` 404'd
on every page load) that no existing test would have caught. This module
pins the HTTP surface the Svelte client actually consumes:

* every endpoint mirrored from ``frontend/src/lib/api/endpoints.ts`` (plus
  ``websocket.ts`` / ``appStore.ts``) must exist in the live OpenAPI
  schema with the right method;
* the progress WebSocket path must stay registered;
* the committed route snapshot (``tests/openapi.json``) must not drift
  from the live schema. Regenerate it with ``make openapi`` (which
  rewrites ``tests/openapi.json`` from ``app.openapi()``) or with
  ``OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/test_frontend_openapi_contract.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omniscribe.server import create_app

SNAPSHOT_PATH = Path(__file__).parent / "openapi.json"

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Mirror of frontend/src/lib/api/endpoints.ts (single API client module),
# plus the fetches in websocket.ts, appStore.ts and websocketStore.ts.
# Keep in sync when adding a frontend API call.
FRONTEND_HTTP_ENDPOINTS: list[tuple[str, str]] = [
    # config + models (appStore.loadModels uses the bare /models route)
    ("GET", "/api/config"),
    ("POST", "/api/config"),
    ("GET", "/api/models"),
    ("GET", "/api/models/ocr"),
    ("GET", "/api/models/translation"),
    ("GET", "/api/models/transcription"),
    # providers
    ("GET", "/api/providers"),
    ("GET", "/api/providers/{provider_id}"),
    # OCR process (sync + async + status + result + cancel)
    ("POST", "/api/process"),
    ("POST", "/api/process/async"),
    ("GET", "/api/process/status/{job_id}"),
    ("GET", "/api/jobs/{job_id}/result"),
    ("POST", "/api/jobs/{job_id}/cancel"),
    # exports
    ("POST", "/api/export/document"),
    ("POST", "/api/export/docx"),
    # translation + transcription + extraction
    ("POST", "/api/translate"),
    ("POST", "/api/translate/async"),
    ("GET", "/api/translate/status/{job_id}"),
    ("POST", "/api/transcribe"),
    ("POST", "/api/extract"),
    # glossary library + imports
    ("GET", "/api/glossary/library"),
    ("GET", "/api/glossary/library/merged"),
    ("GET", "/api/glossary/library/preview"),
    ("GET", "/api/glossary/library/{glossary_id}/entries"),
    ("POST", "/api/glossary/library/{glossary_id}/enable"),
    ("DELETE", "/api/glossary/library/{glossary_id}"),
    ("POST", "/api/glossary/library/reorder"),
    ("POST", "/api/glossary/import"),
    ("POST", "/api/glossary/import/url"),
    # job history
    ("GET", "/api/jobs"),
    ("DELETE", "/api/jobs"),
    # token-bound artifact downloads (Authorization header)
    ("GET", "/api/text/{artifact_id}"),
    ("GET", "/api/export/{artifact_id}"),
    # progress session minting + cancel (websocket.ts / websocketStore.ts)
    ("POST", "/api/progress/session"),
    ("POST", "/api/progress/cancel/{channel_id}"),
]


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def openapi_schema(app):
    return app.openapi()


def _live_routes(schema: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in _HTTP_METHODS
    }


@pytest.mark.parametrize(
    ("method", "path"),
    FRONTEND_HTTP_ENDPOINTS,
    ids=[f"{method} {path}" for method, path in FRONTEND_HTTP_ENDPOINTS],
)
def test_frontend_endpoint_exists_in_openapi(
    openapi_schema: dict, method: str, path: str
):
    """Every call the Svelte client makes must resolve to a registered route.

    This is the regression that would have caught the historical
    ``GET /api/glossary/merged`` 404 on every page load.
    """
    operations = openapi_schema["paths"].get(path)
    assert operations is not None, (
        f"Frontend calls {method} {path} but the route is not registered. "
        f"Update the backend route or frontend/src/lib/api/endpoints.ts."
    )
    assert method.lower() in operations, (
        f"Route {path} exists but does not accept {method}."
    )


def test_progress_websocket_route_is_registered(app):
    """``websocket.ts`` dials ``/ws/{channelId}`` — keep the path pinned."""
    from starlette.routing import WebSocketRoute

    def _walk(routes):
        for route in routes:
            yield route
            nested = getattr(route, "routes", None)
            if nested:
                yield from _walk(nested)
            # Recent starlette wraps include_router() targets lazily;
            # the flattened routes live on ``original_router``.
            original = getattr(route, "original_router", None)
            if original is not None and hasattr(original, "routes"):
                yield from _walk(original.routes)

    ws_paths = {
        route.path for route in _walk(app.routes) if isinstance(route, WebSocketRoute)
    }
    assert "/ws/{channel_id}" in ws_paths


def test_no_duplicate_operation_ids(openapi_schema: dict):
    """Duplicate operation IDs mean two handlers share a route path+method
    (one silently shadows the other, as /api/export/docx once did)."""
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path, operations in openapi_schema["paths"].items():
        for method, operation in operations.items():
            if method not in _HTTP_METHODS:
                continue
            operation_id = operation.get("operationId", "")
            if operation_id in seen:
                duplicates.append(
                    f"{operation_id}: {seen[operation_id]} vs {method.upper()} {path}"
                )
            seen.setdefault(operation_id, f"{method.upper()} {path}")
    assert not duplicates, "Duplicate OpenAPI operation IDs: " + "; ".join(duplicates)


def test_openapi_route_snapshot_matches_live_schema(openapi_schema: dict):
    """The committed snapshot must list exactly the live (method, path) set.

    The snapshot keeps the full spec for reference; only the route set is
    compared so schema-internal churn (descriptions, example values)
    does not force regeneration.
    """
    live = _live_routes(openapi_schema)

    if os.getenv("OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT"):
        SNAPSHOT_PATH.write_text(
            json.dumps(openapi_schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        pytest.skip("Snapshot regenerated.")

    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    recorded = _live_routes(snapshot)

    missing = sorted(live - recorded)
    stale = sorted(recorded - live)
    assert not missing and not stale, (
        "OpenAPI route snapshot is out of date.\n"
        f"  new routes: {missing}\n"
        f"  removed routes: {stale}\n"
        "Regenerate with: "
        "OMNISCRIBE_UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest "
        "tests/test_frontend_openapi_contract.py"
    )
