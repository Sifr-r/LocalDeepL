"""GET/POST /api/config and the /api/config/ocr aliases."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_config_seed_shape(api_client: TestClient) -> None:
    response = api_client.get("/api/config")
    assert response.status_code == 200
    seeded = response.json()
    assert seeded["pipeline_mode"] == "hybrid"
    assert seeded["dense_mode"] == "auto"
    assert seeded["document_processors"] == []
    assert seeded["api_base"]


def test_config_round_trip_ignores_unknown_keys(api_client: TestClient) -> None:
    updated = api_client.post(
        "/api/config", json={"model": "new-model", "dpi": 300, "unknown_key": 1}
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["model"] == "new-model"
    assert body["dpi"] == 300
    assert "unknown_key" not in body

    # The next GET sees the same store.
    assert api_client.get("/api/config").json()["model"] == "new-model"


def test_config_ocr_aliases_share_the_store(api_client: TestClient) -> None:
    api_client.post("/api/config", json={"model": "aliased-model"})
    assert api_client.get("/api/config/ocr").json()["model"] == "aliased-model"

    put = api_client.put("/api/config/ocr", json={"dense_mode": "always"})
    assert put.status_code == 200
    assert put.json()["dense_mode"] == "always"
    assert api_client.get("/api/config").json()["dense_mode"] == "always"
