"""OpenAPI snapshot: writes ``tests/openapi.json`` when missing, diffs otherwise.

The snapshot pins the full route surface the frontend codes against. To
regenerate after an intentional route change, delete ``tests/openapi.json``
and run this test once.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def test_openapi_schema_matches_snapshot(api_client: TestClient) -> None:
    # Routes are included during lifespan startup, so the booted app's
    # schema is the complete surface.
    schema = api_client.app.openapi()
    if not SNAPSHOT_PATH.is_file():
        SNAPSHOT_PATH.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert schema == expected, (
        "openapi.json drifted from the live route surface; if the change is "
        "intentional, delete tests/openapi.json and rerun this test to "
        "regenerate the snapshot."
    )
