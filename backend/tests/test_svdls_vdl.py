"""SVDLS vacant/derelict routes: Data Zone totals; 503 when unavailable."""

from __future__ import annotations

import csv
from pathlib import Path

from layers.svdls_geometry import (
    GEOMETRY_PRECEDENCE,
    GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
)
from layers.vdl import (
    OPEN_VDL_FORBIDDEN_KEYS,
    OPEN_VDL_META_KEYS,
    OPEN_VDL_TOP_KEYS,
    OPEN_VDL_ZONE_KEYS,
    OUT_SR,
    SITE_TYPES,
    _site_props,
    _size_ha,
    query_bbox,
    query_point,
)


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


# Locked copies of the public whitelist. Importing the module constants and
# comparing them here means a quiet widening of either side fails the test.
_EXPECTED_TOP_KEYS = frozenset({"type", "features", "meta"})
_EXPECTED_META_KEYS = frozenset(
    {
        "ok",
        "layer",
        "count",
        "capped",
        "grain",
        "licence",
        "source",
        "register_url",
        "spatial_hub_url",
        "publication_url",
        "site_types",
        "gaps",
        "data_zones",
    }
)
_EXPECTED_ZONE_KEYS = frozenset({"data_zone", "vintage", "site_count", "area_ha"})
# Live /layers/open/vdl property names (size_ha, not site_size_ha).
_PER_SITE_KEYS = frozenset({"site_code", "size_ha", "address", "owner_class"})
_EXPECTED_FORBIDDEN_KEYS = frozenset(
    {
        "site_code",
        "site_name",
        "name",
        "address",
        "uprn",
        "size_ha",
        "site_size",
        "owner_class",
        "owner_1",
        "site_type",
        "local_authority",
        "local_auth",
        "period",
        "geometry",
        "coordinates",
        "geometry_source",
        "geometry_source_label",
    }
)


def _keys(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.append(str(key))
            found.extend(_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_keys(child))
    return found


def test_vdl_open_response_keys_are_data_zone_only(client, monkeypatch):
    """Hostile upstream site rows must not survive /layers/open/vdl.

    Fails on main before VDL-DZ-1: the route returned site_code, per-site
    area and polygon coordinates.
    """

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
                        "address": "1 High Street",
                        "uprn": "123456789",
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

    assert OPEN_VDL_TOP_KEYS == _EXPECTED_TOP_KEYS
    assert OPEN_VDL_META_KEYS == _EXPECTED_META_KEYS
    assert OPEN_VDL_ZONE_KEYS == _EXPECTED_ZONE_KEYS
    assert OPEN_VDL_FORBIDDEN_KEYS == _EXPECTED_FORBIDDEN_KEYS
    monkeypatch.setattr("api.platform_routes.vdl_bbox", _sites)
    r = client.get("/layers/open/vdl", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    leaked = sorted(_PER_SITE_KEYS.intersection(_keys(body)))
    assert leaked == [], f"per-site keys still public: {leaked}"
    assert "geometry" not in _keys(body)
    assert "coordinates" not in _keys(body)
    assert set(body) == _EXPECTED_TOP_KEYS
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    meta = body["meta"]
    assert set(meta) == _EXPECTED_META_KEYS
    assert meta["grain"] == "data_zone"
    assert meta["ok"] is True
    assert meta["licence"] == "OGL-3.0"
    assert meta["data_zones"] == []
    leaked = _EXPECTED_FORBIDDEN_KEYS.intersection(_keys(body))
    assert leaked == set()
    text = r.text
    assert "site_code" not in text
    assert "GLA TEST1" not in text
    assert "1 High Street" not in text
    assert "123456789" not in text
    assert "coordinates" not in text
    for zone in meta["data_zones"]:
        assert set(zone) == _EXPECTED_ZONE_KEYS


def test_query_bbox_rolls_sites_up_to_data_zone(monkeypatch):
    """Two sites in one zone become one total. Site identifiers stay internal."""
    seen: list[dict] = []

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.25, 55.86]},
                        "properties": {
                            "site_name": "SECRET ONE",
                            "site_code": "GLA TEST1",
                            "address": "1 High Street",
                            "site_size": "1.25",
                            "site_type": "Vacant Land",
                            "uprn": "111",
                        },
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.24, 55.87]},
                        "properties": {
                            "site_name": "SECRET TWO",
                            "site_code": "GLA TEST2",
                            "site_size": "2.75",
                            "site_type": "Derelict",
                        },
                    },
                ],
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get(self, _url, params=None):
            seen.append(dict(params or {}))
            return _Resp()

    monkeypatch.setattr("layers.vdl._client", lambda: _Client())
    monkeypatch.setattr(
        "layers.vdl.zone_for_point",
        lambda _lng, _lat: ("S01014567", 2022),
    )
    body = query_bbox(55.84, -4.30, 55.88, -4.22)
    assert set(body) == _EXPECTED_TOP_KEYS
    assert body["features"] == []
    assert set(body["meta"]) == _EXPECTED_META_KEYS
    assert body["meta"]["data_zones"] == [
        {
            "data_zone": "S01014567",
            "vintage": 2022,
            "site_count": "<3",
            "area_ha": None,
        }
    ]
    text = str(body)
    assert "1.25" not in text
    assert "2.75" not in text
    assert set(body["meta"]["data_zones"][0]) == _EXPECTED_ZONE_KEYS
    assert _PER_SITE_KEYS.isdisjoint(_keys(body))
    assert "GLA TEST1" not in text
    assert "SECRET" not in text
    assert "site_code" not in text
    assert "size_ha" not in text
    assert "address" not in text
    assert "owner_class" not in text
    assert "coordinates" not in text
    assert seen[0]["outSR"] == 4326


def test_small_count_area_does_not_leak(client, monkeypatch):
    """One site of 3.27 ha publishes no area. Three sites totalling 7.3 ha round to 7.5.

    Fails on main before VDL-DZ-2: the open response carried the exact site area.
    """

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.25, 55.86]},
                        "properties": {"site_name": "ONE", "site_size": "3.27"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.20, 55.90]},
                        "properties": {"site_name": "A", "site_size": "2.40"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.21, 55.91]},
                        "properties": {"site_name": "B", "site_size": "2.40"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-4.22, 55.92]},
                        "properties": {"site_name": "C", "site_size": "2.50"},
                    },
                ],
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get(self, _url, params=None):
            return _Resp()

    def _zone(lng, lat):
        if lat < 55.88:
            return ("S01014567", 2022)
        return ("S01014568", 2022)

    monkeypatch.setattr("layers.vdl._client", lambda: _Client())
    monkeypatch.setattr("layers.vdl.zone_for_point", _zone)
    r = client.get("/layers/open/vdl", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    by_code = {zone["data_zone"]: zone for zone in body["meta"]["data_zones"]}
    assert by_code["S01014567"] == {
        "data_zone": "S01014567",
        "vintage": 2022,
        "site_count": "<3",
        "area_ha": None,
    }
    assert by_code["S01014568"] == {
        "data_zone": "S01014568",
        "vintage": 2022,
        "site_count": 3,
        "area_ha": 7.5,
    }
    assert "3.27" not in r.text
    assert body["meta"]["source"] == (
        "Totals from the Scottish Vacant and Derelict Land Survey, grouped by Data Zone. "
        "Zones with one or two sites show no area."
    )
    assert body["meta"]["gaps"][0] == body["meta"]["source"]
    for phrase in (
        "Survey sites, not a title",
        "Owner class is a survey field",
        "Survey polygons are indicative",
    ):
        assert phrase not in r.text


def test_public_vdl_downloads_hide_small_site_areas():
    """Committed zone packs must not keep an exact area for a 1- or 2-site zone."""
    root = Path(__file__).resolve().parents[2]
    downloads = root / "frontend" / "public" / "downloads"
    for name in (
        "vacant-derelict-land-dz2022.csv",
        "vacant-derelict-land-dz2011.csv",
    ):
        path = downloads / name
        assert path.is_file(), path
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        ha_cols = [key for key in rows[0] if key.startswith("ha")]
        assert ha_cols
        for row in rows:
            count = row["n_sites"]
            assert count not in {"1", "2"}
            if count == "<3":
                for col in ha_cols:
                    assert row[col] == ""


def test_query_point_omits_site_fields(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "features": [
                    {
                        "attributes": {
                            "site_name": "SECRET",
                            "site_code": "GLA TEST1",
                            "address": "1 High Street",
                            "site_size": "1.5",
                        }
                    }
                ]
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get(self, _url, params=None):
            return _Resp()

    monkeypatch.setattr("layers.vdl._client", lambda: _Client())
    body = query_point(55.86, -4.26)
    assert body["ok"] is True
    assert body["intersects"] is True
    assert body["sites"] == []
    assert "GLA TEST1" not in str(body)
    assert "site_code" not in str(body)
