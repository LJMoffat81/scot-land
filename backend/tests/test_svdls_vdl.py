"""SVDLS vacant/derelict routes: site-level as published; 503 when unavailable."""

from __future__ import annotations

from layers.svdls_geometry import (
    GEOMETRY_PRECEDENCE,
    GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
)
from layers.vdl import OUT_SR, SITE_TYPES, _site_props, _size_ha, query_bbox, query_point


GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_size_ha_coerces_published_string():
    assert _size_ha("3.61") == 3.61
    assert _size_ha(0.81) == 0.81
    assert _size_ha(None) is None
    assert _size_ha("") is None
    assert _size_ha("not-a-number") is None


def test_site_props_map_published_fields():
    props = _site_props(
        {
            "site_name": "FORMER TORPEDO RANGE",
            "site_type": "Derelict",
            "site_size": "3.61",
            "local_auth": "Loch Lomond and Trossachs National Park",
            "owner_1": "Defence",
            "site_code": "ARROCHAR VE1",
            "address": "Arrochar",
            "period": "1980 or earlier",
        }
    )
    assert props["name"] == "FORMER TORPEDO RANGE"
    assert props["site_type"] == "Derelict"
    assert props["size_ha"] == 3.61
    assert props["local_authority"] == "Loch Lomond and Trossachs National Park"
    assert props["owner_class"] == "Defence"
    assert props["site_code"] == "ARROCHAR VE1"
    assert props["address"] == "Arrochar"
    assert props["period"] == "1980 or earlier"
    assert props["layer"] == "vdl"
    assert props["geometry_source"] == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    assert props["geometry_source_label"] == "Spatial Hub survey"
    assert "Open Government Licence" in props["source"]
    assert "Improvement Service" in props["source"]


def test_published_site_types_documented():
    assert SITE_TYPES == (
        "Vacant Land",
        "Vacant Land and Buildings",
        "Derelict",
    )


def test_featureserver_requests_set_out_sr_4326(monkeypatch):
    """GIS note: live FeatureServer queries must request WGS84 (outSR=4326)."""
    seen: list[dict] = []

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"type": "FeatureCollection", "features": []}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get(self, _url, params=None):
            seen.append(dict(params or {}))
            return _Resp()

    monkeypatch.setattr("layers.vdl._client", lambda: _Client())
    assert OUT_SR == 4326
    query_bbox(55.84, -4.30, 55.88, -4.22)
    query_point(55.86, -4.26)
    assert len(seen) == 2
    for params in seen:
        assert params.get("outSR") == 4326
        assert params.get("inSR") == 4326


def test_vdl_503_when_upstream_fails(client, monkeypatch):
    def _down(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": False, "error": "upstream timeout", "layer": "vdl"},
        }

    monkeypatch.setattr("api.platform_routes.vdl_bbox", _down)
    r = client.get("/layers/open/vdl", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "upstream" in detail
    assert "features" not in r.json()
    assert "MOCK" not in r.text


def test_vdl_ok_empty_viewport_is_not_503(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "vdl",
                "count": 0,
                "licence": "OGL-3.0",
                "site_types": list(SITE_TYPES),
                "gaps": ["Owner class is a survey field, not legal title"],
            },
        }

    monkeypatch.setattr("api.platform_routes.vdl_bbox", _empty)
    r = client.get("/layers/open/vdl", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True
    assert body["meta"]["licence"] == "OGL-3.0"


def test_vdl_ok_returns_site_level_properties(client, monkeypatch):
    def _sites(*_a, **_k):
        return {
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
                        "name": "TEST SITE",
                        "site_type": "Vacant Land",
                        "size_ha": 1.25,
                        "local_authority": "Glasgow City",
                        "owner_class": "Local Authority",
                        "site_code": "GLA TEST1",
                        "geometry_source": GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
                        "geometry_source_label": "Spatial Hub survey",
                        "layer": "vdl",
                        "source": "Scottish Vacant and Derelict Land Survey.",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "vdl",
                "count": 1,
                "licence": "OGL-3.0",
                "geometry_precedence": list(GEOMETRY_PRECEDENCE),
                "geometry_source_live": GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
                "register_url": (
                    "https://www.gov.scot/publications/"
                    "the-scottish-vacant-and-derelict-land-survey-site-register/"
                ),
            },
        }

    monkeypatch.setattr("api.platform_routes.vdl_bbox", _sites)
    r = client.get("/layers/open/vdl", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    feat = r.json()["features"][0]
    props = feat["properties"]
    assert props["site_code"] == "GLA TEST1"
    assert props["site_type"] == "Vacant Land"
    assert props["size_ha"] == 1.25
    assert props["owner_class"] == "Local Authority"
    assert props["geometry_source"] == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    meta = r.json()["meta"]
    assert "register_url" in meta
    assert meta["geometry_precedence"] == list(GEOMETRY_PRECEDENCE)
    assert meta["geometry_source_live"] == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
