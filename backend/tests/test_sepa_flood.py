"""SEPA Flood Maps catalog, bbox API, and PostGIS ingest helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from layers.flood import (
    ATTRIBUTION,
    LICENCE,
    LICENCE_URL,
    catalog_layer,
    query_bbox,
)
from layers.platform import platform_catalog

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sepa_flood_sample.geojson"
GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_catalog_lists_flood_live_with_licence_and_source():
    layer = catalog_layer()
    assert layer["id"] == "flood"
    assert layer["ledger_role"] == "constraint"
    assert layer["ledger_row"] is None
    assert layer["ui_surface"] == "ledger"
    assert layer["status"] == "live"
    assert layer["licence"] == LICENCE
    assert layer["licence_url"] == LICENCE_URL
    assert "www2.sepa.org.uk/flooddata" in layer["source_url"]
    assert layer["endpoint"] == "/layers/open/flood"
    assert "tile_endpoint" not in layer
    assert "mapserver_url" not in layer
    assert "www2.sepa.org.uk/flooddata" in layer["description"]

    catalog = platform_catalog()
    ids = [row["id"] for row in catalog["layers"]]
    assert "flood" in ids
    flood = next(row for row in catalog["layers"] if row["id"] == "flood")
    assert flood["status"] == "live"
    assert flood["licence"] == "OGL-3.0"
    assert flood["licence_url"] == LICENCE_URL
    assert flood["source_url"]
    assert flood["ledger_role"] == "constraint"
    assert flood.get("ledger_row") is None
    assert flood["ui_surface"] == "ledger"
    assert "mapserver_url" not in flood


def test_query_bbox_unloaded_is_honest(monkeypatch):
    """When PostGIS is empty, return ok=False — never hit live SEPA services."""
    monkeypatch.setattr("layers.flood.is_loaded", lambda: False)

    payload = query_bbox(**GLASGOW_BBOX, max_features=10)
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []
    assert payload["meta"]["ok"] is False
    assert payload["meta"]["licence"] == LICENCE
    assert payload["meta"]["licence_url"] == LICENCE_URL
    assert "flooddata" in payload["meta"]["source_url"]
    assert payload["meta"].get("backend") == "postgis"
    assert "sepa_mapserver" not in str(payload)


def test_query_bbox_503_path_when_unloaded(client, monkeypatch):
    monkeypatch.setattr("layers.flood.is_loaded", lambda: False)

    def _boom(*args, **kwargs):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": "sepa_flood is missing or empty",
                "licence": LICENCE,
                "licence_url": LICENCE_URL,
            },
        }

    monkeypatch.setattr("api.platform_routes.flood_bbox", _boom)
    response = client.get("/layers/open/flood", params=GLASGOW_BBOX)
    assert response.status_code == 503
    assert "flood" in response.json()["detail"].lower()


def test_open_flood_ok(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.flood_bbox",
        lambda *a, **k: {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "backend": "postgis",
                "count": 0,
                "licence": LICENCE,
                "licence_url": LICENCE_URL,
                "source": ATTRIBUTION,
            },
        },
    )
    response = client.get("/layers/open/flood", params=GLASGOW_BBOX)
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["ok"] is True


def test_ingest_fixture_roundtrip(monkeypatch):
    pytest.importorskip("psycopg2")
    import os

    url = (os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        pytest.skip("no PostGIS URL for flood ingest test")
    if not FIXTURE.is_file():
        pytest.skip("fixture missing")

    from etl import ingest_sepa_flood as ingest
    from layers import flood as flood_mod

    monkeypatch.setenv("DATABASE_URL", url)
    conn = ingest.connect()
    try:
        ingest.ensure_table(conn)
        count = ingest.load_geojson(FIXTURE, conn, replace=True)
    finally:
        conn.close()
    assert count >= 1

    payload = flood_mod.query_bbox(55.84, -4.30, 55.88, -4.22, max_features=10)
    assert payload["meta"]["ok"] is True
    assert payload["meta"]["backend"] == "postgis"
    assert payload["meta"]["licence"] == LICENCE
    assert len(payload["features"]) >= 1


def test_fixture_geojson_is_valid():
    assert FIXTURE.is_file()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["type"] == "FeatureCollection"
    assert data["features"]


def test_flood_module_has_no_mapserver_constants():
    import layers.flood as flood_mod

    text = Path(flood_mod.__file__).read_text(encoding="utf-8")
    assert "map.sepa.org.uk" not in text
    assert "httpx" not in text
    assert "MAPSERVER" not in text
    assert "LIVE_LAYER_IDS" not in text
    assert "_query_live_layer" not in text
