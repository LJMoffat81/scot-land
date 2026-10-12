"""Data Zone bbox overlay: PostGIS preferred, rollups, no rent £."""

from __future__ import annotations

from layers.data_zones import OGL_V3_URL, query_bbox, query_bbox_arcgis
from layers.platform import platform_catalog

GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_catalog_lists_live_data_zones_with_ogl():
    row = next(r for r in platform_catalog()["layers"] if r["id"] == "data_zones")
    assert row["status"] == "live"
    assert row["endpoint"] == "/layers/open/data-zones"
    assert row["minzoom"] == 10
    assert "Open Government Licence" in row["licence"]
    assert row["licence_url"] == OGL_V3_URL
    assert "spatialdata.gov.scot" in row["source_url"]
    assert "AGR" in (row.get("description") or "") or "£" in (
        row.get("description") or ""
    )


def test_data_zones_503_when_upstream_fails(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.data_zones_bbox",
        lambda *_a, **_k: {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": False, "error": "upstream timeout", "layer": "data_zones"},
        },
    )
    r = client.get("/layers/open/data-zones", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "upstream" in detail
    assert "features" not in r.json()


def test_data_zones_ok_empty_viewport_is_not_503(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.data_zones_bbox",
        lambda *_a, **_k: {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "data_zones",
                "count": 0,
                "vintage": 2011,
                "serve": "postgis:dz_boundaries",
                "licence": "Open Government Licence v3.0",
                "licence_url": OGL_V3_URL,
                "note": "Boundaries and open rollups only.",
            },
        },
    )
    r = client.get("/layers/open/data-zones", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True


def test_data_zones_ok_features_have_rollups_no_rent(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.data_zones_bbox",
        lambda *_a, **_k: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-4.25, 55.85],
                                [-4.24, 55.85],
                                [-4.24, 55.86],
                                [-4.25, 55.86],
                                [-4.25, 55.85],
                            ]
                        ],
                    },
                    "properties": {
                        "code": "S01009859",
                        "name": "Ibrox - 01",
                        "vintage": 2011,
                        "la_name": "Glasgow City",
                        "population": 812,
                        "pop_year": 2022,
                        "dwellings": 410,
                        "dw_year": 2025,
                        "layer": "data_zones",
                        "source": "test",
                        "licence": "Open Government Licence v3.0",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "data_zones",
                "count": 1,
                "vintage": 2011,
                "serve": "postgis:dz_boundaries",
                "note": "Boundaries and open rollups only.",
            },
        },
    )
    r = client.get("/layers/open/data-zones", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    props = body["features"][0]["properties"]
    assert props["code"] == "S01009859"
    assert props["name"] == "Ibrox - 01"
    assert props["la_name"] == "Glasgow City"
    assert props["population"] == 812
    assert props["dwellings"] == 410
    assert "annual_ground_rent" not in props
    assert "agr" not in {k.lower() for k in props}
    text = r.text.lower()
    assert "£" not in text
    assert "annual_ground_rent" not in text


def test_query_bbox_prefers_postgis(monkeypatch):
    monkeypatch.setattr(
        "layers.data_zones.query_bbox_postgis",
        lambda *_a, **_k: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.25, 55.86]},
                    "properties": {
                        "code": "S01009859",
                        "name": "Ibrox - 01",
                        "vintage": 2011,
                        "population": 100,
                        "layer": "data_zones",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "serve": "postgis:dz_boundaries",
                "layer": "data_zones",
                "count": 1,
            },
        },
    )

    def _boom(*_a, **_k):
        raise AssertionError("ArcGIS fallback must not run when PostGIS works")

    monkeypatch.setattr("layers.data_zones.query_bbox_arcgis", _boom)
    payload = query_bbox(55.84, -4.30, 55.88, -4.22, max_features=10)
    assert payload["meta"]["serve"] == "postgis:dz_boundaries"
    assert payload["features"][0]["properties"]["population"] == 100


def test_query_bbox_arcgis_maps_props(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.25, 55.86]},
                        "properties": {"datazone": "S01009859", "name": "Ibrox - 01"},
                    }
                ],
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *_a, **_k):
            return FakeResp()

    monkeypatch.setattr("layers.data_zones._client", FakeClient)
    payload = query_bbox_arcgis(55.84, -4.30, 55.88, -4.22, max_features=10)
    assert payload["meta"]["ok"] is True
    assert payload["meta"]["licence_url"] == OGL_V3_URL
    assert payload["features"][0]["properties"]["code"] == "S01009859"
    assert payload["features"][0]["properties"]["vintage"] == 2011
