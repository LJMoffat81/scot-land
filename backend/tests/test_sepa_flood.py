"""SEPA Flood Maps catalog, bbox API, and PostGIS ingest helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from layers.flood import (
    ATTRIBUTION,
    LICENCE,
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
    assert layer["status"] == "live"
    assert layer["licence"] == LICENCE
    assert "sepa.org.uk/flooddata" in layer["source_url"]
    assert layer["endpoint"] == "/layers/open/flood"
    assert "flood/tiles" in layer["tile_endpoint"]

    catalog = platform_catalog()
    ids = [row["id"] for row in catalog["layers"]]
    assert "flood" in ids
    flood = next(row for row in catalog["layers"] if row["id"] == "flood")
    assert flood["status"] == "live"
    assert flood["licence"] == "OGL-3.0"
    assert flood["source_url"]


def test_query_bbox_live_or_empty_meta(monkeypatch):
    """When PostGIS is empty, live MapServer path returns ok or honest failure."""

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-4.28, 55.85],
                                    [-4.27, 55.85],
                                    [-4.27, 55.86],
                                    [-4.28, 55.86],
                                    [-4.28, 55.85],
                                ]
                            ],
                        },
                        "properties": {
                            "OBJECTID": 1,
                            "SOURCE": "River",
                            "PROB": "M",
                            "SCENARIO": "Present Day",
                            "MAP_TYPE": "Hazard",
                            "REFERENCE": "HA_TEST",
                            "VERSION": "v3_0",
                        },
                    }
                ],
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            assert "/Flood_Maps/MapServer/" in url
            return _Resp()

    monkeypatch.setattr("layers.flood.is_loaded", lambda: False)
    monkeypatch.setattr("layers.flood.httpx.Client", _Client)

    payload = query_bbox(**GLASGOW_BBOX, max_features=10)
    assert payload["type"] == "FeatureCollection"
    assert payload["meta"]["ok"] is True
    assert payload["meta"]["licence"] == LICENCE
    assert payload["meta"]["backend"] == "sepa_mapserver"
    assert len(payload["features"]) >= 1
    assert payload["features"][0]["properties"]["licence"] == LICENCE


def test_query_bbox_503_path_when_upstream_down(client, monkeypatch):
    monkeypatch.setattr("layers.flood.is_loaded", lambda: False)

    def _boom(*args, **kwargs):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": False, "error": "connection failed", "licence": LICENCE},
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
